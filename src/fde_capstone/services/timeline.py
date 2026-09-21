"""Journey timing: what actually happened, what the cohort usually takes, and what is likely next.

The plan is not invented. Expected durations are the cohort's own observed transition times
between recorded milestones, so every number can be traced to the events that produced it.
Forecasts are intervals with an explicit basis and are advisory only: they are never a promise
to a patient and never a scheduling instruction for conditioning chemotherapy.
"""
from __future__ import annotations

import statistics
from datetime import timedelta

from .loader import Estate, load, parse_time

MODEL = {"name": "journey-transition-quantiles", "version": "1.0",
         "method": "empirical p10/p50/p90 of observed milestone transitions in this estate"}

# The milestones every source system timestamps, in the order they occur in this estate.
MILESTONES = [
    ("S01", "PATIENT_ENROLLED", "Enrolled"),
    ("S06", "COLLECTION_COMPLETED", "Cells collected"),
    ("S08", "SHIPMENT_DISPATCHED", "Shipped to the manufacturing site"),
    ("S08R", "SHIPMENT_RECEIVED", "Arrived at the manufacturing site"),
    ("S10", "MANUFACTURING_STARTED", "Manufacturing started"),
    ("S11", "MANUFACTURING_COMPLETED", "Manufacturing finished"),
    ("S13", "RETURN_SHIPMENT_DISPATCHED", "Shipped back to the treatment centre"),
    ("S13A", "RETURN_SHIPMENT_ARRIVED", "Arrived at the treatment centre"),
]


def _transition_samples(est: Estate) -> dict[str, list[float]]:
    """Hours between each pair of consecutive milestones, across every journey in the estate."""
    samples: dict[str, list[float]] = {}
    for patient in est.patients:
        times = {e["event_type"]: parse_time(e["occurred_at"])
                 for e in est.events_by_key.get(patient["patient_key"], [])}
        for (_, previous, _), (_, nxt, _) in zip(MILESTONES, MILESTONES[1:]):
            start, end = times.get(previous), times.get(nxt)
            if start and end and end >= start:
                samples.setdefault(f"{previous}->{nxt}", []).append(
                    (end - start).total_seconds() / 3600)
    return samples


def _quantiles(values: list[float]) -> dict | None:
    if len(values) < 10:
        return None
    deciles = statistics.quantiles(values, n=10)
    return {"p10_h": round(deciles[0], 1),
            "p50_h": round(statistics.median(values), 1),
            "p90_h": round(deciles[-1], 1),
            "n": len(values)}


def cohort_plan(estate: Estate | None = None) -> dict[str, dict]:
    """Observed transition times, keyed by the milestone the step ends at."""
    est = estate or load()
    samples = _transition_samples(est)
    plan: dict[str, dict] = {}
    for (_, previous, _), (stage_id, nxt, label) in zip(MILESTONES, MILESTONES[1:]):
        q = _quantiles(samples.get(f"{previous}->{nxt}", []))
        if q:
            plan[stage_id] = {"from": previous, "to": nxt, "label": label, **q}
    return plan


def _hours(start, end) -> float | None:
    return round((end - start).total_seconds() / 3600, 1) if start and end else None


def qc_latency(estate: Estate | None = None) -> dict | None:
    """How long the laboratory takes to report, used to estimate the QA release step."""
    est = estate or load()
    lags = []
    for row in est.qc:
        sampled, reported = parse_time(row["sampled_at"]), parse_time(row["reported_at"])
        if sampled and reported and reported >= sampled:
            lags.append((reported - sampled).total_seconds() / 3600)
    return _quantiles(lags)


