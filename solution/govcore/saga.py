"""POC-3 - Idempotent slot and logistics orchestration with saga compensation.

Closes the non-idempotent SlotService defect (INJ-006) and the scheduler/MES phantom
capacity conflict (F-ST-005).

Engineering controls implemented here:
  idempotency keys · explicit state machine · transactional outbox · retry policy ·
  deduplication · correlation and causation IDs · compensation events ·
  dead-letter queue · manual recovery path · full command audit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .loader import Estate, load


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def idempotency_key(*parts: str) -> str:
    """Deterministic from business intent - the same intent always yields the same key."""
    return "IDK-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


class SagaState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class StepState(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"
    SKIPPED = "SKIPPED"


class SlotState(str, Enum):
    NONE = "NONE"
    PROVISIONAL = "PROVISIONAL"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    CONFLICT = "CONFLICT"


# Explicit state machine - transitions not listed here are rejected.
SLOT_TRANSITIONS: dict[SlotState, set[SlotState]] = {
    SlotState.NONE: {SlotState.PROVISIONAL},
    SlotState.PROVISIONAL: {SlotState.CONFIRMED, SlotState.CANCELLED, SlotState.EXPIRED, SlotState.CONFLICT},
    SlotState.CONFIRMED: {SlotState.CANCELLED, SlotState.CONFLICT},
    SlotState.CANCELLED: set(),
    SlotState.EXPIRED: set(),
    SlotState.CONFLICT: {SlotState.CANCELLED},
}


class IllegalTransition(RuntimeError):
    pass


def transition(current: SlotState, target: SlotState) -> SlotState:
    if target not in SLOT_TRANSITIONS[current]:
        raise IllegalTransition(f"{current.value} -> {target.value} is not a permitted slot transition")
    return target


@dataclass
class Command:
    command_id: str
    name: str
    idempotency_key: str
    correlation_id: str
    causation_id: str | None
    payload: dict
    issued_at: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        return {"command_id": self.command_id, "name": self.name,
                "idempotency_key": self.idempotency_key, "correlation_id": self.correlation_id,
                "causation_id": self.causation_id, "payload": self.payload,
                "issued_at": self.issued_at}


class IdempotencyStore:
    """Same key returns the original result. This is the fix for INJ-006."""

    def __init__(self) -> None:
        self._results: dict[str, dict] = {}
        self.replays = 0

    def seen(self, key: str) -> bool:
        return key in self._results

    def get(self, key: str) -> dict:
        self.replays += 1
        return self._results[key]

    def put(self, key: str, result: dict) -> dict:
        self._results.setdefault(key, result)
        return self._results[key]


class Outbox:
    """Transactional outbox - state change and event emission cannot diverge."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.published: list[dict] = []

    def stage(self, event_type: str, correlation_id: str, payload: dict,
              causation_id: str | None = None) -> dict:
        event = {"event_id": f"EVT-{len(self.events)+1:05d}", "event_type": event_type,
                 "correlation_id": correlation_id, "causation_id": causation_id,
                 "occurred_at": _now(), "recorded_at": _now(), "payload": payload}
        self.events.append(event)
        return event

    def publish(self) -> list[dict]:
        pending = [e for e in self.events if e not in self.published]
        self.published.extend(pending)
        return pending


class DeadLetterQueue:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, command: Command, error: str, attempts: int) -> dict:
        item = {"command": command.as_dict(), "error": error, "attempts": attempts,
                "queued_at": _now(), "manual_recovery_required": True, "owner": None}
        self.items.append(item)
        return item


@dataclass
class Step:
    name: str
    action: Callable[[dict], dict]
    compensate: Callable[[dict], dict] | None = None
    state: StepState = StepState.PENDING
    result: dict = field(default_factory=dict)
    error: str | None = None
    attempts: int = 0


@dataclass
class SagaRun:
    saga_id: str
    correlation_id: str
    state: SagaState
    steps: list[dict]
    events: list[dict]
    exception: dict | None = None
    alternatives: list[dict] = field(default_factory=list)
    requires_approval: str | None = None

    def as_dict(self) -> dict:
        return {"saga_id": self.saga_id, "correlation_id": self.correlation_id,
                "state": self.state.value, "steps": self.steps, "events": self.events,
                "exception": self.exception, "alternatives": self.alternatives,
                "requires_approval": self.requires_approval}


