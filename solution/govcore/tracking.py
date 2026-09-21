"""Courier and cold-chain tracking.

Custody chain, telemetry profile, SLA performance and escalations for a shipment. Excursion
evaluation is delegated to the SOP v7 rule; nothing here dispositions material.

Positions come from the local geography reference - no external geocoding or map service is
contacted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import geo, intelligence
from .loader import Estate, load, parse_time
from .reality import EXCURSION_THRESHOLD_C, excursion_profile

CUSTODY_EVENTS = ("SHIPMENT_DISPATCHED", "SHIPMENT_RECEIVED", "COLLECTION_COMPLETED")

CHECKPOINT_LABELS = {
    "COLLECTION_COMPLETED": "Material collected",
    "SHIPMENT_DISPATCHED": "Dispatched by courier",
    "SHIPMENT_RECEIVED": "Received at destination",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _located(est: Estate, site_id: str) -> dict:
    centre = est.center_by_id.get(site_id)
    site = est.site_by_id.get(site_id)
    if centre:
        return geo.locate(site_id, centre["canonical_name"], centre["country"])
    if site:
        return geo.locate(site_id, site["name"], site["country"])
    return geo.locate(site_id)


def _sla(est: Estate, shipment: dict) -> dict:
    courier = est.courier_by_id.get(shipment["courier_id"], {})
    dep, arr = parse_time(shipment["departed_at"]), parse_time(shipment["arrived_at"])
    sla_hours = float(courier.get("sla_hours", 0) or 0)
    transit = None
    ordering_valid = True
    if dep and arr:
        if arr < dep:
            ordering_valid = False
        else:
            transit = round((arr - dep).total_seconds() / 3600, 2)
    return {
        "courier_id": shipment["courier_id"],
        "courier_name": courier.get("name"),
        "regions": courier.get("regions"),
        "sla_hours": sla_hours,
        "transit_hours": transit,
        "sla_breach": bool(transit is not None and sla_hours and transit > sla_hours),
        "overrun_hours": round(transit - sla_hours, 2) if transit is not None and sla_hours
                         and transit > sla_hours else None,
        "ordering_valid": ordering_valid,
        "planned_arrival": (dep + timedelta(hours=sla_hours)).isoformat() if dep and sla_hours else None,
    }


def _route(est: Estate, shipment: dict, sla: dict) -> dict:
    origin = _located(est, shipment["origin"])
    destination = _located(est, shipment["destination"])
    dep, arr = parse_time(shipment["departed_at"]), parse_time(shipment["arrived_at"])

    # Arrival evidence governs the map position; the status string may lag behind it.
    arrived = bool(shipment["arrived_at"])
    delivered = shipment["status"] == "DELIVERED" and arrived
    fraction = 1.0
    if not arrived and dep and sla["sla_hours"]:
        elapsed = (_now() - dep).total_seconds() / 3600
        fraction = max(0.0, min(1.0, elapsed / sla["sla_hours"]))

    position = geo.interpolate(origin, destination, fraction)
    position["label"] = (destination["city"] if arrived
                         else f"Estimated position, {round(fraction * 100)}% of planned route")
    position["estimated"] = not arrived

    return {
        "origin": origin,
        "destination": destination,
        "distance_km": geo.distance_km(origin, destination),
        "position": position,
        "delivered": delivered,
        "arrived": arrived,
        "departed_at": shipment["departed_at"] or None,
        "arrived_at": shipment["arrived_at"] or None,
        "elapsed_hours": round((( arr or _now()) - dep).total_seconds() / 3600, 2)
                         if dep and (arr or True) and (not arr or arr >= dep) else None,
    }


def _checkpoints(est: Estate, shipment: dict, route: dict, sla: dict) -> list[dict]:
    """Dated tracking timeline from collection to receipt.

    The shipment record is authoritative for when something happened; the event stream
    contributes the ingestion time, so staleness is visible per checkpoint.
    """
    origin, destination = route["origin"], route["destination"]
    dep, arr = parse_time(shipment["departed_at"]), parse_time(shipment["arrived_at"])

    events = {e["event_type"]: e for e in est.events_by_key.get(shipment["patient_key"], [])
              if e["event_type"] in CUSTODY_EVENTS}

    def build(code, title, place, occurred, status="COMPLETE", source="LOGISTICS", note=""):
        event = events.get(code)
        elapsed = None
        if dep and occurred and occurred >= dep:
            elapsed = round((occurred - dep).total_seconds() / 3600, 2)
        lag = None
        recorded = event["recorded_at"] if event else None
        recorded_dt = parse_time(recorded) if recorded else None
        if occurred and recorded_dt and recorded_dt >= occurred:
            lag = round((recorded_dt - occurred).total_seconds() / 3600, 2)
        return {
            "code": code, "title": title,
            "location": place["name"], "city": place["city"], "country": place["country"],
            "lat": place["lat"], "lon": place["lon"],
            "occurred_at": occurred.isoformat() if occurred else None,
            "recorded_at": recorded,
            "ingest_lag_hours": lag,
            "elapsed_hours": elapsed,
            "status": status,
            "source": event["source"] if event else source,
            "event_id": event["event_id"] if event else None,
            "note": note,
        }

    steps = []

    collected = events.get("COLLECTION_COMPLETED")
    if collected:
        steps.append(build("COLLECTION_COMPLETED", "Material collected", origin,
                           parse_time(collected["occurred_at"]), source="CLINICAL"))

    steps.append(build(
        "SHIPMENT_DISPATCHED", "Custody handed to courier", origin, dep,
        status="COMPLETE" if dep else "PENDING",
        note="" if dep else "No dispatch timestamp recorded"))

    if arr is None:
        steps.append(build(
            "IN_TRANSIT", "In transit", origin, None, status="ACTIVE",
            note=(f"Planned arrival {sla['planned_arrival']} under a "
                  f"{sla['sla_hours']:.0f} hour service level")
            if sla["planned_arrival"] else "Awaiting carrier update"))

    if arr:
        steps.append(build(
            "SHIPMENT_RECEIVED", "Received at destination", destination, arr,
            status="CONFLICT" if not sla["ordering_valid"] else "COMPLETE",
            note=("Arrival is recorded before departure. The custody timeline cannot be trusted "
                  "and has not been corrected." if not sla["ordering_valid"] else "")))
    else:
        steps.append(build("SHIPMENT_RECEIVED", "Awaiting receipt", destination, None,
                           status="PENDING", note="No arrival has been recorded"))

    # Chronological, with undated checkpoints held at the end.
    steps.sort(key=lambda s: (s["occurred_at"] is None, s["occurred_at"] or ""))
    for index, step in enumerate(steps, start=1):
        step["seq"] = index
    return steps


def _custody_chain(est: Estate, shipment: dict) -> list[dict]:
    chain = [{
        "step": "ORIGIN_HANDOFF", "location": shipment["origin"],
        "at": shipment["departed_at"], "verified": bool(shipment["departed_at"]),
        "source": "LOGISTICS",
    }]
    events = [e for e in est.events_by_key.get(shipment["patient_key"], [])
              if e["event_type"] in CUSTODY_EVENTS]
    for event in sorted(events, key=lambda e: e["occurred_at"]):
        chain.append({
            "step": event["event_type"], "location": None,
            "at": event["occurred_at"], "recorded_at": event["recorded_at"],
            "verified": True, "source": event["source"], "event_id": event["event_id"],
        })
    chain.append({
        "step": "DESTINATION_RECEIPT", "location": shipment["destination"],
        "at": shipment["arrived_at"], "verified": bool(shipment["arrived_at"]),
        "source": "LOGISTICS",
    })
    return chain


def track(shipment_id: str, estate: Estate | None = None) -> dict:
    est = estate or load()
    shipment = next((s for s in est.shipments if s["shipment_id"] == shipment_id), None)
    if shipment is None:
        raise KeyError(shipment_id)

    profile = excursion_profile(est, shipment_id)
    profile["flagged_by_logistics"] = shipment["temp_excursion"].strip().upper() == "TRUE"
    sla = _sla(est, shipment)
    route = _route(est, shipment, sla)
    checkpoints = _checkpoints(est, shipment, route, sla)
    decision = intelligence.evaluate_excursion(shipment_id, est)

    readings = sorted(est.telemetry_by_shipment.get(shipment_id, []),
                      key=lambda t: t["timestamp"])
    series = [{
        "timestamp": r["timestamp"],
        "temperature_c": float(r["temperature_c"]) if r["temperature_c"] else None,
        "quality": r["quality"], "gps_zone": r["gps_zone"], "sensor_id": r["sensor_id"],
        "above_threshold": bool(r["temperature_c"] and float(r["temperature_c"]) > EXCURSION_THRESHOLD_C),
    } for r in readings]

    anomalies = []
    if not sla["ordering_valid"]:
        anomalies.append("arrival is recorded before departure - the custody timeline cannot be "
                         "trusted and has not been corrected")
    if sla["sla_breach"]:
        anomalies.append(f"transit exceeded the contracted SLA by {sla['overrun_hours']}h")
    if profile["flagged_by_logistics"] and profile["above_threshold"] == 0:
        anomalies.append("flagged as an excursion with no supporting telemetry")
    if profile["above_threshold"] and not profile["sensor_trustworthy"]:
        anomalies.append("every above-threshold reading came from a sensor not flagged OK")
    if profile["degraded_sensor_points"]:
        anomalies.append(f"{profile['degraded_sensor_points']} reading(s) of degraded quality")
    wrong_zone = [r for r in series
                  if shipment["direction"] == "OUTBOUND" and r["gps_zone"] == "DESTINATION"]
    if wrong_zone:
        anomalies.append(f"{len(wrong_zone)} reading(s) report a zone inconsistent with direction")

    escalations = [e for e in est.escalations if e["shipment_id"] == shipment_id]

    return {
        "shipment_id": shipment_id,
        "patient_key": shipment["patient_key"],
        "direction": shipment["direction"],
        "status": shipment["status"],
        "origin": shipment["origin"],
        "destination": shipment["destination"],
        "coi_id": shipment["coi_id"],
        "batch_id": shipment["batch_id"] or None,
        "departed_at": shipment["departed_at"],
        "arrived_at": shipment["arrived_at"],
        "sla": sla,
        "route": route,
        "checkpoints": checkpoints,
        "custody_chain": _custody_chain(est, shipment),
        "telemetry": series,
        "excursion_profile": profile,
        "excursion_decision": decision.as_dict(),
        "anomalies": anomalies,
        "escalations": escalations,
        "authority": "Quality for disposition; Logistics for routing",
    }


def board(estate: Estate | None = None, limit: int = 60, only_issues: bool = False) -> dict:
    """Fleet view. In-transit and problem shipments first."""
    est = estate or load()
    rows = []
    for shipment in est.shipments:
        sla = _sla(est, shipment)
        profile = excursion_profile(est, shipment["shipment_id"])
        flagged = shipment["temp_excursion"].strip().upper() == "TRUE"
        issue = (sla["sla_breach"] or not sla["ordering_valid"] or profile["above_threshold"] > 0
                 or flagged or shipment["status"] != "DELIVERED")
        if only_issues and not issue:
            continue
        rows.append({
            "shipment_id": shipment["shipment_id"],
            "patient_key": shipment["patient_key"],
            "direction": shipment["direction"],
            "status": shipment["status"],
            "courier": sla["courier_name"],
            "origin": shipment["origin"],
            "destination": shipment["destination"],
            "transit_hours": sla["transit_hours"],
            "sla_hours": sla["sla_hours"],
            "sla_breach": sla["sla_breach"],
            "ordering_valid": sla["ordering_valid"],
            "above_threshold": profile["above_threshold"],
            "sensor_trustworthy": profile["sensor_trustworthy"],
            "flagged": flagged,
            "issue": issue,
        })

    rows.sort(key=lambda r: (not r["issue"], r["shipment_id"]))
    total = len(est.shipments)
    return {
        "total": total,
        "shown": len(rows[:limit]),
        "shipments": rows[:limit],
        "summary": {
            "in_transit": sum(1 for s in est.shipments if s["status"] != "DELIVERED"),
            "sla_breaches": sum(1 for r in rows if r["sla_breach"]),
            "with_excursion_readings": sum(1 for r in rows if r["above_threshold"]),
            "impossible_timelines": sum(1 for r in rows if not r["ordering_valid"]),
            "open_escalations": len([e for e in est.escalations if e["status"] != "CLOSED"]),
        },
    }