def forecast(patient_key: str, estate: Estate | None = None) -> dict:
    """Actual timings for what has happened, interval estimates for what has not."""
    est = estate or load()
    plan = cohort_plan(est)
    times = {e["event_type"]: parse_time(e["occurred_at"])
             for e in est.events_by_key.get(patient_key, [])}

    enrolled = times.get("PATIENT_ENROLLED")
    steps: list[dict] = []
    cursor = enrolled                      # last point in time we actually know
    cursor_is_actual = True
    earliest = latest = cursor

    for stage_id, event, label in MILESTONES:
        expected = plan.get(stage_id)
        actual = times.get(event)
        step = {
            "stage_id": stage_id, "event": event, "label": label,
            "expected_hours": expected["p50_h"] if expected else None,
            "expected_basis": (f"median of {expected['n']} comparable journeys"
                               if expected else "no comparable journeys recorded"),
            "actual_at": actual.isoformat() if actual else None,
            "elapsed_from_enrolment_h": _hours(enrolled, actual) if actual else None,
            "variance_hours": None,
            "predicted": None,
        }

        if actual:
            if expected and cursor:
                observed = _hours(cursor, actual)
                if observed is not None:
                    step["variance_hours"] = round(observed - expected["p50_h"], 1)
            cursor, cursor_is_actual = actual, True
            earliest = latest = actual
        elif expected and cursor:
            earliest = (earliest or cursor) + timedelta(hours=expected["p10_h"])
            expect = cursor + timedelta(hours=expected["p50_h"])
            latest = (latest or cursor) + timedelta(hours=expected["p90_h"])
            step["predicted"] = {
                "earliest": earliest.isoformat(),
                "expected": expect.isoformat(),
                "latest": latest.isoformat(),
                "anchored_on": "recorded event" if cursor_is_actual else "previous estimate",
            }
            cursor, cursor_is_actual = expect, False
        steps.append(step)

    # QA release has no event anywhere in this estate, so it is estimated from how long the
    # laboratory takes to report, anchored on the end of manufacturing.
    lab = qc_latency(est)
    release_anchor = times.get("MANUFACTURING_COMPLETED") or cursor
    released = _release_state(patient_key, est) == "RELEASED"
    release_step = {
        "stage_id": "S12", "event": "QA_RELEASE", "label": "Released by Quality",
        "expected_hours": lab["p50_h"] if lab else None,
        "expected_basis": (f"median laboratory reporting time over {lab['n']} results"
                           if lab else "no laboratory results to measure"),
        "actual_at": None, "elapsed_from_enrolment_h": None,
        "variance_hours": None, "predicted": None,
        "released": released,
        "note": ("The QMS records this batch as released; its export carries no release timestamp."
                 if released else ""),
    }
    if not released and lab and release_anchor:
        release_step["predicted"] = {
            "earliest": (release_anchor + timedelta(hours=lab["p10_h"])).isoformat(),
            "expected": (release_anchor + timedelta(hours=lab["p50_h"])).isoformat(),
            "latest": (release_anchor + timedelta(hours=lab["p90_h"])).isoformat(),
            "anchored_on": "recorded event" if times.get("MANUFACTURING_COMPLETED")
            else "previous estimate",
        }
    steps.append(release_step)

    steps.append({
        "stage_id": "S15", "event": "INFUSED", "label": "Infusion",
        "expected_hours": None,
        "expected_basis": ("no journey in this estate has reached infusion, so there is nothing "
                           "to measure"),
        "actual_at": None, "elapsed_from_enrolment_h": None,
        "variance_hours": None, "predicted": None,
        "note": ("The treating clinician sets this date once Quality has released the product "
                 "and the patient is clinically fit. It is never estimated here."),
    })

    remaining = [s for s in steps if s["predicted"]]
    return {
        "patient_key": patient_key,
        "model": MODEL,
        "enrolled_at": enrolled.isoformat() if enrolled else None,
        "steps": steps,
        "completed_milestones": sum(1 for s in steps if s["actual_at"]),
        "total_milestones": len(steps),
        "predicted_completion": release_step["predicted"],
        "predicted_completion_label": "Released by Quality",
        "already_complete": bool(released),
        "confidence": 0.55 if remaining and remaining[0]["predicted"]["anchored_on"]
        == "recorded event" else 0.35,
    }


def _release_state(patient_key: str, est: Estate) -> str:
    batches = est.batches_by_key.get(patient_key, [])
    return batches[0]["qms_release_status"] if batches else "NO_BATCH"


def project_new(start, estate: Estate | None = None) -> dict:
    """The journey a patient enrolling on a given date would be expected to have.

    Nothing patient-specific is known yet, so this is purely the cohort's own history rolled
    forward from the chosen date. It is a planning aid, not a schedule and not a commitment.
    """
    est = estate or load()
    plan = cohort_plan(est)
    lab = qc_latency(est)

    earliest = expected = latest = start
    steps = [{
        "stage_id": "S01", "label": "Enrolled", "typical_hours": 0,
        "basis": "the date you are planning from",
        "earliest": start.isoformat(), "expected": start.isoformat(), "latest": start.isoformat(),
        "days_from_start": {"earliest": 0.0, "expected": 0.0, "latest": 0.0},
    }]

    def add(stage_id: str, label: str, q: dict | None, basis: str) -> None:
        nonlocal earliest, expected, latest
        if not q:
            steps.append({"stage_id": stage_id, "label": label, "typical_hours": None,
                          "basis": basis, "earliest": None, "expected": None, "latest": None,
                          "days_from_start": None})
            return
        earliest += timedelta(hours=q["p10_h"])
        expected += timedelta(hours=q["p50_h"])
        latest += timedelta(hours=q["p90_h"])
        steps.append({
            "stage_id": stage_id, "label": label, "typical_hours": q["p50_h"], "basis": basis,
            "earliest": earliest.isoformat(), "expected": expected.isoformat(),
            "latest": latest.isoformat(),
            "days_from_start": {
                "earliest": round((earliest - start).total_seconds() / 86400, 1),
                "expected": round((expected - start).total_seconds() / 86400, 1),
                "latest": round((latest - start).total_seconds() / 86400, 1)},
        })

    for stage_id, _, label in MILESTONES[1:]:
        q = plan.get(stage_id)
        add(stage_id, label, q, f"median of {q['n']} comparable journeys" if q
            else "no comparable journeys recorded")
    add("S12", "Released by Quality", lab,
        f"median laboratory reporting time over {lab['n']} results" if lab
        else "no laboratory results to measure")

    steps.append({
        "stage_id": "S15", "label": "Infusion", "typical_hours": None,
        "basis": "set by the treating clinician after release; never estimated here",
        "earliest": None, "expected": None, "latest": None, "days_from_start": None,
    })

    return {
        "start": start.isoformat(),
        "model": MODEL,
        "steps": steps,
        "ready_window": {"earliest": earliest.isoformat(), "expected": expected.isoformat(),
                         "latest": latest.isoformat()},
        "expected_total_days": round((expected - start).total_seconds() / 86400, 1),
    }
