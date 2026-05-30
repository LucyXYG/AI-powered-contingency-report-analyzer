"""
Synthetic PSS/E ACCC report generator.
Mimics the fixed-width text export of an AC Contingency Calculation (ACCC)
single-run report: a thermal (monitored-element overload) section and a
voltage-violation section, both grouped by contingency label.

Column layout follows the slicing used by engineers parsing real .acc text
exports (from-bus/name/kV, to-bus/name/kV, ckt | contingency | rating | flow | %).
Two reports are produced:
  - accc_base.rpt        : pre-upgrade network
  - accc_postupgrade.rpt : same study with a 230 kV reconductor + new xfmr,
                           so the diff has resolved / unchanged / new cases.
"""
import random, datetime

random.seed(7)  # deterministic so the demo is repeatable

# ---- a tiny fictional network -------------------------------------------------
BUSES = {
    50001: ("MAPLE 230", 230.0), 50002: ("CEDAR 230", 230.0),
    50003: ("BIRCH 230", 230.0), 50004: ("ASPEN 230", 230.0),
    50005: ("WILLOW230", 230.0), 50010: ("MAPLE 500", 500.0),
    50011: ("CEDAR 500", 500.0), 60001: ("ELMHURST115", 115.0),
    60002: ("OAKDALE115", 115.0), 60003: ("PINE  115", 115.0),
}

# branches: (frm, to, ckt, rating_MVA)
BRANCHES = [
    (50001, 50002, "1", 478.0), (50002, 50003, "1", 478.0),
    (50003, 50004, "1", 717.0), (50004, 50005, "1", 478.0),
    (50001, 50005, "1", 478.0), (50010, 50001, "1", 1200.0),  # 500/230 xfmr
    (50011, 50002, "1", 1200.0), (60001, 60002, "1", 239.0),
    (60002, 60003, "1", 159.0), (50003, 60001, "1", 358.0),   # 230/115 xfmr
]
BR = {(f, t, c): r for (f, t, c, r) in BRANCHES}

# contingencies (single-element N-1 outages)
CONTINGENCIES = [
    ("L_MAPLE-CEDAR_230_1",   50001, 50002, "1"),
    ("L_CEDAR-BIRCH_230_1",   50002, 50003, "1"),
    ("L_BIRCH-ASPEN_230_1",   50003, 50004, "1"),
    ("X_MAPLE_500/230_1",     50010, 50001, "1"),
    ("X_BIRCH-ELMHURST_1",    50003, 60001, "1"),
    ("L_ELM-OAKDALE_115_1",   60001, 60002, "1"),
]

def busname(n):  return BUSES[n][0]
def buskv(n):    return BUSES[n][1]

# ---- fixed-width field writers (match real .acc column slicing) ---------------
def mon_field(frm, to, ckt):
    # 59-char monitored-element block + 2-char ckt, total ~63
    s  = f"{frm:>6d}"                 # [0:6]   from bus num
    s += f"{busname(frm):<17.17s}"    # [6:23]  from bus name
    s += f"{buskv(frm):>6.1f}"        # [23:29] from kV
    s += f"{to:>7d}"                  # [29:36] to bus num
    s += f"{busname(to):<17.17s}"     # [36:53] to bus name
    s += f"{buskv(to):>6.1f}"         # [53:59] to kV
    s += f"{ckt:>2.2s}"               # [59:61] circuit id
    return s

def thermal_line(frm, to, ckt, con_label, rating, flow_mva):
    loading = 100.0 * flow_mva / rating
    mon = mon_field(frm, to, ckt)
    return (f"{mon:<63.63s}"
            f"{con_label:<24.24s}"
            f"{rating:>8.1f}"
            f"{flow_mva:>10.1f}"
            f"{loading:>9.1f}")

def voltage_line(bus, con_label, v_init, v_cont, lo=0.95, hi=1.05):
    # percent here = deviation from the violated limit
    limit = lo if v_cont < lo else hi
    dev = 100.0 * (v_cont - limit) / limit
    return (f"{bus:>6d} {busname(bus):<17.17s}{buskv(bus):>6.1f}  "
            f"{con_label:<24.24s}"
            f"{v_init:>9.4f}{v_cont:>9.4f}{dev:>9.2f}")

# ---- the actual violation sets -----------------------------------------------
# Each tuple: (con_label, frm, to, ckt, flow_MVA)  -> thermal overloads
def base_thermal():
    return [
        ("L_MAPLE-CEDAR_230_1", 50002, 50003, "1", 660.0),   # 138.1%
        ("L_MAPLE-CEDAR_230_1", 50001, 50005, "1", 521.0),   # 109.0%
        ("L_CEDAR-BIRCH_230_1", 50001, 50002, "1", 552.0),   # 115.5%
        ("L_CEDAR-BIRCH_230_1", 50003, 50004, "1", 742.0),   # 103.5%
        ("L_BIRCH-ASPEN_230_1", 50004, 50005, "1", 503.0),   # 105.2%
        ("X_MAPLE_500/230_1",   50011, 50002, "1", 1262.0),  # 105.2%
        ("X_BIRCH-ELMHURST_1",  60001, 60002, "1", 271.0),   # 113.4%
        ("X_BIRCH-ELMHURST_1",  60002, 60003, "1", 168.0),   # 105.7%
        ("L_ELM-OAKDALE_115_1", 60002, 60003, "1", 173.0),   # 108.8%
    ]

