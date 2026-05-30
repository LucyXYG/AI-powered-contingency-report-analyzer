"""Parser for PSS/E AC Contingency Calculation (ACCC) fixed-width text reports."""
from __future__ import annotations

import pandas as pd

from schema import ViolationRow, to_dataframe

# ---------------------------------------------------------------------------
# Thermal row column slices (derived from gen_accc.py mon_field + thermal_line)
# ---------------------------------------------------------------------------
# mon_field produces 61 chars; thermal_line pads it to 63 with :<63.63s
T_FROM_BUS  = slice(0,   6)    # f"{bus:>6d}"          right-just 6-char int
T_FROM_NAME = slice(6,  23)    # f"{name:<17.17s}"     left-just  17-char str
T_FROM_KV   = slice(23, 29)    # f"{kv:>6.1f}"         right-just 6-char float
T_TO_BUS    = slice(29, 36)    # f"{bus:>7d}"          right-just 7-char int
T_TO_NAME   = slice(36, 53)    # f"{name:<17.17s}"     left-just  17-char str
T_TO_KV     = slice(53, 59)    # f"{kv:>6.1f}"         right-just 6-char float
T_CKT       = slice(59, 61)    # f"{ckt:>2.2s}"        right-just 2-char str
# positions 61-62 are padding spaces from :<63.63s
T_CON_LABEL = slice(63, 87)    # f"{label:<24.24s}"    left-just  24-char str
T_RATING    = slice(87, 95)    # f"{rating:>8.1f}"     right-just 8-char float
T_FLOW      = slice(95, 105)   # f"{flow:>10.1f}"      right-just 10-char float
T_LOADING   = slice(105, 114)  # f"{loading:>9.1f}"    right-just 9-char float

# ---------------------------------------------------------------------------
# Voltage row column slices (derived from gen_accc.py voltage_line)
# ---------------------------------------------------------------------------
# f"{bus:>6d} {name:<17.17s}{kv:>6.1f}  {label:<24.24s}{v_init:>9.4f}..."
V_BUS       = slice(0,   6)    # right-just 6-char int
# position 6 is a literal space in the format string
V_BUS_NAME  = slice(7,  24)    # left-just  17-char str
V_BUS_KV    = slice(24, 30)    # right-just 6-char float
# positions 30-31 are 2 literal spaces
V_CON_LABEL = slice(32, 56)    # left-just  24-char str
V_INIT      = slice(56, 65)    # right-just 9-char float (4 dec)
V_CONT      = slice(65, 74)    # right-just 9-char float (4 dec)
V_DEV       = slice(74, 83)    # right-just 9-char float (2 dec)

_THERMAL_HEADER = "MONITORED BRANCH OVERLOADS (THERMAL)"
_VOLTAGE_HEADER = "MONITORED BUS VOLTAGE VIOLATIONS"


def parse_file(path: str) -> list[ViolationRow]:
    rows: list[ViolationRow] = []
    section: str | None = None  # 'thermal' | 'voltage'

    with open(path) as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()

            # section transitions
            if _THERMAL_HEADER in stripped:
                section = "thermal"
                continue
            if _VOLTAGE_HEADER in stripped:
                section = "voltage"
                continue

            # skip lines before any section, blanks, separators, headers, CONTINGENCY labels
            if not section or not stripped:
                continue
            if (stripped.startswith("CONTINGENCY:")
                    or stripped[0] in ("-", "=")
                    or stripped.startswith("FROM")
                    or stripped.startswith("BUS")
                    or stripped.startswith("END")):
                continue

            # data rows: leading space then a digit (bus number)
            if len(line) < 2 or line[0] != " " or not line[1].isdigit():
                continue

            if section == "thermal":
                rows.append(_parse_thermal(line))
            else:
                rows.append(_parse_voltage(line))

    return rows


def _parse_thermal(line: str) -> ViolationRow:
    from_kv = float(line[T_FROM_KV])
    to_kv = float(line[T_TO_KV])
    return ViolationRow(
        contingency_label=line[T_CON_LABEL].strip(),
        violation_type="thermal",
        element_type="xfmr" if from_kv != to_kv else "branch",
        from_bus=int(line[T_FROM_BUS]),
        from_name=line[T_FROM_NAME].strip(),
        from_kv=from_kv,
        to_bus=int(line[T_TO_BUS]),
        to_name=line[T_TO_NAME].strip(),
        to_kv=to_kv,
        ckt=line[T_CKT].strip(),
        rating=float(line[T_RATING]),
        flow=float(line[T_FLOW]),
        loading_pct=float(line[T_LOADING]),
        v_init=None,
        v_cont=None,
        dev_pct=None,
    )


def _parse_voltage(line: str) -> ViolationRow:
    return ViolationRow(
        contingency_label=line[V_CON_LABEL].strip(),
        violation_type="voltage",
        element_type="bus",
        from_bus=int(line[V_BUS]),
        from_name=line[V_BUS_NAME].strip(),
        from_kv=float(line[V_BUS_KV]),
        to_bus=None,
        to_name=None,
        to_kv=None,
        ckt=None,
        rating=None,
        flow=None,
        loading_pct=None,
        v_init=float(line[V_INIT]),
        v_cont=float(line[V_CONT]),
        dev_pct=float(line[V_DEV]),
    )


def parse_to_dataframe(path: str) -> pd.DataFrame:
    return to_dataframe(parse_file(path))
