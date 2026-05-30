"""Before/after comparison between two parsed ACCC report DataFrames."""
from __future__ import annotations

import pandas as pd

from analytics import add_severity

# Minimum severity delta to classify a change as improved/worsened rather than
# unchanged.  Set relative to the 1-decimal-place precision of the raw metrics.
EPS: float = 0.1

VALID_STATUSES = frozenset({"resolved", "unchanged", "improved", "worsened", "new"})


# ---------------------------------------------------------------------------
# Violation key
# ---------------------------------------------------------------------------

def violation_key(row: pd.Series) -> tuple:
    """Stable, hashable identity for one violation row.

    thermal : (contingency_label, from_bus, to_bus, ckt, 'thermal')
    voltage : (contingency_label, from_bus, 'voltage')
    """
    if row["violation_type"] == "thermal":
        return (
            row["contingency_label"],
            int(row["from_bus"]),
            int(row["to_bus"]),
            row["ckt"],
            "thermal",
        )
    return (
        row["contingency_label"],
        int(row["from_bus"]),
        "voltage",
    )


def _metric(row: pd.Series) -> float:
    """Primary scalar metric for a row (loading_pct or dev_pct)."""
    return float(
        row["loading_pct"] if row["violation_type"] == "thermal" else row["dev_pct"]
    )


def _element_label(row: pd.Series) -> str:
    if row["violation_type"] == "thermal":
        return f"{row['from_name']} → {row['to_name']}"
    return str(row["from_name"])


def _ensure_severity(df: pd.DataFrame) -> pd.DataFrame:
    return df if "severity" in df.columns else add_severity(df)


# ---------------------------------------------------------------------------
# diff_reports
# ---------------------------------------------------------------------------

def diff_reports(base_df: pd.DataFrame, post_df: pd.DataFrame) -> pd.DataFrame:
    """One row per union of violation keys across the two reports.

    Columns
    -------
    contingency_label, element, violation_type,
    from_bus, from_name, to_bus, to_name, ckt,
    base_metric, post_metric,
    base_severity, post_severity,
    status  ∈ {'resolved','unchanged','improved','worsened','new'}
    """
    base_df = _ensure_severity(base_df)
    post_df = _ensure_severity(post_df)

    base_map: dict[tuple, pd.Series] = {
        violation_key(r): r for _, r in base_df.iterrows()
    }
    post_map: dict[tuple, pd.Series] = {
        violation_key(r): r for _, r in post_df.iterrows()
    }

    records = []
    for key in base_map.keys() | post_map.keys():
        b = base_map.get(key)
        p = post_map.get(key)
        rep = b if b is not None else p  # representative row for metadata

        vtype = rep["violation_type"]
        base_metric = _metric(b) if b is not None else None
        post_metric = _metric(p) if p is not None else None
        base_sev = float(b["severity"]) if b is not None else None
        post_sev = float(p["severity"]) if p is not None else None

        if b is not None and p is None:
            status = "resolved"
        elif p is not None and b is None:
            status = "new"
        else:
            delta = post_sev - base_sev  # type: ignore[operator]
            if delta > EPS:
                status = "worsened"
            elif delta < -EPS:
                status = "improved"
            else:
                status = "unchanged"

        records.append(
            {
                "contingency_label": rep["contingency_label"],
                "element": _element_label(rep),
                "violation_type": vtype,
                "from_bus": int(rep["from_bus"]),
                "from_name": rep["from_name"],
                "to_bus": int(rep["to_bus"]) if vtype == "thermal" else None,
                "to_name": rep["to_name"] if vtype == "thermal" else None,
                "ckt": rep["ckt"] if vtype == "thermal" else None,
                "base_metric": base_metric,
                "post_metric": post_metric,
                "base_severity": base_sev,
                "post_severity": post_sev,
                "status": status,
            }
        )

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# diff_summary
# ---------------------------------------------------------------------------

def diff_summary(diff_df: pd.DataFrame) -> dict:
    """Counts per status and headline KPIs.

    Keys: resolved, new, improved, worsened, unchanged,
          n_resolved, n_new, net_change (n_resolved − n_new).
    """
    counts: dict[str, int] = diff_df["status"].value_counts().to_dict()
    for s in VALID_STATUSES:
        counts.setdefault(s, 0)

    n_resolved = counts["resolved"]
    n_new = counts["new"]
    return {
        **counts,
        "n_resolved": n_resolved,
        "n_new": n_new,
        "net_change": n_resolved - n_new,
    }
