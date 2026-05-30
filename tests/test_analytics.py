from pathlib import Path

import pytest

from parsers.psse_accc import parse_to_dataframe
from analytics import (
    add_severity,
    critical_contingencies,
    severity_score,
    summary,
    vulnerable_elements,
)

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
BASE_RPT = str(SAMPLE_DIR / "accc_base.rpt")


@pytest.fixture(scope="module")
def base_df():
    return parse_to_dataframe(BASE_RPT)


@pytest.fixture(scope="module")
def scored_df(base_df):
    return add_severity(base_df)


# ---------------------------------------------------------------------------
# severity_score
# ---------------------------------------------------------------------------

def test_severity_thermal_formula(base_df):
    # worst thermal: 138.1 % loading at 230 kV → (138.1−100)×1.2 = 45.72
    worst = base_df.loc[base_df["loading_pct"].idxmax()]
    score = severity_score(worst)
    assert score == pytest.approx(38.1 * 1.2, abs=0.05)


def test_severity_voltage_formula(base_df):
    # PINE 115 under X_BIRCH-ELMHURST_1: dev_pct=−3.29, kv=115 → 3.29×1.0
    row = base_df[
        (base_df["violation_type"] == "voltage") & (base_df["dev_pct"] == -3.29)
    ].iloc[0]
    assert severity_score(row) == pytest.approx(3.29, abs=0.01)


def test_add_severity_column_present(scored_df):
    assert "severity" in scored_df.columns
    assert len(scored_df) == 13


def test_add_severity_does_not_mutate(base_df):
    assert "severity" not in base_df.columns


def test_severity_all_positive(scored_df):
    assert (scored_df["severity"] >= 0).all()


# ---------------------------------------------------------------------------
# critical_contingencies
# ---------------------------------------------------------------------------

def test_highest_violation_count(scored_df):
    cc = critical_contingencies(scored_df, sort_by="violation_count")
    row = cc[cc["contingency_label"] == "X_BIRCH-ELMHURST_1"].iloc[0]
    assert row["violation_count"] == 4
    # it should be the global maximum
    assert row["violation_count"] == cc["violation_count"].max()


def test_worst_loading_pct_contingency(scored_df):
    cc = critical_contingencies(scored_df)
    maple_row = cc[cc["contingency_label"] == "L_MAPLE-CEDAR_230_1"].iloc[0]
    assert maple_row["worst_loading_pct"] == pytest.approx(138.1, abs=0.05)
    assert maple_row["worst_loading_pct"] == cc["worst_loading_pct"].max()


def test_critical_contingencies_row_count(scored_df):
    cc = critical_contingencies(scored_df)
    assert len(cc) == 6  # 6 distinct contingencies in base report


def test_critical_contingencies_sort_by_count(scored_df):
    cc = critical_contingencies(scored_df, sort_by="violation_count")
    counts = cc["violation_count"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_critical_contingencies_sort_by_total_severity(scored_df):
    cc = critical_contingencies(scored_df, sort_by="total_severity")
    vals = cc["total_severity"].tolist()
    assert vals == sorted(vals, reverse=True)


def test_critical_contingencies_invalid_sort():
    df = parse_to_dataframe(BASE_RPT)
    with pytest.raises(ValueError):
        critical_contingencies(df, sort_by="banana")


# ---------------------------------------------------------------------------
# vulnerable_elements
# ---------------------------------------------------------------------------

def test_top_vulnerable_element_is_oakdale_pine(scored_df):
    ve = vulnerable_elements(scored_df)
    top = ve.iloc[0]
    assert top["from_bus"] == 60002    # OAKDALE115
    assert top["to_bus"] == 60003     # PINE  115
    assert top["n_contingencies"] == 2
    assert top["element_type"] == "branch"


def test_vulnerable_elements_sorted_by_n_contingencies(scored_df):
    ve = vulnerable_elements(scored_df)
    counts = ve["n_contingencies"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_vulnerable_elements_count(scored_df):
    ve = vulnerable_elements(scored_df)
    # 8 unique thermal elements (OAKDALE→PINE counted once despite 2 contingencies)
    # + 3 distinct voltage buses (PINE, OAKDALE, WILLOW) = 11
    assert len(ve) == 11


def test_voltage_elements_have_no_to_bus(scored_df):
    ve = vulnerable_elements(scored_df)
    bus_rows = ve[ve["element_type"] == "bus"]
    assert bus_rows["to_bus"].isna().all()
    assert bus_rows["ckt"].isna().all()


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def test_summary_total_violations(base_df):
    s = summary(base_df)
    assert s["total_violations"] == 13


def test_summary_thermal_voltage_counts(base_df):
    s = summary(base_df)
    assert s["thermal_count"] == 9
    assert s["voltage_count"] == 4
    assert s["thermal_count"] + s["voltage_count"] == s["total_violations"]


def test_summary_worst_loading(base_df):
    s = summary(base_df)
    assert s["worst_loading_pct"] == pytest.approx(138.1, abs=0.05)


def test_summary_worst_voltage_dev(base_df):
    s = summary(base_df)
    # most severe undervoltage in base report is −3.29 %
    assert s["worst_voltage_dev_pct"] == pytest.approx(-3.29, abs=0.01)


def test_summary_worst_voltage_dev_magnitude_beats_sign(base_df):
    # Splice in a synthetic overvoltage row (+2.0 %) alongside the real
    # undervoltage rows (worst real = −3.29 %).  The −3.29 has larger absolute
    # magnitude, so it must still win.
    import pandas as pd

    overvoltage_row = base_df.iloc[0].copy()
    overvoltage_row["violation_type"] = "voltage"
    overvoltage_row["dev_pct"] = 2.0   # positive: overvoltage
    overvoltage_row["v_init"] = 1.01
    overvoltage_row["v_cont"] = 1.07
    overvoltage_row["loading_pct"] = None

    mixed_df = pd.concat([base_df, overvoltage_row.to_frame().T], ignore_index=True)
    s = summary(mixed_df)
    assert s["worst_voltage_dev_pct"] == pytest.approx(-3.29, abs=0.01)


def test_summary_n_contingencies(base_df):
    s = summary(base_df)
    assert s["n_contingencies"] == 6