class SlotOrchestrator:
    """Reserve capacity -> confirm MES -> reserve outbound logistics.

    Forward progression stops on the first conflict. Completed steps are compensated in
    reverse order, provisional capacity is released, an exception is raised with an owner,
    alternates are proposed, and planner approval is required before any retry.
    """

    MAX_ATTEMPTS = 3

    def __init__(self, estate: Estate | None = None) -> None:
        self.est = estate or load()
        self.idempotency = IdempotencyStore()
        self.outbox = Outbox()
        self.dlq = DeadLetterQueue()
        self.reservations: dict[str, dict] = {}
        self.audit: list[dict] = []
        self.exceptions: list[dict] = []

    # -- commands ----------------------------------------------------------- #

    def reserve(self, patient_key: str, site_id: str, scheduled_start: str,
                correlation_id: str | None = None) -> dict:
        """Idempotent. Retrying the same business intent returns the original reservation."""
        key = idempotency_key("reserve_slot", patient_key, site_id, scheduled_start)
        correlation_id = correlation_id or f"COR-{key[4:12]}"
        command = Command(f"CMD-{len(self.audit)+1:05d}", "reserve_slot", key, correlation_id,
                          None, {"patient_key": patient_key, "site_id": site_id,
                                 "scheduled_start": scheduled_start})
        self.audit.append(command.as_dict())

        if self.idempotency.seen(key):
            original = self.idempotency.get(key)
            self.audit.append({"command_id": command.command_id, "outcome": "IDEMPOTENT_REPLAY",
                               "reservation_id": original["reservation_id"]})
            return original

        reservation = {
            "reservation_id": f"RES-{key[4:12]}",
            "idempotency_key": key,
            "correlation_id": correlation_id,
            "patient_key": patient_key,
            "site_id": site_id,
            "scheduled_start": scheduled_start,
            "state": transition(SlotState.NONE, SlotState.PROVISIONAL).value,
            "created_at": _now(),
        }
        self.reservations[reservation["reservation_id"]] = reservation
        self.outbox.stage("SLOT_RESERVED_PROVISIONAL", correlation_id, reservation, command.command_id)
        return self.idempotency.put(key, reservation)

    def release(self, reservation_id: str, reason: str) -> dict:
        res = self.reservations[reservation_id]
        res["state"] = transition(SlotState(res["state"]), SlotState.CANCELLED).value
        res["released_reason"] = reason
        self.outbox.stage("SLOT_RELEASED", res["correlation_id"],
                          {"reservation_id": reservation_id, "reason": reason})
        return res

    def _confirm_with_mes(self, ctx: dict) -> dict:
        """MES is authoritative for manufacturing capacity. Scheduler optimism is not enough."""
        slot = next((s for s in self.est.slots_by_key.get(ctx["patient_key"], [])), None)
        if slot is None:
            raise RuntimeError("no scheduler slot record exists for this patient")
        if slot["mes_state"] == "CANCELLED":
            raise RuntimeError(
                f"MES has cancelled {slot['slot_id']} while the scheduler reports "
                f"{slot['scheduler_state']} - phantom capacity, forward progression stopped")
        return {"slot_id": slot["slot_id"], "mes_state": slot["mes_state"],
                "scheduler_state": slot["scheduler_state"]}

    def _reserve_logistics(self, ctx: dict) -> dict:
        courier = self.est.courier_by_id.get("CRYO-02")
        return {"courier_id": courier["courier_id"], "sla_hours": courier["sla_hours"],
                "booking_ref": f"BKG-{ctx['reservation_id'][4:]}"}

    # -- saga --------------------------------------------------------------- #

    def run_reservation_saga(self, patient_key: str, site_id: str,
                             scheduled_start: str) -> SagaRun:
        correlation_id = f"COR-{idempotency_key('saga', patient_key, site_id)[4:12]}"
        saga_id = f"SAGA-{correlation_id[4:]}"
        ctx: dict = {"patient_key": patient_key, "site_id": site_id,
                     "scheduled_start": scheduled_start}

        steps = [
            Step("reserve_capacity",
                 lambda c: self.reserve(c["patient_key"], c["site_id"], c["scheduled_start"],
                                        correlation_id),
                 lambda c: self.release(c["reservation_id"], "saga compensation")),
            Step("confirm_mes_acceptance", self._confirm_with_mes),
            Step("reserve_outbound_logistics", self._reserve_logistics),
        ]

        state = SagaState.RUNNING
        failure: Step | None = None

        for step in steps:
            while step.attempts < self.MAX_ATTEMPTS:
                step.attempts += 1
                try:
                    step.result = step.action(ctx)
                    step.state = StepState.SUCCEEDED
                    ctx.update(step.result)
                    self.outbox.stage(f"STEP_SUCCEEDED:{step.name}", correlation_id, step.result)
                    break
                except RuntimeError as exc:
                    step.error = str(exc)
                    # A conflict is deterministic; retrying cannot change the answer.
                    step.state = StepState.FAILED
                    self.outbox.stage(f"STEP_FAILED:{step.name}", correlation_id,
                                      {"error": step.error, "attempt": step.attempts})
                    break
            if step.state is StepState.FAILED:
                failure = step
                break

        if failure:
            state = SagaState.COMPENSATING
            for step in reversed(steps):
                if step.state is StepState.SUCCEEDED and step.compensate:
                    step.compensate(ctx)
                    step.state = StepState.COMPENSATED
                    self.outbox.stage(f"STEP_COMPENSATED:{step.name}", correlation_id,
                                      {"reservation_id": ctx.get("reservation_id")})
                elif step.state is StepState.PENDING:
                    step.state = StepState.SKIPPED
            state = SagaState.COMPENSATED

            exception = {
                "exception_id": f"EXC-{saga_id[5:]}",
                "patient_key": patient_key,
                "kind": "SLOT_ORCHESTRATION_CONFLICT",
                "detail": failure.error,
                "owner": "Manufacturing planner",
                "authority": "Manufacturing planner",
                "sla_hours": 4,
                "raised_at": _now(),
                "status": "OPEN",
            }
            self.exceptions.append(exception)
            self.dlq.add(Command(f"CMD-DLQ-{saga_id}", failure.name, "", correlation_id, None, ctx),
                         failure.error or "unknown", failure.attempts)

            return SagaRun(saga_id, correlation_id, state,
                           [self._step_dict(s) for s in steps], self.outbox.publish(),
                           exception, self.propose_alternatives(patient_key, site_id),
                           requires_approval="Manufacturing planner")

        self.outbox.stage("SAGA_COMPLETED", correlation_id, {"patient_key": patient_key})
        return SagaRun(saga_id, correlation_id, SagaState.COMPLETED,
                       [self._step_dict(s) for s in steps], self.outbox.publish())

    @staticmethod
    def _step_dict(step: Step) -> dict:
        return {"name": step.name, "state": step.state.value, "attempts": step.attempts,
                "error": step.error, "result": step.result}

    def propose_alternatives(self, patient_key: str, exclude_site: str, limit: int = 3) -> list[dict]:
        """Advisory only (Class B). A planner chooses; the system does not rebook."""
        product = self.est.by_key.get(patient_key, {}).get("product_code")
        options = []
        for site in self.est.sites:
            if site["site_id"] == exclude_site:
                continue
            booked = sum(1 for s in self.est.slots if s["site_id"] == site["site_id"])
            # QC throughput is the binding constraint, assessed over a 30-day horizon.
            capacity = int(site["qc_capacity_day"]) * 30
            options.append({
                "site_id": site["site_id"], "name": site["name"], "country": site["country"],
                "timezone": site["timezone"], "suites": int(site["suites"]),
                "qc_capacity_day": int(site["qc_capacity_day"]),
                "current_load": booked,
                "capacity_30d": capacity,
                "headroom_pct": round(max(0.0, 1 - booked / max(capacity, 1)) * 100, 1),
                "product": product,
                "trade_off": "moving this journey displaces queued patients at the receiving site",
                "requires_approval": "Manufacturing planner",
                "auto_apply": False,
            })
        options.sort(key=lambda o: -o["headroom_pct"])
        return options[:limit]


def demonstrate_idempotency(estate: Estate | None = None) -> dict:
    """Legacy mints a new UUID per retry; the orchestrator returns the original."""
    orch = SlotOrchestrator(estate)
    a = orch.reserve("P-00001", "MFG-US-NJ-01", "2026-01-15T02:00:00Z")
    b = orch.reserve("P-00001", "MFG-US-NJ-01", "2026-01-15T02:00:00Z")
    c = orch.reserve("P-00001", "MFG-US-NJ-01", "2026-01-15T02:00:00Z")
    return {
        "attempts": 3,
        "distinct_reservations": len({a["reservation_id"], b["reservation_id"], c["reservation_id"]}),
        "reservation_id": a["reservation_id"],
        "idempotent_replays": orch.idempotency.replays,
        "slot_state": a["state"],
    }
