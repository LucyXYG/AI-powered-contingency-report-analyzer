# AI-Powered Contingency Report Analyzer

A Python tool for transmission planning that ingests **AC Contingency Calculation (ACCC)** reports exported from PSS®E, parses them into a clean tabular model, scores and ranks the violations, and — as the headline feature — **diffs a base case against a post-upgrade case** to show exactly which violations a proposed reinforcement resolved, left unchanged, made worse, or newly introduced.

The tool parses the *exported text report*, not a live PSS®E session, so it runs anywhere with no PSS®E license — on a laptop, or in the bundled Google Colab notebook.

> **Note on data:** the reports in `sample_data/` are *synthetic but realistic* — they reproduce the fixed-width column layout of a PSS®E ACCC single-run export on a small fictional network (MAPLE / CEDAR / BIRCH / ASPEN / WILLOW at 230 kV, a 500 kV backbone, and an ELMHURST / OAKDALE / PINE 115 kV pocket). They exist so the full pipeline is testable without proprietary files. Column widths vary slightly between PSS®E versions and report modes, so the parser's offsets are defined as named constants for easy retargeting.

---

## Why this tool

Transmission planning is a loop: run contingency analysis → find thermal and voltage violations → propose a fix (reconductor a line, add a transformer, etc.) → re-run → confirm the violations clear *and* nothing new breaks. The tedious, error-prone part is the before/after comparison across two large reports. This tool automates the parse, the triage, and that comparison.

---

## Architecture

A small, testable pipeline. Each stage has its own module and unit tests; the notebook is a thin presentation layer on top.

```
  ACCC .rpt (text)
        │
        ▼
  parsers/psse_accc.py   ──►  schema.ViolationRow  ──►  pandas DataFrame
        │                          (canonical row)
        ├──────────────────────────────────────────────┐
        ▼                                                ▼
  analytics.py                                       diff.py
   severity scoring                                 base vs post-upgrade
   critical contingencies                           resolved / new / worsened
   vulnerable elements                              improved / unchanged
        │                                                │
        └───────────────────────┬────────────────────────┘
                                 ▼
                           demo.ipynb (Plotly)
```

---

## The canonical schema (`schema.py`)

Everything downstream depends on one stable record type: a `ViolationRow` dataclass with 16 fields, one row per violation. Fields that don't apply to a given violation type are `Optional` and left `None` (thermal rows have no voltage fields; voltage rows have no rating/flow).

| Field | Meaning |
|---|---|
| `contingency_label` | the outage that caused the violation |
| `violation_type` | `thermal` or `voltage` |
| `element_type` | `branch`, `xfmr`, or `bus` |
| `from_bus`, `from_name`, `from_kv` | monitored element (or monitored bus) |
| `to_bus`, `to_name`, `to_kv` | second terminal (branches/transformers only) |
| `ckt` | circuit ID |
| `rating`, `flow`, `loading_pct` | thermal metrics |
| `v_init`, `v_cont`, `dev_pct` | voltage metrics (pre, post, % outside limit) |

`to_dataframe()` turns a list of these into a pandas DataFrame that the analytics and diff modules consume.

---

## Module 1 — Parser (`parsers/psse_accc.py`)

A **state-machine, fixed-width** parser. Two design decisions matter:

1. **Section state, not pattern guessing.** The report has a thermal (monitored-element overload) section and a voltage-violation section, each headed by a banner line. The parser flips a `section` flag on those banners; inside a section, lines beginning `CONTINGENCY:` set the current contingency label that subsequent data rows inherit.

2. **Column offsets, not whitespace splitting.** Bus names contain embedded spaces *and* digits (e.g. `WILLOW230`, `CEDAR 500`). A naive `.split()` would shred them. Instead every field is a named `slice` constant derived directly from the export's format string — e.g. thermal rows read `from_name` from `[6:23]`, the contingency label from `[63:87]`, and loading from `[105:114]`; voltage rows read the label from `[32:56]`.

