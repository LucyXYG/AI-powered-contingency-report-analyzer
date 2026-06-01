"""Generate demo.ipynb. Run once (or after editing cell sources below)."""
import json
import pathlib

ROOT = pathlib.Path(__file__).parent


def _cc(src: str, cid: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "id": cid,
            "metadata": {}, "outputs": [], "source": src}


def _md(src: str, cid: str) -> dict:
    return {"cell_type": "markdown", "id": cid, "metadata": {}, "source": src}


# ---------------------------------------------------------------------------
# Cell sources  (Python code uses single-quoted strings throughout)
# ---------------------------------------------------------------------------

TITLE = """\
# ACCC Contingency Report Analyzer — Demo

End-to-end walk-through of **parser → analytics → diff** against the bundled
synthetic PSS/E ACCC reports.

Run cells **top-to-bottom**.  Swap your own `.rpt` in the *Optional upload*
cell to analyse a real study.\
"""

SETUP = """\
# ── Colab setup ──────────────────────────────────────────────────────────────
# Fill in your GitHub path, uncomment the three lines, then Run All.
# !git clone https://github.com/<me>/<repo>.git
# %cd <repo>
# !pip install -q pandas plotly\
"""

IMPORTS = """\
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from parsers.psse_accc import parse_to_dataframe
from analytics import add_severity, critical_contingencies, vulnerable_elements, summary
from diff import diff_reports, diff_summary\
"""

UPLOAD_MD = """\
## Optional — Upload Your Own Report

Run the cell below to drop a real PSS/E ACCC `.rpt` file onto the demo.
Skip it to use the bundled `sample_data/accc_base.rpt` throughout.\
"""

UPLOAD = """\
BASE_RPT = 'sample_data/accc_base.rpt'   # default; overwritten when a file is uploaded

try:
    from google.colab import files as _colab_files
    print('Click Choose Files to upload a .rpt — or skip this cell for sample data.')
    _up = _colab_files.upload()
    if _up:
        BASE_RPT = next(iter(_up))
        print('Using uploaded file:', BASE_RPT)
    else:
        print('No file uploaded — using', BASE_RPT)
except ImportError:
    print('Not in Colab — using', BASE_RPT)\
"""

LOAD_MD = """\
## 1 · Load

Parse the base-case report, compute severity scores, and display every violation
ranked from most to least severe.\
"""

LOAD = """\
df = parse_to_dataframe(BASE_RPT)
df = add_severity(df)

display_cols = [
    'contingency_label', 'violation_type', 'element_type',
    'from_name', 'to_name', 'loading_pct', 'dev_pct', 'severity',
]
(df[display_cols]
 .sort_values('severity', ascending=False)
 .reset_index(drop=True))\
"""

KPI_MD = """\
## 2 · KPI Cards

Six headline figures for the loaded report.\
"""

KPI = """\
kpi = summary(df)

fig = make_subplots(
    rows=1, cols=6,
    specs=[[{'type': 'indicator'} for _ in range(6)]],
)
kpi_items = [
    ('Violations',    kpi['total_violations'],     ''),
    ('Thermal',       kpi['thermal_count'],         ''),
    ('Voltage',       kpi['voltage_count'],         ''),
    ('Worst load',    kpi['worst_loading_pct'],     '%'),
    ('Worst ΔV', kpi['worst_voltage_dev_pct'], '%'),
    ('Contingencies', kpi['n_contingencies'],       ''),
]
for col, (title, val, suffix) in enumerate(kpi_items, start=1):
    fig.add_trace(
        go.Indicator(
            mode='number',
            value=val,
            title={'text': title, 'font': {'size': 13}},
            number={'suffix': suffix, 'font': {'size': 30}},
        ),
        row=1, col=col,
    )
fig.update_layout(height=200, margin=dict(t=30, b=0, l=20, r=20))
fig.show()\
"""

CC_MD = """\
## 3 · Critical Contingencies

Horizontal bars ranked by **total severity**; annotated with violation count.
Count-rank and severity-rank can disagree — both perspectives matter.\
"""

CC = """\
cc = (critical_contingencies(df, sort_by='total_severity')
      .sort_values('total_severity'))          # ascending so highest is at top

fig = go.Figure(go.Bar(
    y=cc['contingency_label'],
    x=cc['total_severity'],
    orientation='h',
    text=[f'{n} violation' + ('' if n == 1 else 's') for n in cc['violation_count']],
    textposition='outside',
    marker=dict(
        color=cc['total_severity'],
        colorscale='YlOrRd',
        showscale=True,
        colorbar=dict(title='Total<br>severity'),
    ),
))
fig.update_layout(
    title='Critical Contingencies — Total Severity Score',
    xaxis_title='Total Severity Score',
    height=400,
    margin=dict(l=230, r=130, t=60, b=40),
)
fig.show()\
"""

VE_MD = """\
## 4 · Vulnerable Elements

Elements that violate under the most contingencies are the strongest
reinforcement candidates — fix one, improve multiple contingency outcomes.\
"""

