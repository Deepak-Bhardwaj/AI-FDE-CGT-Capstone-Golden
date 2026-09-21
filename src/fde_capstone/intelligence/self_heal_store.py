"""Bounded logistics self-heal overlay (Repo 3.0 moonshot).

May substitute a courier / planned ETA on BOOKED or IN_TRANSIT legs only.
Must never write patient journey, QMS release, consent, identity, or COI.

Original ``shipments`` rows stay intact (evidence). The overlay is the
compensatable route change; audit rows are ``AUTONOMOUS_ACTION``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

RULE_VERSION = "self-heal-logistics-v1"
ALLOWED_STATUSES = frozenset({"BOOKED", "IN_TRANSIT"})
FORBIDDEN_FIELDS = frozenset(
    {
        "qms_release_status",
        "journey_status",
        "consent_status",
        "patient_key",
        "coi_id",
        "mes_status",
    }
)

# Courier SLA hours from data/reference/couriers.csv — used to pick a faster lane.
COURIER_SLA = {
    "CRYO-01": 28,
    "CRYO-02": 24,
    "CRYO-03": 30,
    "CRYO-04": 32,
    "CRYO-05": 30,
}
COURIER_NAME = {
    "CRYO-01": "CryoPath Global",
    "CRYO-02": "PolarBridge BioLogistics",
    "CRYO-03": "CellRoute Express",
    "CRYO-04": "BlueArc Life Logistics",
    "CRYO-05": "GeneTransit Partners",
}

_OVERLAY: dict[str, dict[str, Any]] = {}
_AUDIT: list[dict[str, Any]] = []


def reset() -> None:
    """Test helper. Clears overlay and audit without touching seed shipments."""
    _OVERLAY.clear()
    _AUDIT.clear()


def overlay_for(shipment_id: str) -> dict[str, Any] | None:
    return _OVERLAY.get(shipment_id)


def all_overlays() -> dict[str, dict[str, Any]]:
    return dict(_OVERLAY)


def audit_log() -> list[dict[str, Any]]:
    return list(_AUDIT)


def choose_alternate_courier(current: str) -> str:
    current = (current or "").strip()
    ranked = sorted(COURIER_SLA.items(), key=lambda item: (item[1], item[0]))
    for courier_id, _sla in ranked:
        if courier_id != current:
            return courier_id
    return current or "CRYO-02"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def planned_eta(departed_at: str | None, courier_id: str) -> str:
    sla = COURIER_SLA.get(courier_id, 28)
    departed = _parse_dt(departed_at) or datetime.now(timezone.utc)
    return (departed + timedelta(hours=sla)).isoformat().replace("+00:00", "Z")


def apply_self_heal(shipment: dict[str, Any], actor: str = "logistics-agent") -> dict[str, Any]:
    """Apply or replay an idempotent logistics reroute. Does not mutate ``shipment`` SoR fields in-place."""
    shipment_id = str(shipment.get("shipment_id") or "")
    if not shipment_id:
        raise ValueError("shipment_id required")
    status = str(shipment.get("status") or "").upper()
    if status not in ALLOWED_STATUSES:
        return {
            "ok": False,
            "shipment_id": shipment_id,
            "error": "not_reroutable",
            "reason": (
                f"status={status}. Self-heal may only substitute courier/ETA on "
                "BOOKED or IN_TRANSIT legs. DELIVERED history is not rewritten."
            ),
            "autonomous_action": "none",
            "effect_on_clinical_state": "none",
            "effect_on_qms": "none",
            "effect_on_identity": "none",
            "rule_version": RULE_VERSION,
        }

    existing = _OVERLAY.get(shipment_id)
    if existing:
        return {**existing, "idempotent_replay": True}

    previous_courier = str(shipment.get("courier_id") or "")
    next_courier = choose_alternate_courier(previous_courier)
    eta = planned_eta(shipment.get("departed_at"), next_courier)
    now = datetime.now(timezone.utc).isoformat()
    action_id = f"AA-REROUTE-{shipment_id}"
    record = {
        "ok": True,
        "action_id": action_id,
        "action_type": "AUTONOMOUS_ACTION",
        "autonomous_action": "logistics_courier_reroute",
        "shipment_id": shipment_id,
        "patient_id": shipment.get("patient_key") or shipment.get("patient_id"),
        "previous_courier_id": previous_courier,
        "new_courier_id": next_courier,
        "previous_courier_name": COURIER_NAME.get(previous_courier, previous_courier),
        "new_courier_name": COURIER_NAME.get(next_courier, next_courier),
        "previous_planned_arrival": shipment.get("arrived_at"),
        "new_planned_eta": eta,
        "origin": shipment.get("origin"),
        "destination": shipment.get("destination"),
        "status_unchanged": status,
        "actor": actor or "logistics-agent",
        "acted_at": now,
        "idempotency_key": f"self-heal:{shipment_id}",
        "compensation": {
            "restore_courier_id": previous_courier,
            "restore_planned_arrival": shipment.get("arrived_at"),
        },
        "effect_on_clinical_state": "none",
        "effect_on_qms": "none",
        "effect_on_identity": "none",
        "effect_on_chain_of_custody_authority": "none — courier lane overlay only; COI id unchanged",
        "forbidden_fields_untouched": sorted(FORBIDDEN_FIELDS),
        "requires_human_review": True,
        "authority_requirement": "human-logistics-or-scheduling",
        "rule_version": RULE_VERSION,
        "note": (
            "Overlay only. Seed shipments.csv / SQLite shipments row is preserved. "
            "Does not hold manufacturing slots, release product, or merge identity."
        ),
    }
    _OVERLAY[shipment_id] = record
    _AUDIT.append(dict(record))
    return {**record, "idempotent_replay": False}


def merge_shipment_view(row: dict[str, Any]) -> dict[str, Any]:
    """Return a display copy of a shipment with overlay courier/ETA if healed."""
    view = dict(row)
    overlay = _OVERLAY.get(str(row.get("shipment_id") or ""))
    if not overlay or not overlay.get("ok"):
        view["healed"] = False
        return view
    view["healed"] = True
    view["courier_id"] = overlay["new_courier_id"]
    view["planned_eta"] = overlay["new_planned_eta"]
    view["previous_courier_id"] = overlay["previous_courier_id"]
    view["autonomous_action"] = overlay["autonomous_action"]
    view["action_id"] = overlay["action_id"]
    return view
