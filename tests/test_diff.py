from pathlib import Path

import pytest

from parsers.psse_accc import parse_to_dataframe
from diff import diff_reports, diff_summary, violation_key, VALID_STATUSES

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
BASE_RPT = str(SAMPLE_DIR / "accc_base.rpt")
POST_RPT = str(SAMPLE_DIR / "accc_postupgrade.rpt")


@pytest.fixture(scope="module")
def diff_df():
    base = parse_to_dataframe(BASE_RPT)
    post = parse_to_dataframe(POST_RPT)
    return diff_reports(base, post)


# ---------------------------------------------------------------------------
# Four named status assertions from the spec
# ---------------------------------------------------------------------------

def test_cedar_birch_resolved(diff_df):
    row = diff_df[
        (diff_df["contingency_label"] == "L_MAPLE-CEDAR_230_1")
        & (diff_df["from_bus"] == 50002)
        & (diff_df["to_bus"] == 50003)
    ].iloc[0]
    assert row["status"] == "resolved"
    assert row["base_metric"] == pytest.approx(138.1, abs=0.05)
    assert row["post_metric"] is None or (row["post_metric"] != row["post_metric"])  # None or NaN


def test_oakdale_pine_unchanged(diff_df):
    row = diff_df[
        (diff_df["contingency_label"] == "L_ELM-OAKDALE_115_1")
        & (diff_df["from_bus"] == 60002)
        & (diff_df["to_bus"] == 60003)
    ].iloc[0]
    assert row["status"] == "unchanged"
    assert row["base_metric"] == pytest.approx(108.8, abs=0.05)
    assert row["post_metric"] == pytest.approx(108.8, abs=0.05)


def test_aspen_willow_worsened(diff_df):
    row = diff_df[
        (diff_df["contingency_label"] == "L_BIRCH-ASPEN_230_1")
        & (diff_df["from_bus"] == 50004)
        & (diff_df["to_bus"] == 50005)
    ].iloc[0]
    assert row["status"] == "worsened"
    assert row["base_metric"] == pytest.approx(105.2, abs=0.05)
    assert row["post_metric"] == pytest.approx(114.6, abs=0.05)
    assert row["post_severity"] > row["base_severity"]


def test_aspen_willow_new_under_maple500(diff_df):
    row = diff_df[
        (diff_df["contingency_label"] == "X_MAPLE_500/230_1")
        & (diff_df["from_bus"] == 50004)
        & (diff_df["to_bus"] == 50005)
    ].iloc[0]
    assert row["status"] == "new"
    assert row["base_metric"] is None or (row["base_metric"] != row["base_metric"])


def test_every_status_is_valid(diff_df):
    assert set(diff_df["status"].unique()) <= VALID_STATUSES


def test_all_five_statuses_present(diff_df):
    assert set(diff_df["status"].unique()) == VALID_STATUSES


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

def test_diff_total_rows(diff_df):
    assert len(diff_df) == 15  # 9 resolved + 2 new + 2 improved + 1 worsened + 1 unchanged


def test_diff_summary_counts(diff_df):
    s = diff_summary(diff_df)
    assert s["resolved"] == 9
    assert s["new"] == 2
    assert s["improved"] == 2
    assert s["worsened"] == 1
    assert s["unchanged"] == 1
    assert s["n_resolved"] == 9
    assert s["n_new"] == 2
    assert s["net_change"] == 7  # 9 resolved - 2 new


def test_resolved_rows_have_no_post_values(diff_df):
    resolved = diff_df[diff_df["status"] == "resolved"]
    assert resolved["post_metric"].isna().all()
    assert resolved["post_severity"].isna().all()
    assert resolved["base_metric"].notna().all()


def test_new_rows_have_no_base_values(diff_df):
    new = diff_df[diff_df["status"] == "new"]
    assert new["base_metric"].isna().all()
    assert new["base_severity"].isna().all()
    assert new["post_metric"].notna().all()


def test_voltage_rows_have_null_to_bus(diff_df):
    voltage = diff_df[diff_df["violation_type"] == "voltage"]
    assert voltage["to_bus"].isna().all()
    assert voltage["ckt"].isna().all()


# ---------------------------------------------------------------------------
# violation_key helper
# ---------------------------------------------------------------------------

def test_violation_key_thermal():
    base = parse_to_dataframe(BASE_RPT)
    thermal_row = base[base["violation_type"] == "thermal"].iloc[0]
    k = violation_key(thermal_row)
    assert len(k) == 5
    assert k[-1] == "thermal"
    assert isinstance(k[1], int)  # from_bus
    assert isinstance(k[2], int)  # to_bus


def test_violation_key_voltage():
    base = parse_to_dataframe(BASE_RPT)
    voltage_row = base[base["violation_type"] == "voltage"].iloc[0]
    k = violation_key(voltage_row)
    assert len(k) == 3
    assert k[-1] == "voltage"


def test_violation_key_is_hashable():
    base = parse_to_dataframe(BASE_RPT)
    keys = {violation_key(r) for _, r in base.iterrows()}
    assert len(keys) == len(base)  # all 13 base rows are distinct


# ---------------------------------------------------------------------------
# add_severity passthrough: diff_reports accepts pre-scored DataFrames
# ---------------------------------------------------------------------------

def test_diff_accepts_pre_scored_input():
    from analytics import add_severity
    base = add_severity(parse_to_dataframe(BASE_RPT))
    post = add_severity(parse_to_dataframe(POST_RPT))
    df = diff_reports(base, post)
    assert len(df) == 15
