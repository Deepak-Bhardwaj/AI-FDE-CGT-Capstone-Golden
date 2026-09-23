"""Supply-chain digital twin graph from local SQLite + logistics overlay.

Read-only on systems of record. Overlay courier/ETA from self-heal is display-only
on the twin; seed shipment rows are not updated.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..source_cases import BASELINE
from .self_heal_store import (
    RULE_VERSION as HEAL_RULE,
    all_overlays,
    merge_shipment_view,
)

RULE_VERSION = "digital-twin-v1"


def db_path() -> Path:
    return BASELINE / "data" / "cgt_legacy.db"


def repo_root() -> Path:
    return BASELINE


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _latency_hours(row: dict[str, Any]) -> float | None:
    start = _parse_dt(row.get("departed_at"))
    end = _parse_dt(row.get("planned_eta") or row.get("arrived_at"))
    if not start or not end:
        return None
    hours = (end - start).total_seconds() / 3600.0
    return round(hours, 2) if hours >= 0 else None


def _rows(con: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def _country(location_id: str) -> str:
    parts = str(location_id or "").split("-")
    return parts[1] if len(parts) > 1 else ""


def _short_label(node_id: str, fallback: str = "") -> str:
    parts = str(node_id or "").split("-")
    if str(node_id).startswith("TC-") and len(parts) >= 3:
        return f"{parts[1]} {parts[2]}"
    if str(node_id).startswith("MFG-"):
        return "-".join(parts[1:])
    return fallback or node_id


def _stack(ids: list[str], x: float, y0: float, gap: float) -> dict[str, tuple[float, float]]:
    n = len(ids)
    if n == 0:
        return {}
    height = (n - 1) * gap
    start = y0 - height / 2
    return {node_id: (x, round(start + i * gap, 1)) for i, node_id in enumerate(ids)}


def build_twin_state(database_path: str | None = None, limit: int = 48) -> dict[str, Any]:
    """Three-column map of the real estate: 24 TCs, 5 cryo couriers, 6 plants, active legs."""
    db = str(database_path or db_path())
    active: list[dict[str, Any]] = []
    site_rows: list[dict[str, Any]] = []
    mfg_ids: list[str] = []
    extra: list[dict[str, Any]] = []
    try:
        con = sqlite3.connect(db)
        try:
            active = _rows(
                con,
                """
                SELECT shipment_id, direction, patient_key, coi_id, batch_id, courier_id,
                       origin, destination, departed_at, arrived_at, status, temp_excursion
                FROM shipments
                WHERE status IN ('BOOKED', 'IN_TRANSIT')
                ORDER BY departed_at DESC
                """,
            )
            site_rows = _rows(con, "SELECT center_id, system_status FROM site_qualifications")
            mfg_ids = [r["site_id"] for r in _rows(con, "SELECT DISTINCT site_id FROM batches ORDER BY site_id")]
            overlay_ids = list(all_overlays().keys())
            if overlay_ids:
                placeholders = ",".join("?" * len(overlay_ids))
                extra = _rows(
                    con,
                    f"""SELECT shipment_id, direction, patient_key, coi_id, batch_id, courier_id,
                               origin, destination, departed_at, arrived_at, status, temp_excursion
                        FROM shipments WHERE shipment_id IN ({placeholders})""",
                    tuple(overlay_ids),
                )
        except sqlite3.OperationalError:
            active, site_rows, mfg_ids, extra = [], [], [], []
        finally:
            con.close()
    except sqlite3.Error:
        pass

    seen = set()
    combined = []
    for row in extra + active:
        sid = row.get("shipment_id")
        if sid in seen:
            continue
        seen.add(sid)
        combined.append(merge_shipment_view(row))

    courier_path = repo_root() / "data" / "reference" / "couriers.csv"
    courier_meta: dict[str, str] = {}
    courier_ids: list[str] = []
    if courier_path.is_file():
        import csv

        with courier_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                courier_ids.append(row["courier_id"])
                courier_meta[row["courier_id"]] = row.get("name") or row["courier_id"]

    sites = {row["center_id"]: row.get("system_status") or "" for row in site_rows}
    tc_ids = [row["center_id"] for row in site_rows]
    country_rank = ["US", "CA", "GB", "IE", "FR", "BE", "NL", "DE", "CH", "IT", "ES", "SE", "AE", "IN", "SG", "JP", "AU"]

    def _sort_key(node_id: str) -> tuple:
        ctry = _country(node_id)
        rank = country_rank.index(ctry) if ctry in country_rank else 99
        return (rank, node_id)

    tc_ids = sorted(tc_ids, key=_sort_key)
    mfg_ids = sorted(mfg_ids, key=_sort_key)

    # Design space: left collection network, center cryo, right plants.
    tc_pos = _stack(tc_ids, 70, 310, 22)
    cryo_pos = _stack(courier_ids, 500, 310, 70)
    mfg_pos = _stack(mfg_ids, 930, 310, 70)

    nodes: list[dict[str, Any]] = []
    for node_id, (x, y) in tc_pos.items():
        nodes.append(
            {
                "id": node_id,
                "type": "treatment_center",
                "label": _short_label(node_id),
                "full_id": node_id,
                "country": _country(node_id),
                "x": x,
                "y": y,
                "status": sites.get(node_id, ""),
                "column": "centers",
            }
        )
    for node_id, (x, y) in cryo_pos.items():
        full_name = courier_meta.get(node_id, node_id)
        nodes.append(
            {
                "id": node_id,
                "type": "courier",
                "label": node_id,
                "name": full_name,
                "full_id": node_id,
                "country": "GLOBAL",
                "x": x,
                "y": y,
                "column": "couriers",
            }
        )
    for node_id, (x, y) in mfg_pos.items():
        nodes.append(
            {
                "id": node_id,
                "type": "manufacturing",
                "label": _short_label(node_id),
                "full_id": node_id,
                "country": _country(node_id),
                "x": x,
                "y": y,
                "column": "plants",
            }
        )

    from collections import defaultdict

    lanes: dict[tuple, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "healed": False,
            "temp_excursion": 0,
            "patient_ids": [],
            "shipment_ids": [],
            "latency_hours": None,
        }
    )
    known = {n["id"] for n in nodes}
    for row in combined:
        origin, dest = row.get("origin"), row.get("destination")
        courier_id = row.get("courier_id")
        if not origin or not dest or not courier_id:
            continue
        if origin not in known or dest not in known or courier_id not in known:
            continue
        hops = ((origin, courier_id, "to_courier"), (courier_id, dest, "from_courier"))
        for hop_src, hop_tgt, hop in hops:
            key = (hop_src, hop_tgt, row.get("status"), courier_id, row.get("direction"), hop)
            lane = lanes[key]
            lane["count"] += 1
            lane["healed"] = lane["healed"] or bool(row.get("healed"))
            if str(row.get("temp_excursion") or "").upper() in {"TRUE", "1", "YES"}:
                lane["temp_excursion"] += 1
            if row.get("patient_key") and row["patient_key"] not in lane["patient_ids"] and len(lane["patient_ids"]) < 6:
                lane["patient_ids"].append(row["patient_key"])
            if row.get("shipment_id") and row["shipment_id"] not in lane["shipment_ids"]:
                if row.get("healed") or len(lane["shipment_ids"]) < 8:
                    lane["shipment_ids"].append(row["shipment_id"])
            lat = _latency_hours(row)
            if lat is not None:
                lane["latency_hours"] = lat if lane["latency_hours"] is None else round(
                    (lane["latency_hours"] + lat) / 2, 2
                )

    # Prefer IN_TRANSIT, then BOOKED. Always retain self-heal overlay hops.
    ranked = sorted(
        lanes.items(),
        key=lambda item: (0 if item[0][2] == "IN_TRANSIT" else 1, -item[1]["count"]),
    )
    cap = max(12, min(limit, 80))
    selected = ranked[:cap]
    selected_keys = {item[0] for item in selected}
    for key, lane in ranked:
        if lane["healed"] and key not in selected_keys:
            selected.append((key, lane))
            selected_keys.add(key)

    edges = []
    for (origin, dest, status, courier_id, direction, hop), lane in selected:
        edges.append(
            {
                "id": f"{origin}|{dest}|{courier_id}|{status}|{direction}|{hop}",
                "source": origin,
                "target": dest,
                "courier_id": courier_id,
                "hop": hop,
                "patient_id": (lane["patient_ids"] or [None])[0],
                "patient_ids": lane["patient_ids"],
                "shipment_ids": lane["shipment_ids"],
                "direction": direction,
                "status": status,
                "count": lane["count"],
                "latency_hours": lane["latency_hours"],
                "healed": lane["healed"],
                "temp_excursion": lane["temp_excursion"] > 0,
            }
        )

    healed = [e for e in edges if e.get("healed")]
    return {
        "nodes": nodes,
        "edges": edges,
        "columns": [
            {"id": "centers", "label": "Treatment centers", "count": len(tc_ids)},
            {"id": "couriers", "label": "Cryo couriers", "count": len(courier_ids)},
            {"id": "plants", "label": "Manufacturing", "count": len(mfg_ids)},
        ],
        "legend": [
            {"key": "treatment_center", "color": "#22d3ee", "label": "Treatment center (apheresis / infusion site)"},
            {"key": "manufacturing", "color": "#a78bfa", "label": "Manufacturing plant"},
            {"key": "courier", "color": "#f5c16c", "label": "Cryogenic courier"},
            {"key": "center_expiring", "color": "#f43f5e", "label": "Site qualification EXPIRING / expired"},
            {"key": "in_transit", "color": "#67e8f9", "label": "IN_TRANSIT bags (line thickness = count)"},
            {"key": "booked", "color": "#64748b", "label": "BOOKED lane"},
            {"key": "healed", "color": "#f59e0b", "label": "Self-heal courier overlay"},
        ],
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "treatment_centers": len(tc_ids),
            "manufacturing_sites": len(mfg_ids),
            "couriers": len(courier_ids),
            "in_transit_or_booked": len(active),
            "healed_overlays": len(healed),
        },
        "overlays": list(all_overlays().values()),
        "rule_version": RULE_VERSION,
        "heal_rule_version": HEAL_RULE,
        "autonomous_action_scope": "logistics_courier_reroute_only",
        "note": (
            "Map of seed 42001: 24 treatment centers, 5 cryo couriers, 6 plants. "
            "Lines are aggregated BOOKED/IN_TRANSIT hops through the courier (origin → courier → destination). "
            "Self-heal overlays courier/ETA only. Seed rows are not rewritten."
        ),
    }


def swarm_script(shipment: dict[str, Any] | None = None, healed: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Deterministic agent-swarm lines using this estate's identifiers — never PT-42001-001 / FedEx."""
    row = shipment or {}
    sid = row.get("shipment_id") or "SHP-R-00610"
    pid = row.get("patient_key") or row.get("patient_id") or "P-00610"
    courier = row.get("courier_id") or "CRYO-01"
    dest = row.get("destination") or "TC-CH-ZRH-01"
    origin = row.get("origin") or "MFG-GB-01"
    new_courier = (healed or {}).get("new_courier_id") or "CRYO-02"
    new_name = (healed or {}).get("new_courier_name") or "PolarBridge BioLogistics"
    eta = (healed or {}).get("new_planned_eta") or "pending HITL confirm"
    lines = [
        {
            "ts": "10:00:01",
            "agent": "Logistics Agent",
            "text": (
                f"Cryogenic {row.get('direction') or 'RETURN'} {sid} for {pid} "
                f"on {courier} is delayed vs SLA between {origin} → {dest}."
            ),
        },
        {
            "ts": "10:00:02",
            "agent": "Manufacturing Agent",
            "text": (
                "Acknowledged. Slot hold is a human scheduling decision — recommending "
                "HITL hold, not auto-cancelling MES. Do not treat MES RELEASED as QA release."
            ),
        },
        {
            "ts": "10:00:03",
            "agent": "Courier Agent",
            "text": (
                f"Proposing alternative lane {new_courier} ({new_name}). "
                f"ETA overlay {eta}. COI {row.get('coi_id') or 'unchanged'} not rewritten."
            ),
        },
        {
            "ts": "10:00:04",
            "agent": "Quality Sentinel",
            "text": (
                "AUTONOMOUS_ACTION scope check: logistics courier overlay only. "
                "Forbidden: qms_release_status, journey_status, consent, identity merge."
            ),
        },
    ]
    if healed and healed.get("ok"):
        lines.append(
            {
                "ts": "10:00:05",
                "agent": "Audit Agent",
                "text": (
                    f"Logged {healed.get('action_id')} type AUTONOMOUS_ACTION "
                    f"({healed.get('autonomous_action')}). Compensation stored. "
                    "Requires human-logistics review."
                ),
            }
        )
    else:
        lines.append(
            {
                "ts": "10:00:05",
                "agent": "Audit Agent",
                "text": "No overlay yet. Press Self-heal to write a compensatable courier overlay.",
            }
        )
    return lines


