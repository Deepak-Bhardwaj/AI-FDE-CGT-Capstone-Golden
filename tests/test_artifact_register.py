import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/21_STAGE_ARTIFACT_REGISTER.csv"

PDF_STATUS_COUNTS = {
    "PRESENT_INTERNAL": 88,
    "PARTIAL": 72,
    "CONDITIONAL_NOT_SELECTED": 16,
    "EXTERNAL_REQUIRED": 9,
}
MERGED_COMPONENT_STATUS = {"COMPLETED", "VERIFIED"}
CORE_MARKERS = ("-M", "-N")


def _load_rows() -> list[dict[str, str]]:
    with REGISTER.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _is_core_pdf_row(row: dict[str, str]) -> bool:
    artifact_id = row["artifact_id"]
    return all(marker not in artifact_id for marker in CORE_MARKERS)


def test_each_pdf_essential_artifact_has_a_unique_canonical_row_and_valid_path():
    rows = _load_rows()
    core = [row for row in rows if _is_core_pdf_row(row)]
    assert len(core) == 185
    assert len({row["artifact_id"] for row in rows}) == len(rows)
    assert {row["stage"] for row in rows} == {f"{stage:02}" for stage in range(1, 22)}
    assert Counter(row["status"] for row in core) == PDF_STATUS_COUNTS
    assert Counter(row["status"] for row in rows) == {
        **PDF_STATUS_COUNTS,
        "COMPLETED": 45,
        "VERIFIED": 63,
    }
    assert len(rows) == 293
    for row in rows:
        path = row["canonical_path"]
        if path == "-":
            assert row["status"] in {"MISSING", "EXTERNAL_REQUIRED", "CONDITIONAL_NOT_SELECTED"}
        else:
            assert (ROOT / path).is_file(), row["artifact_id"]
        assert row["accountable_role"] and row["exit_evidence"]


def test_prd_is_identified_as_a_training_extra_not_a_pdf_essential_artifact():
    rows = _load_rows()
    extras = [row for row in rows if "-X" in row["artifact_id"]]
    assert len(extras) == 1
    assert extras[0]["artifact_id"] == "S13-X01"
    assert "PRODUCT_REQUIREMENTS_DOCUMENT" in extras[0]["canonical_path"]


def test_every_stage_lists_merged_intelligence_reconciliation_webapp_and_governance():
    rows = {row["artifact_id"]: row for row in _load_rows()}
    expected = {
        "M01": ("intelligence", "VERIFIED"),
        "M02": ("reconcil", "VERIFIED"),
        "M03": ("webapp", "COMPLETED"),
        "M04": ("governance", "VERIFIED"),
    }
    for stage in range(1, 22):
        prefix = f"S{stage:02}-"
        for suffix, (token, status) in expected.items():
            row = rows[f"{prefix}{suffix}"]
            assert row["status"] == status
            assert row["status"] in MERGED_COMPONENT_STATUS
            assert token in row["pdf_essential_artifact"].lower()
            assert (ROOT / row["canonical_path"]).is_file()
