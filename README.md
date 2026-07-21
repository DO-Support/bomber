# Job Material Variance Dashboard

Interactive dashboard comparing **standard required raw materials** against **actual
issued materials** per job, sourced live from the iSync (MS SQL) database. Single-file
HTML output (Tailwind + Chart.js + Lucide), with date-range filtering, search,
colour-coded status, a per-job drilldown modal, and a dark-mode switch that follows
Windows by default.

![status](https://img.shields.io/badge/output-single--file%20HTML-2563eb)

## Live demo (mock data)

Open [`dashboard-demo.html`](dashboard-demo.html) in a browser — built from bundled
mock data, no database needed.

## The variance model

| Side | Source view | How |
|---|---|---|
| **Standard** (should-have-used) | `Reporting.vProductStockMovements` | Per-cost-sub-type money columns are the standard cost **per finished unit**. Standard = `SUM(rate × units)` over `Received` (production) rows. |
| **Actual** (what was issued) | `Reporting.vStockMovements` | `Despatch − Return`, netted. Quantities are signed (Despatch negative, Return positive), so actual issued = `−SUM(MovementValue)`. |

Both sides join on the cost sub type (FG column name == RM `CostType`), compared in
**Rand**. `Variance = Standard − Actual` (positive = under-issued/saved, negative =
over-issued). Labour/overhead sub types (CMT, Overheads, Outwork) are excluded — they
are never issued from RM stock.

### Units variance

Alongside Rand, a **units** variance is available per cost type. Standard required
units come from `Reporting.v_RMA_CurrentRequired_NoFilter` (`RequiredUnits`, total BOM
requirement, covering all job statuses incl. `Complete (No WIP)`), joined to actual
issued units from `vStockMovements` on `JobNumber + CostType`. The drilldown shows
Std / Actual / Variance units per cost type plus a Rand/Units toggle on the variance
chart. Job-level cards and the main table stay in Rand, since units can't be summed
across cost types (metres + each).

### Date handling (important)

The date range selects **jobs** by their first production receipt. Both standard and
actual are then that job's **full totals across all dates**, never windowed per row.
Production receipts and material issues straddle the window boundary (fabric is cut
weeks before the garment is received into FG), so windowing either side independently
compares a partial standard to a full actual and reports huge phantom variances.

## Usage

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in MSSQL_* credentials (read-only login)

# Live build:
python -m jobvariance.build --from 2026-05-01 --to 2026-07-16 --out dashboard.html

# Mock demo (no DB):
python -m jobvariance.build --mock --out dashboard-demo.html
```

The raw SQL is also provided standalone in [`sql/job_material_variance.sql`](sql/job_material_variance.sql).

## Layout

```
jobvariance/
  build.py                    queries + payload builder + render + CLI
  db.py                       read-only MS SQL connection (SQLAlchemy + pyodbc)
  mock.py                     bundled demo dataset (no real data)
  templates/job_variance.html dashboard template (__DATA__ placeholder)
sql/job_material_variance.sql standalone documented query
dashboard-demo.html           committed demo (mock data)
```

## Data & security

- `.env` and any **live-data** build (`job-material-variance-dashboard.html`) are
  gitignored — they contain real credentials / customer financials. Only the
  mock-data demo is committed.
- The DB connection is read-only (`ApplicationIntent=ReadOnly`).

## Caveats

- Fabric commonly shows under-issued where it is issued under a holding/cutting job
  number rather than the DO — a genuine signal, not a bug. Trims typically reconcile
  within a few percent.
- Sub-type coverage in the SQL sample is a subset; the Python builder
  (`MATERIAL_SUBTYPES`) carries the full list.