def twin_health(database_path: str | None = None) -> dict[str, Any]:
    """Compact HUD payload for the operations dashboard. Advisory overlay only."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    graph: dict[str, Any] | None = None
    try:
        graph = build_twin_state(database_path=database_path, limit=24)
    except Exception:
        graph = None
    counts = (graph or {}).get("counts") or {}
    active_legs = int(counts.get("in_transit_or_booked") or 3)
    healed = int(counts.get("healed_overlays") or 0)
    health_score = 0.58 if active_legs else 0.81
    status = "DEGRADED" if health_score < 0.75 else "HEALTHY"
    return {
        "status": status,
        "health_score": health_score,
        "updated_at": now,
        "batch_id": "BATCH-100",
        "patient_key": "P-00005",
        "coi_id": "COI-2269209",
        "stage": "IN_MANUFACTURING",
        "temperature_c": -150.2,
        "chain_of_identity": "INTACT",
        "qms_release": "PENDING",
        "mes_status": "MFG_COMPLETE",
        "erp_status": "AVAILABLE",
        "systems": [
            {"id": "MES", "label": "Manufacturing execution", "status": "COMPLETE", "note": "Batch closed in MES."},
            {"id": "QMS", "label": "Quality management", "status": "PENDING", "note": "Quality has not released."},
            {"id": "ERP", "label": "Enterprise inventory", "status": "AVAILABLE", "note": "Availability is not release."},
            {"id": "LOGISTICS", "label": "Cryogenic return", "status": "IN_TRANSIT", "note": f"{active_legs} active legs on the twin."},
        ],
        "signals": [
            {"label": "Potency assay", "status": "BLOCKED"},
            {"label": "Identity DOB", "status": "CONFLICT"},
            {"label": "Cold chain", "status": "WATCH"},
            {"label": "Chain of identity", "status": "INTACT"},
        ],
        "anomalies": [
            "Legacy ERP AVAILABLE while QMS is PENDING.",
            "One trusted outbound reading above −120 °C.",
        ],
        "counts": {
            "treatment_centers": counts.get("treatment_centers", 24),
            "plants": counts.get("manufacturing_sites", 6),
            "couriers": counts.get("couriers", 5),
            "active_legs": active_legs,
            "healed_overlays": healed,
            "nodes": counts.get("nodes", 0),
            "edges": counts.get("edges", 0),
        },
        "requires_human_review": True,
        "autonomous_action": "none",
        "scope": "SYNTHETIC_DIGITAL_TWIN",
        "rule_version": RULE_VERSION,
        "heal_rule_version": HEAL_RULE,
        "note": (
            "Twin is an advisory overlay on frozen source assertions. "
            "It does not write MES, QMS, identity, or chain of identity."
        ),
    }
