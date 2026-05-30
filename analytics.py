"""Scoring and ranking analytics for ACCC violation DataFrames."""
from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Tunable weight constants
# ---------------------------------------------------------------------------

# Thermal base score: percentage points above 100 % of rating
# Voltage base score: absolute deviation percent from the limit band

# Maps nominal kV (as integer) to a multiplier; higher voltage → higher weight
KV_WEIGHT: dict[int, float] = {
    500: 1.5,
    230: 1.2,
    115: 1.0,
}
KV_WEIGHT_DEFAULT = 1.0  # fallback for voltages not in the table


def _kv_weight(kv: float) -> float:
    return KV_WEIGHT.get(round(kv), KV_WEIGHT_DEFAULT)


# ---------------------------------------------------------------------------
# Row-level scoring
# ---------------------------------------------------------------------------

def severity_score(row: pd.Series) -> float:
    """Severity score for one violation row.

    thermal : max(0, loading_pct − 100) × kV_weight
    voltage : abs(dev_pct)              × kV_weight
    """
    if row["violation_type"] == "thermal":
        base = max(0.0, float(row["loading_pct"]) - 100.0)
    else:
        base = abs(float(row["dev_pct"]))
    return base * _kv_weight(float(row["from_kv"]))


def add_severity(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with a 'severity' column appended."""
    out = df.copy()
    out["severity"] = out.apply(severity_score, axis=1)
    return out


def _ensure_severity(df: pd.DataFrame) -> pd.DataFrame:
    return df if "severity" in df.columns else add_severity(df)


# ---------------------------------------------------------------------------
# Contingency-level aggregation
# ---------------------------------------------------------------------------

def critical_contingencies(
    df: pd.DataFrame,
    sort_by: str = "max_severity",
) -> pd.DataFrame:
    """One row per contingency with aggregated statistics.

    Columns: contingency_label, violation_count, max_severity,
             total_severity, worst_loading_pct.

    sort_by: 'max_severity' | 'total_severity' | 'violation_count'
             These can produce different rankings — that is intentional.
    """
    valid = {"max_severity", "total_severity", "violation_count"}
    if sort_by not in valid:
        raise ValueError(f"sort_by must be one of {valid!r}")

    df = _ensure_severity(df)
    grp = df.groupby("contingency_label")

    result = pd.DataFrame(
        {
            "violation_count": grp.size(),
            "max_severity": grp["severity"].max(),
            "total_severity": grp["severity"].sum(),
            # NaN when a contingency has only voltage violations
            "worst_loading_pct": grp["loading_pct"].max(),
        }
    ).reset_index()

    return result.sort_values(sort_by, ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Element-level aggregation
# ---------------------------------------------------------------------------

def vulnerable_elements(df: pd.DataFrame) -> pd.DataFrame:
    """One row per monitored element with multi-contingency exposure stats.

    Element key
    -----------
    branch / xfmr : (from_bus, to_bus, ckt)
    voltage bus   : (from_bus)  — to_bus / ckt are None

    Columns: from_bus, from_name, to_bus, to_name, ckt, element_type,
             n_contingencies, max_severity, max_loading_pct.
    Sorted by n_contingencies desc, then max_severity desc.
    """
    df = _ensure_severity(df)

    # Sentinel-fill so groupby works uniformly across both row types
    tmp = df.copy()
    tmp["_to_bus"] = tmp["to_bus"].fillna(-1).astype(int)
    tmp["_ckt"] = tmp["ckt"].fillna("")

    records = []
    for (from_bus, to_bus_sentinel, ckt_sentinel), grp in tmp.groupby(
        ["from_bus", "_to_bus", "_ckt"], sort=False
    ):
        first = grp.iloc[0]
        records.append(
            {
                "from_bus": int(from_bus),
                "from_name": first["from_name"],
                "to_bus": None if to_bus_sentinel == -1 else int(to_bus_sentinel),
                "to_name": first["to_name"],
                "ckt": ckt_sentinel if ckt_sentinel else None,
                "element_type": first["element_type"],
                "n_contingencies": int(grp["contingency_label"].nunique()),
                "max_severity": grp["severity"].max(),
                # NaN for voltage-only elements
                "max_loading_pct": grp["loading_pct"].max(),
            }
        )

    return (
        pd.DataFrame(records)
        .sort_values(["n_contingencies", "max_severity"], ascending=False)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Summary KPIs
# ---------------------------------------------------------------------------

def summary(df: pd.DataFrame) -> dict:
    """KPI card values for the entire report DataFrame."""
    thermal = df[df["violation_type"] == "thermal"]
    voltage = df[df["violation_type"] == "voltage"]

    if len(voltage):
        # return the actual dev_pct value with the largest absolute magnitude
        idx = voltage["dev_pct"].abs().idxmax()
        worst_vdev = float(voltage.loc[idx, "dev_pct"])
    else:
        worst_vdev = None

    return {
        "total_violations": len(df),
        "thermal_count": len(thermal),
        "voltage_count": len(voltage),
        "worst_loading_pct": float(thermal["loading_pct"].max()) if len(thermal) else None,
        "worst_voltage_dev_pct": worst_vdev,
        "n_contingencies": int(df["contingency_label"].nunique()),
    }