Element type is inferred from voltage levels: a thermal element with `from_kv != to_kv` is a transformer, otherwise a branch — which is correct domain logic, since a branch joining two different nominal voltages *is* a transformer. (The heuristic classifies elements that appear as monitored violations; it doesn't label the equipment removed by the contingency itself.)

Public API: `parse_file(path) -> list[ViolationRow]` and `parse_to_dataframe(path) -> DataFrame`.

---

## Module 2 — Analytics (`analytics.py`)

Turns the flat violation table into the rankings a planner actually wants.

**Severity score** — a single defensible number per violation, with the weights as named constants so they can be explained and tuned:

```
thermal base  = max(0, loading_pct - 100)      # percent over rating
voltage base  = abs(dev_pct)                    # percent outside the limit band
severity      = base × KV_WEIGHT
KV_WEIGHT     = { 500 kV: 1.5,  230 kV: 1.2,  115 kV: 1.0 }
```

Higher-voltage problems score higher because they're more consequential. Worked example: the worst overload, CEDAR 230 → BIRCH 230 at 138.1 %, scores `(138.1 − 100) × 1.2 = 45.72` — the largest single severity in the base case.

**`critical_contingencies(df)`** — one row per contingency with `violation_count`, `max_severity`, `total_severity`, and `worst_loading_pct`. The caller chooses the sort key, because **count and severity deliberately disagree** (see the story below).

**`vulnerable_elements(df)`** — one row per monitored element, keyed by `(from_bus, to_bus, ckt)` for branches and `from_bus` for buses, with `n_contingencies` (how many *distinct* contingencies violate it), `max_severity`, and `max_loading_pct`. Sorted by `n_contingencies` — these are the **reinforcement candidates**, because an element that fails under several contingencies is a structural weak point, not a one-off.

**`summary(df)`** — six KPI scalars for the dashboard cards.

---

## Module 3 — Diff (`diff.py`)

The headline feature: compare two parsed reports.

A stable **violation key** lets the same violation be matched across the two files — `(contingency_label, from_bus, to_bus, ckt, 'thermal')` for thermal, `(contingency_label, from_bus, 'voltage')` for voltage. `diff_reports(base_df, post_df)` walks the union of keys and classifies each one against a named threshold `EPS = 0.1`:

| Status | Meaning |
|---|---|
| `resolved` | present in base, gone in post |
| `new` | absent in base, present in post |
| `worsened` | in both, post severity higher by more than EPS |
| `improved` | in both, post severity lower by more than EPS |
| `unchanged` | in both, within EPS |

`diff_summary(diff_df)` returns counts per status plus `net_change = n_resolved − n_new` — a single headline for the upgrade's effect.

---

## The complete story: base case → upgrade → diff

This is what the tool tells you when you feed it the two bundled reports.

### 1. The base case has 13 violations

Parsing `accc_base.rpt` yields **9 thermal overloads and 4 voltage violations across 6 N-1 contingencies**. The worst overload is **138.1 % on CEDAR 230 → BIRCH 230** under loss of the MAPLE–CEDAR line; the worst voltage is **−3.29 % on PINE 115** under loss of the BIRCH–ELMHURST transformer.

### 2. Which contingencies matter — and why "worst" is ambiguous

Ranking the contingencies surfaces a genuine planning nuance: **count and severity name different villains.**

- **X_BIRCH-ELMHURST_1** triggers the *most* violations — 4 (two 115 kV overloads plus two undervoltages in the same pocket).
- **L_MAPLE-CEDAR_230_1** has the *highest total and single severity*, driven by that one 138 % overload, despite causing only 3 violations.

A planner needs both lenses, which is why the tool reports both columns rather than collapsing to one number.

### 3. Which elements to reinforce

`vulnerable_elements` flags **OAKDALE 115 → PINE 115** and the **PINE 115 bus** as the top candidates — each is violated under *two distinct contingencies*. That makes them stronger reinforcement targets than, say, the 138 % CEDAR–BIRCH overload, which is more severe but appears under only one contingency. Breadth of exposure, not just peak percentage, is what a structural fix should target.

### 4. The proposed upgrade, tested

`accc_postupgrade.rpt` is the same study after reconductoring two 230 kV lines and adding a second BIRCH–ELMHURST transformer. The diff against the base case is the payoff:

**9 resolved · 2 improved · 1 unchanged · 1 worsened · 2 new (net: +7)**

- **9 resolved**, including the headline 138 % CEDAR–BIRCH overload and most of the ELMHURST-pocket problems.
- **1 unchanged** — OAKDALE 115 → PINE 115 at 108.8 % in *both* cases, because the upgrade didn't touch that 115 kV corridor.
- **1 worsened** — ASPEN 230 → WILLOW 230 climbs from 105.2 % to **114.6 %**: the reconductoring redistributed flow and loaded this line harder.
- **2 new** violations appear that weren't in the base case.

That last part is the point. A diff that only showed wins would be naive; flagging that the fix *introduced* a worsened line and new violations is exactly the honesty a planning team needs before signing off. The recommendation isn't "ship it" — it's "ship it, but the ASPEN–WILLOW corridor now needs a second look."

---

## Demo notebook (`demo.ipynb`)

Six visual sections, generated from the same logic modules, in the order they render:

**Figure 1 — Violations table.** The parsed base report as a DataFrame, sorted by severity descending. The top row is the 138.1 % CEDAR–BIRCH overload (severity 45.72); voltage rows sit lower with their negative `dev_pct`. This is the raw material everything else summarizes.

**Figure 2 — KPI cards.** The six `summary()` scalars at a glance: 13 violations, 9 thermal, 4 voltage, worst load 138.1 %, worst ΔV −3.29 %, 6 contingencies. The instant snapshot of how stressed the case is.

**Figure 3 — Critical Contingencies.** Horizontal bars ranked by total severity, each annotated with its violation count. This is where the count-vs-severity tension is visible: L_MAPLE-CEDAR_230_1 has the longest bar (severity) but only 3 violations, while X_BIRCH-ELMHURST_1 has a shorter bar but 4 violations. Which contingency you "worry about most" depends on the question.

**Figure 4 — Vulnerable Elements.** Bars ranked by the number of distinct contingencies that violate each element, colored by max severity. OAKDALE→PINE and PINE bus top the list at 2 contingencies — the reinforcement candidates. Note that CEDAR→BIRCH, despite the darkest color (highest severity, 45.7), sits lower because it's only exposed once.

**Figure 5 — Thermal Overload Heatmap.** Contingency (rows) × monitored element (columns), each cell colored by loading %, with non-violated pairs left blank. The visual centerpiece: the deep-red 138.1 % CEDAR–BIRCH cell jumps out immediately, and the sparse layout shows which contingencies stress which corridors.

**Figure 6 — Before/After Diff.** A diverging bar chart, one bar per violation, colored by status. Resolved/improved bars point **left** (length = the severity that was removed); worsened/new/unchanged point **right** (length = current severity). The big green CEDAR–BIRCH bar on the left is the headline win; the orange ASPEN–WILLOW bar and red bars on the right are the warnings. The plain-text headline above carries the `diff_summary` counts.

---

## Repository layout

```
.
├── schema.py                       # ViolationRow dataclass + to_dataframe
├── parsers/
│   ├── __init__.py
│   └── psse_accc.py                # fixed-width state-machine parser
├── analytics.py                    # severity, critical contingencies, vulnerable elements
├── diff.py                         # base vs post-upgrade comparison
├── tests/
│   ├── test_psse_accc.py
│   ├── test_analytics.py
│   └── test_diff.py
├── sample_data/
│   ├── gen_accc.py                 # synthetic report generator (deterministic)
│   ├── accc_base.rpt               # 13 violations across 6 contingencies
│   └── accc_postupgrade.rpt        # same study, post-reinforcement
├── demo.ipynb                      # Plotly walkthrough (the visual demo)
└── README.md
```

---

## Getting started

**Locally:**

```bash
pip install pandas plotly pytest
pytest                                       # run the full test suite
python -c "from parsers.psse_accc import parse_to_dataframe; \
           print(parse_to_dataframe('sample_data/accc_base.rpt'))"
```

**In Google Colab:** open `demo.ipynb`, then in the first cell:

```python
!git clone https://github.com/LucyXYG/AI-powered-contingency-report-analyzer.git
%cd AI-powered-contingency-report-analyzer
!pip install -q pandas plotly
```

Run top-to-bottom. The "Optional upload" cell lets you drop in your own `.rpt` to analyze a real study instead of the bundled sample.

To regenerate the sample reports: `python sample_data/gen_accc.py`.

---

## Possible extensions

- **Drive PSS®E directly** via `psspy` / `pssarrays` to run ACCC and parse the result in one step, instead of working from an exported file.
- **A second parser** for TARA (PowerGEM) reports feeding the same `ViolationRow` schema, so the analytics and diff layers work unchanged across tools.
- **N-1-1 support** — the schema already anticipates contingency order; the analytics could weight higher-order contingencies more heavily.
- **Batch / seasonal comparison** — diff a fleet of cases (summer peak vs. winter peak) rather than two.
- **Map NERC TPL criteria** onto the severity thresholds so the tool reports against a specific reliability standard.
