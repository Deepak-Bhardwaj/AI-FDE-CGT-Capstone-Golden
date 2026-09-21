"""Predictive logistics delay model (POC 3).

Statistical / rule-based forecast from local synthetic evidence only.
No weather APIs, no courier network calls, no writes to MES/QMS/CRM.

Probability is a weighted combination of:
- courier historical SLA-miss rate (delivered legs vs ``data/reference/couriers.csv`` sla_hours)
- route complexity (international origin/destination, number of legs)
- manufacturing-slot urgency and scheduler/MES conflict
- seasonal delay rate by month of ``departed_at`` plus a *deterministic*
  simulated weather residual (hash of patient_key, not ``random``)

This is a **recommendation**. It does not authorize infusion, QA release,
slot cancel, or courier dispatch.
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cgt_orchestrator.paths import db_path, repo_root

RULE_VERSION = "predictive-logistics-v1"
POLICY_EXCURSION = "SOP-LOG-007-v7"

_IN_FLIGHT = frozenset(
    {
        "APHERESIS_PENDING",
        "COLLECTED",
        "IN_MANUFACTURING",
        "QC_PENDING",
        "QA_HOLD",
        "RETURN_TRANSIT",
        "INFUSION_READY",
    }
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _hours_between(start: str | None, end: str | None) -> float | None:
    departed = _parse_dt(start)
    arrived = _parse_dt(end)
    if not departed or not arrived:
        return None
    delta = (arrived - departed).total_seconds() / 3600.0
    if delta < 0:
        return None
    return delta


def _country(location_id: str | None) -> str:
    parts = str(location_id or "").split("-")
    return parts[1] if len(parts) > 1 else ""


def _truthy(value: Any) -> bool:
    return str(value or "").strip().upper() in {"1", "TRUE", "YES", "Y"}


def _simulated_weather_variance(patient_key: str, month: int) -> float:
    """Deterministic 0–0.08 stand-in for weather. Reproducible; not a forecast API."""
    digest = hashlib.sha256(f"{patient_key}:{month}:wx-sim".encode()).digest()
    return (digest[0] / 255.0) * 0.08


class _Catalog:
    def __init__(self, database_path: str | None = None) -> None:
        self.db = str(database_path or db_path())
        self.root = repo_root()
        self.sla: dict[str, int] = {}
        self.courier_name: dict[str, str] = {}
        self.late_rate: dict[str, float] = {}
        self.courier_n: dict[str, int] = {}
        self.month_late_rate: dict[int, float] = {}
        self.escalations: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        courier_path = self.root / "data" / "reference" / "couriers.csv"
        with Path(courier_path).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                cid = row["courier_id"]
                self.sla[cid] = int(row["sla_hours"])
                self.courier_name[cid] = row.get("name") or cid
        late = defaultdict(lambda: [0, 0])
        month_late = defaultdict(lambda: [0, 0])
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            for row in con.execute("SELECT * FROM shipments"):
                hours = _hours_between(row["departed_at"], row["arrived_at"])
                if hours is None or str(row["status"]).upper() != "DELIVERED":
                    continue
                cid = row["courier_id"]
                sla = self.sla.get(cid, 28)
                late[cid][1] += 1
                if hours > sla:
                    late[cid][0] += 1
                departed = _parse_dt(row["departed_at"])
                if departed:
                    month_late[departed.month][1] += 1
                    if hours > sla:
                        month_late[departed.month][0] += 1
        finally:
            con.close()
        for cid, (misses, total) in late.items():
            self.late_rate[cid] = misses / total if total else 0.0
            self.courier_n[cid] = total
        for month, (misses, total) in month_late.items():
            self.month_late_rate[month] = misses / total if total else 0.0
        esc_path = self.root / "shadow_ops" / "CourierEscalations.csv"
        if esc_path.is_file():
            with esc_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if str(row.get("status") or "").upper() == "OPEN":
                        self.escalations[row["shipment_id"]] = row

    def rows(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()


_CATALOG: _Catalog | None = None


def _catalog(database_path: str | None = None) -> _Catalog:
    global _CATALOG
    if database_path:
        return _Catalog(database_path)
    if _CATALOG is None:
        _CATALOG = _Catalog()
    return _CATALOG


def reset_catalog() -> None:
    """Test helper so a custom database_path is not required after fixture changes."""
    global _CATALOG
    _CATALOG = None


def predict_delay(patient_id: str, database_path: str | None = None) -> dict[str, Any] | None:
    """Return an explainable delay probability for one patient, or None if unknown."""
    cat = _catalog(database_path)
    patients = cat.rows("SELECT * FROM patients WHERE patient_key=?", (patient_id,))
    if not patients:
        return None
    patient = patients[0]
    shipments = cat.rows(
        "SELECT * FROM shipments WHERE patient_key=? ORDER BY departed_at",
        (patient_id,),
    )
    slots = cat.rows("SELECT * FROM manufacturing_slots WHERE patient_key=?", (patient_id,))
    factors: list[dict[str, Any]] = []
    score = 0.08
    sample_n = 0

    couriers_used = {str(s.get("courier_id") or "") for s in shipments if s.get("courier_id")}
    for cid in sorted(couriers_used):
        rate = cat.late_rate.get(cid, 0.0)
        sample_n += cat.courier_n.get(cid, 0)
        if rate >= 0.05:
            contrib = min(0.16, rate * 0.55)
            score += contrib
            factors.append(
                {
                    "factor": "COURIER_HISTORICAL_SLA_MISS",
                    "weight": round(contrib, 3),
                    "detail": (
                        f"{cat.courier_name.get(cid, cid)} ({cid}) historical SLA-miss rate "
                        f"{rate:.1%} on {cat.courier_n.get(cid, 0)} delivered legs "
                        f"(SLA {cat.sla.get(cid, 28)}h from data/reference/couriers.csv)."
                    ),
                }
            )

    international = 0
    pending = 0
    impossible = 0
    excursion = 0
    open_esc = []
    months: list[int] = []
    for ship in shipments:
        origin_c = _country(ship.get("origin"))
        dest_c = _country(ship.get("destination"))
        if origin_c and dest_c and origin_c != dest_c:
            international += 1
        status = str(ship.get("status") or "").upper()
        if status in {"BOOKED", "IN_TRANSIT"}:
            pending += 1
        departed, arrived = ship.get("departed_at"), ship.get("arrived_at")
        if departed and arrived and arrived < departed:
            impossible += 1
        if _truthy(ship.get("temp_excursion")):
            excursion += 1
        sid = ship.get("shipment_id")
        if sid in cat.escalations:
            open_esc.append(cat.escalations[sid])
        dt = _parse_dt(departed)
        if dt:
            months.append(dt.month)

    if international:
        contrib = min(0.12, 0.05 + 0.02 * international)
        score += contrib
        factors.append(
            {
                "factor": "INTERNATIONAL_ROUTE",
                "weight": round(contrib, 3),
                "detail": (
                    f"{international} leg(s) cross country codes (origin vs destination in "
                    f"data/raw/shipments.csv) — proxy for handoff/customs complexity."
                ),
            }
        )
    if len(shipments) >= 2:
        contrib = 0.04
        score += contrib
        factors.append(
            {
                "factor": "MULTI_LEG_JOURNEY",
                "weight": contrib,
                "detail": f"{len(shipments)} shipment rows (outbound/return) for {patient_id}.",
            }
        )
    if pending:
        contrib = min(0.20, 0.10 * pending)
        score += contrib
        factors.append(
            {
                "factor": "OPEN_SHIPMENT_STATUS",
                "weight": round(contrib, 3),
                "detail": f"{pending} shipment(s) still BOOKED or IN_TRANSIT.",
            }
        )
    if impossible:
        contrib = 0.12
        score += contrib
        factors.append(
            {
                "factor": "IMPOSSIBLE_TIMELINE",
                "weight": contrib,
                "detail": (
                    f"{impossible} shipment(s) have arrived_at < departed_at "
                    f"(EVAL-003). Do not invent a corrected clock."
                ),
            }
        )
    if excursion:
        contrib = min(0.14, 0.10 + 0.02 * excursion)
        score += contrib
        factors.append(
            {
                "factor": "TEMP_EXCURSION_FLAG",
                "weight": round(contrib, 3),
                "detail": (
                    f"{excursion} shipment(s) flagged temp_excursion. "
                    f"{POLICY_EXCURSION}: review, not automatic failure."
                ),
            }
        )
    if open_esc:
        contrib = min(0.18, 0.12 + 0.03 * len(open_esc))
        score += contrib
        issues = ", ".join(sorted({e.get("issue") or "UNKNOWN" for e in open_esc}))
        factors.append(
            {
                "factor": "OPEN_COURIER_ESCALATION",
                "weight": round(contrib, 3),
                "detail": (
                    f"{len(open_esc)} OPEN row(s) in shadow_ops/CourierEscalations.csv "
                    f"({issues}). Untrusted notes — not a dispatch command (EVAL-006)."
                ),
            }
        )

    for slot in slots:
        if str(slot.get("scheduler_state")) == "CONFIRMED" and str(slot.get("mes_state")) == "CANCELLED":
            score += 0.18
            factors.append(
                {
                    "factor": "MES_SLOT_CANCELLED",
                    "weight": 0.18,
                    "detail": (
                        f"{slot.get('slot_id')} scheduler CONFIRMED / MES CANCELLED "
                        f"(data/raw/manufacturing_slots.csv)."
                    ),
                }
            )
        elif str(slot.get("scheduler_state")) == "HOLD":
            score += 0.08
            factors.append(
                {
                    "factor": "SLOT_HOLD",
                    "weight": 0.08,
                    "detail": f"{slot.get('slot_id')} scheduler_state=HOLD.",
                }
            )
        try:
            priority = int(slot.get("priority") or 99)
        except (TypeError, ValueError):
            priority = 99
        if priority == 1:
            score += 0.07
            factors.append(
                {
                    "factor": "HIGH_SLOT_URGENCY",
                    "weight": 0.07,
                    "detail": f"{slot.get('slot_id')} priority=1 (scarce suite time).",
                }
            )

    journey = str(patient.get("journey_status") or "")
    if journey in {"RETURN_TRANSIT", "COLLECTED", "APHERESIS_PENDING"}:
        contrib = 0.08
        score += contrib
        factors.append(
            {
                "factor": "IN_FLIGHT_JOURNEY",
                "weight": contrib,
                "detail": f"journey_status={journey} still depends on remaining logistics/mfg.",
            }
        )

    month = months[-1] if months else datetime.now(timezone.utc).month
    seasonal = cat.month_late_rate.get(month, 0.0)
    if seasonal >= 0.04:
        contrib = min(0.10, seasonal)
        score += contrib
        factors.append(
            {
                "factor": "SEASONAL_HISTORICAL_DELAY",
                "weight": round(contrib, 3),
                "detail": (
                    f"Month {month:02d} historical SLA-miss rate {seasonal:.1%} "
                    f"on delivered legs in this fixture (not an external climatology)."
                ),
            }
        )
    weather = _simulated_weather_variance(patient_id, month)
    if weather >= 0.04:
        score += weather
        factors.append(
            {
                "factor": "SIMULATED_WEATHER_RESIDUAL",
                "weight": round(weather, 3),
                "detail": (
                    "Deterministic hash residual standing in for weather variance. "
                    "No external weather API was called."
                ),
            }
        )

    delay_probability = round(min(0.95, max(0.02, score)), 3)
    if sample_n >= 80 and impossible == 0:
        confidence = 0.82
    elif sample_n >= 30:
        confidence = 0.68
    elif shipments:
        confidence = 0.55
    else:
        confidence = 0.35
    if impossible:
        confidence = min(confidence, 0.50)

    return {
        "patient_id": patient_id,
        "delay_probability": delay_probability,
        "risk_factors": factors,
        "recommended_action": _recommend(factors, journey),
        "confidence_score": round(confidence, 2),
        "requires_human_review": True,
        "autonomous_action": "none",
        "authority_requirement": "human-logistics-or-scheduling",
        "rule_version": RULE_VERSION,
        "in_flight": journey in _IN_FLIGHT,
        "journey_status": journey,
        "evidence": {
            "shipment_ids": [s.get("shipment_id") for s in shipments],
            "slot_ids": [s.get("slot_id") for s in slots],
            "source": ["data/raw/shipments.csv", "data/raw/manufacturing_slots.csv", "data/reference/couriers.csv"],
        },
    }


def _recommend(factors: list[dict[str, Any]], journey: str) -> str:
    names = {item["factor"] for item in factors}
    if "IMPOSSIBLE_TIMELINE" in names:
        return "HITL: adjudicate source timestamps. Do not invent a corrected timeline."
    if journey == "INFUSED" and "OPEN_SHIPMENT_STATUS" not in names:
        return (
            "Retrospective signal only — journey already INFUSED. "
            "Do not rewrite history or auto-release related batches."
        )
    if "MES_SLOT_CANCELLED" in names:
        return (
            "HITL: reconcile scheduler vs MES before treating the slot as capacity. "
            "Do not auto-rebook or cancel MES."
        )
    if "OPEN_COURIER_ESCALATION" in names or "TEMP_EXCURSION_FLAG" in names:
        return (
            "HITL: review courier escalation / cryogenic flag with Quality per SOP-LOG-007-v7. "
            "Do not auto-fail, auto-reroute, or mark QA released."
        )
    if "COURIER_HISTORICAL_SLA_MISS" in names or "INTERNATIONAL_ROUTE" in names:
        return (
            "HITL: consider expedited cryo lane or extra buffer on remaining legs. "
            "Do not dispatch autonomously."
        )
    if "SLOT_HOLD" in names or "HIGH_SLOT_URGENCY" in names:
        return (
            "HITL: scheduling review of slot HOLD/priority. "
            "Revalidate site and quality gates before clinical milestones."
        )
    if "IMPOSSIBLE_TIMELINE" in names:
        return "HITL: adjudicate source timestamps. Do not invent a corrected timeline."
    return "Monitor remaining legs. No autonomous logistics or manufacturing change."


def predict_for_patient(patient_id: str, database_path: str | None = None) -> dict[str, Any] | None:
    return predict_delay(patient_id, database_path=database_path)


def top_logistics_risks(
    limit: int = 10,
    database_path: str | None = None,
    in_flight_only: bool = False,
) -> list[dict[str, Any]]:
    """Highest delay_probability patients. Default ranking includes all journeys."""
    cat = _catalog(database_path)
    keys = [row["patient_key"] for row in cat.rows("SELECT patient_key FROM patients")]
    ranked: list[dict[str, Any]] = []
    for key in keys:
        prediction = predict_delay(key, database_path=database_path)
        if prediction is None:
            continue
        if in_flight_only and not prediction.get("in_flight"):
            continue
        ranked.append(prediction)
    ranked.sort(key=lambda row: (-row["delay_probability"], row["patient_id"]))
    return ranked[: max(1, limit)]
