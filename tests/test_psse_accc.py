import math
from pathlib import Path

import pytest

from parsers.psse_accc import parse_file, parse_to_dataframe

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
BASE_RPT = str(SAMPLE_DIR / "accc_base.rpt")
POST_RPT = str(SAMPLE_DIR / "accc_postupgrade.rpt")


# ---------------------------------------------------------------------------
# base report row counts
# ---------------------------------------------------------------------------

def test_base_total_count():
    rows = parse_file(BASE_RPT)
    assert len(rows) == 13, f"expected 13 rows, got {len(rows)}"


def test_base_thermal_count():
    rows = parse_file(BASE_RPT)
    thermal = [r for r in rows if r.violation_type == "thermal"]
    assert len(thermal) == 9, f"expected 9 thermal rows, got {len(thermal)}"


def test_base_voltage_count():
    rows = parse_file(BASE_RPT)
    voltage = [r for r in rows if r.violation_type == "voltage"]
    assert len(voltage) == 4, f"expected 4 voltage rows, got {len(voltage)}"


# ---------------------------------------------------------------------------
# worst thermal loading in base report
# ---------------------------------------------------------------------------

def test_worst_thermal_loading():
    rows = parse_file(BASE_RPT)
    thermal = [r for r in rows if r.violation_type == "thermal"]
    worst = max(thermal, key=lambda r: r.loading_pct)
    assert worst.loading_pct == pytest.approx(138.1, abs=0.05)
    assert worst.from_name == "CEDAR 230"
    assert worst.to_name == "BIRCH 230"
    assert worst.contingency_label == "L_MAPLE-CEDAR_230_1"


# ---------------------------------------------------------------------------
# post-upgrade report row counts
# ---------------------------------------------------------------------------

def test_post_total_count():
    rows = parse_file(POST_RPT)
    assert len(rows) == 6, f"expected 6 rows, got {len(rows)}"


def test_post_thermal_count():
    rows = parse_file(POST_RPT)
    thermal = [r for r in rows if r.violation_type == "thermal"]
    assert len(thermal) == 4


def test_post_voltage_count():
    rows = parse_file(POST_RPT)
    voltage = [r for r in rows if r.violation_type == "voltage"]
    assert len(voltage) == 2


# ---------------------------------------------------------------------------
# data quality: no empty labels, no NaN in applicable numeric fields
# ---------------------------------------------------------------------------

def _check_quality(rows):
    for row in rows:
        assert row.contingency_label, f"empty contingency_label: {row}"
        if row.violation_type == "thermal":
            for name, val in [
                ("from_kv", row.from_kv),
                ("to_kv", row.to_kv),
                ("rating", row.rating),
                ("flow", row.flow),
                ("loading_pct", row.loading_pct),
            ]:
                assert val is not None and not math.isnan(val), \
                    f"NaN/None in {name} for thermal row: {row}"
        else:
            for name, val in [
                ("from_kv", row.from_kv),
                ("v_init", row.v_init),
                ("v_cont", row.v_cont),
                ("dev_pct", row.dev_pct),
            ]:
                assert val is not None and not math.isnan(val), \
                    f"NaN/None in {name} for voltage row: {row}"


def test_base_data_quality():
    _check_quality(parse_file(BASE_RPT))


def test_post_data_quality():
    _check_quality(parse_file(POST_RPT))


# ---------------------------------------------------------------------------
# DataFrame helper
# ---------------------------------------------------------------------------

def test_dataframe_shape():
    df = parse_to_dataframe(BASE_RPT)
    assert len(df) == 13
    assert "contingency_label" in df.columns
    assert "loading_pct" in df.columns
    assert "v_init" in df.columns


def test_element_type_inference():
    rows = parse_file(BASE_RPT)
    by_label = {r.contingency_label: r for r in rows
                if r.violation_type == "thermal"}
    # X_MAPLE_500/230_1 monitored element: CEDAR 500 -> CEDAR 230 (different kV)
    xfmr_row = next(r for r in rows
                    if r.violation_type == "thermal"
                    and r.contingency_label == "X_MAPLE_500/230_1")
    assert xfmr_row.element_type == "xfmr"

    # L_MAPLE-CEDAR_230_1 worst row: CEDAR 230 -> BIRCH 230 (same kV)
    branch_row = next(r for r in rows
                      if r.violation_type == "thermal"
                      and r.from_name == "CEDAR 230"
                      and r.to_name == "BIRCH 230")
    assert branch_row.element_type == "branch"

    # all voltage rows are 'bus'
    for r in rows:
        if r.violation_type == "voltage":
            assert r.element_type == "bus"