def base_voltage():
    return [
        ("L_MAPLE-CEDAR_230_1", 60003, 1.0102, 0.9381),
        ("X_BIRCH-ELMHURST_1",  60002, 1.0050, 0.9298),
        ("X_BIRCH-ELMHURST_1",  60003, 1.0011, 0.9187),
        ("X_MAPLE_500/230_1",   50005, 1.0151, 0.9402),
    ]

# Post-upgrade: reconductor MAPLE-CEDAR & CEDAR-BIRCH (higher ratings),
# add 2nd BIRCH-ELMHURST transformer -> clears most 230kV + ELMHURST issues,
# but the reconductor pushes a little extra flow onto ASPEN-WILLOW (new/worse),
# and the 115kV OAKDALE issue is unaffected.
def post_thermal():
    return [
        ("L_CEDAR-BIRCH_230_1", 50003, 50004, "1", 731.0),   # 101.9% still mild
        ("L_BIRCH-ASPEN_230_1", 50004, 50005, "1", 548.0),   # 114.6% WORSE
        ("L_ELM-OAKDALE_115_1", 60002, 60003, "1", 173.0),   # 108.8% UNCHANGED
        ("X_MAPLE_500/230_1",   50004, 50005, "1", 491.0),   # 102.7% NEW element
    ]

def post_voltage():
    return [
        ("L_ELM-OAKDALE_115_1", 60003, 1.0009, 0.9442),      # NEW (mild)
        ("X_MAPLE_500/230_1",   50005, 1.0151, 0.9461),      # improved but still <0.95
    ]

# ---- report writer ------------------------------------------------------------
def write_report(path, title, thermal, voltage):
    ts = datetime.datetime(2026, 5, 28, 14, 3).strftime("%a %b %d %H:%M:%S %Y")
    L = []
    L.append("PSS(R)E  AC CONTINGENCY CALCULATION REPORT")
    L.append(f"  {title}")
    L.append(f"  RATING SET: A (NORMAL)    SOLVED: {ts}")
    L.append(f"  BASE CASE: {title}.sav     DFAX: study.dfx")
    L.append("  THRESHOLDS:  FLOW > 100.0%   VOLTAGE < 0.950 PU OR > 1.050 PU")
    L.append("=" * 113)
    L.append("")
    L.append("MONITORED BRANCH OVERLOADS (THERMAL)")
    L.append("-" * 113)
    hdr = (f"{'FROM BUS':<6s} {'FROM NAME':<16s}{'KV':>6s}{'TO BUS':>7s} "
           f"{'TO NAME':<15s}{'KV':>6s} CK "
           f"{'CONTINGENCY LABEL':<22s}{'RATING':>8s}{'FLOW(MVA)':>10s}{'LOAD%':>9s}")
    L.append(hdr)
    L.append("-" * 113)
    # group thermal by contingency for readability (as PSS/E does)
    for con in [c[0] for c in CONTINGENCIES]:
        rows = [t for t in thermal if t[0] == con]
        if not rows:
            continue
        L.append(f"CONTINGENCY: {con}")
        for (cl, frm, to, ckt, flow) in rows:
            rating = BR[(frm, to, ckt)]
            L.append(thermal_line(frm, to, ckt, cl, rating, flow))
        L.append("")
    L.append("=" * 113)
    L.append("")
    L.append("MONITORED BUS VOLTAGE VIOLATIONS")
    L.append("-" * 113)
    vhdr = (f"{'BUS':<6s} {'BUS NAME':<16s}{'KV':>6s}  "
            f"{'CONTINGENCY LABEL':<22s}{'V-INIT':>9s}{'V-CONT':>9s}{'DEV%':>9s}")
    L.append(vhdr)
    L.append("-" * 113)
    for con in [c[0] for c in CONTINGENCIES]:
        rows = [v for v in voltage if v[0] == con]
        if not rows:
            continue
        L.append(f"CONTINGENCY: {con}")
        for (cl, bus, vi, vc) in rows:
            L.append(voltage_line(bus, cl, vi, vc))
        L.append("")
    L.append("=" * 113)
    L.append("END OF REPORT")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")

write_report("/home/claude/accc/accc_base.rpt",
             "STUDY2026_SUMMER_PEAK_BASE", base_thermal(), base_voltage())
write_report("/home/claude/accc/accc_postupgrade.rpt",
             "STUDY2026_SUMMER_PEAK_UPGRADE", post_thermal(), post_voltage())
print("written")