VE = """\
ve = vulnerable_elements(df).copy()
ve['label'] = ve.apply(
    lambda r: (f'{r["from_name"]} → {r["to_name"]}'
               if pd.notna(r['to_name']) else r['from_name']),
    axis=1,
)
ve_plot = ve.sort_values('n_contingencies')     # ascending so highest is at chart top

fig = go.Figure(go.Bar(
    y=ve_plot['label'],
    x=ve_plot['n_contingencies'],
    orientation='h',
    text=[f'max sev {s:.1f}' for s in ve_plot['max_severity']],
    textposition='outside',
    marker=dict(
        color=ve_plot['max_severity'],
        colorscale='Blues',
        showscale=True,
        colorbar=dict(title='Max<br>severity'),
    ),
))
fig.update_layout(
    title='Vulnerable Elements — Reinforcement Candidates',
    xaxis=dict(title='Distinct contingencies triggering a violation', dtick=1),
    height=500,
    margin=dict(l=250, r=160, t=60, b=40),
)
fig.show()\
"""

HM_MD = """\
## 5 · Overload Heatmap

Visual centrepiece: **contingency × monitored element**, colour = loading %.
Blank cells = no thermal violation recorded for that pair.\
"""

HM = """\
thermal = df[df['violation_type'] == 'thermal'].copy()
thermal['element'] = (
    thermal['from_name'].str.strip() + ' → ' + thermal['to_name'].str.strip()
)
pivot = thermal.pivot_table(
    index='contingency_label',
    columns='element',
    values='loading_pct',
    aggfunc='max',
)
pivot.columns.name = None
pivot.index.name = None

z = pivot.values.astype(float)
text_grid = [
    [f'{v:.1f}%' if not np.isnan(v) else '' for v in row]
    for row in z
]

fig = go.Figure(go.Heatmap(
    z=z,
    x=pivot.columns.tolist(),
    y=pivot.index.tolist(),
    colorscale='YlOrRd',
    zmin=100,
    zmax=max(float(np.nanmax(z)), 110),
    text=text_grid,
    texttemplate='%{text}',
    colorbar=dict(title='Loading %'),
    hoverongaps=False,
))
fig.update_layout(
    title='Thermal Overload Heatmap: Contingency × Element',
    height=420,
    margin=dict(l=230, r=40, b=190, t=60),
    xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
)
fig.show()\
"""

DIFF_MD = """\
## 6 · Before / After Diff

Compare the base-case and post-upgrade reports.
Bars point **left** for resolved violations (gone), **right** for all others.
Bar length = severity score.\
"""

DIFF = """\
POST_RPT = 'sample_data/accc_postupgrade.rpt'
post_df  = parse_to_dataframe(POST_RPT)

ddf = diff_reports(df, post_df).copy()
ds  = diff_summary(ddf)

headline = (
    f"{ds['n_resolved']} resolved  ·  "
    f"{ds['n_new']} new  ·  "
    f"{ds['worsened']} worsened  ·  "
    f"{ds['improved']} improved  ·  "
    f"{ds['unchanged']} unchanged"
    f"   (net: {'+' if ds['net_change'] >= 0 else ''}{ds['net_change']})"
)

STATUS_COLOR = {
    'resolved':  '#2ca02c',   # green
    'improved':  '#1f77b4',   # blue
    'unchanged': '#aec7e8',   # grey-blue
    'worsened':  '#ff7f0e',   # orange
    'new':       '#d62728',   # red
}
STATUS_ORDER = ['resolved', 'improved', 'unchanged', 'worsened', 'new']


def _bar_x(row):
    if row['status'] == 'resolved':
        return -(row['base_severity'] if pd.notna(row['base_severity']) else 0.0)
    return float(row['post_severity'] if pd.notna(row['post_severity']) else 0.0)


ddf['bar_x'] = ddf.apply(_bar_x, axis=1)
ddf['label'] = ddf['contingency_label'] + ' / ' + ddf['element']
ddf['_ord']  = ddf['status'].map({s: i for i, s in enumerate(STATUS_ORDER)})
ddf = ddf.sort_values(['_ord', 'bar_x']).reset_index(drop=True)

fig = go.Figure()
for status in STATUS_ORDER:
    grp = ddf[ddf['status'] == status]
    if grp.empty:
        continue
    fig.add_trace(go.Bar(
        x=grp['bar_x'],
        y=grp['label'],
        name=status,
        orientation='h',
        marker_color=STATUS_COLOR[status],
        width=0.6,
    ))

fig.update_layout(
    title=headline,
    barmode='overlay',
    xaxis=dict(
        title='← resolved   |   severity →',
        zeroline=True, zerolinewidth=2, zerolinecolor='black',
    ),
    yaxis=dict(autorange='reversed', tickfont=dict(size=10)),
    height=620,
    margin=dict(l=385, r=120, t=60, b=40),
    legend=dict(title='Status', traceorder='normal'),
)
fig.show()\
"""

# ---------------------------------------------------------------------------
# Assemble and write
# ---------------------------------------------------------------------------

cells = [
    _md(TITLE,     "title0"),
    _cc(SETUP,     "setup0"),
    _cc(IMPORTS,   "impt0"),
    _md(UPLOAD_MD, "upmd0"),
    _cc(UPLOAD,    "upcd0"),
    _md(LOAD_MD,   "load0"),
    _cc(LOAD,      "load1"),
    _md(KPI_MD,    "kpi0"),
    _cc(KPI,       "kpi1"),
    _md(CC_MD,     "cc0"),
    _cc(CC,        "cc1"),
    _md(VE_MD,     "ve0"),
    _cc(VE,        "ve1"),
    _md(HM_MD,     "hm0"),
    _cc(HM,        "hm1"),
    _md(DIFF_MD,   "diff0"),
    _cc(DIFF,      "diff1"),
]

notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.10.0"},
        "colab": {"provenance": []},
    },
    "cells": cells,
}

out = ROOT / "demo.ipynb"
with open(out, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"Written {out}  ({len(cells)} cells)")
