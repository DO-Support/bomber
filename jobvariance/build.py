"""Job material variance: standard cost content vs actual raw-material issued.

Standard (what a job *should* have consumed) comes from the finished-goods view
``Reporting.vProductStockMovements``, whose per-cost-sub-type money columns are the
standard cost **per unit** of finished product. Standard cost per sub type per job =
SUM(rate * units) over production ``Received`` movements.

Actual (what was issued) comes from ``Reporting.vStockMovements``, netting Despatch
(stored negative) against Return (stored positive): actual issued Rand =
-SUM(MovementValue) over Despatch+Return. The two sides join on the cost sub type
(FG column name == RM CostType, whitespace-stripped).

Compared in Rand — the only common denominator, since the standard side carries no
raw-material unit quantities. Actual units are surfaced as supplementary detail.

Usage:
    python -m jobvariance.build --from 2026-05-01 --to 2026-07-16 --out dashboard.html
    python -m jobvariance.build --mock --out dashboard-demo.html   # no DB needed
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# Cost sub types that are genuine issued raw materials (present as money columns in
# vProductStockMovements AND as CostType values in vStockMovements). Labour/overhead
# sub types (CMT, Overheads, Outwork, Shipping) are deliberately excluded — they are
# never issued from RM stock, so they have no actual to compare against.
MATERIAL_SUBTYPES: list[str] = [
    "Fabric", "Fabric ICC", "Fabric Kevro", "Fabric Alpac", "Fabric Brand Brigade",
    "Fabric Comage", "Fabric Cowie", "Fabric Dirt Road", "Fabric Dyambu",
    "Fabric General Workwear", "Fabric Kulanathi Black Ginger", "Fabric Merbit",
    "Fabric Mighty Supplies", "Fabric Sedgars/Fredock", "Fabric Simon Workwear",
    "Fabric Sniper", "Fabric Star Tune", "Fabric Well Worn",
    "Trims", "Trims ICC", "Trims Sticker and Swing Tags", "Trims Tape", "Trims Labels",
    "Trims Packaging", "Trims Velcro", "Trims Elastic", "Trims Drawcord", "Trims Zips",
    "Trims Other", "Trims Cotton", "Trims Press Studs", "Trims Buttons",
    "Customer Supplied",
]

# Percentage tolerance on |variance| / standard within which a material is "on-track".
TOLERANCE_PCT = 2.0

# The date window selects JOBS, not individual movements. A job is in scope when its
# production STARTED (first FG receipt) inside the window. Both the standard and the
# actual side are then the job's FULL totals across all dates — never windowed per row.
# This is essential: a job's production and its material issues straddle the window
# boundary (fabric is cut weeks before FG receipt, receipts trickle in over weeks), so
# windowing either side independently compares a partial standard to a full actual (or
# vice-versa) and reports enormous phantom variances.
_JOB_SET = """
        SELECT p.fJobNumber
        FROM Reporting.vProductStockMovements AS p
        WHERE p.MovementType = 'Received'
        GROUP BY p.fJobNumber
        HAVING MIN(p.MovementDate) >= :date_from AND MIN(p.MovementDate) < :date_to
"""


def _standard_sql() -> str:
    """Standard cost per (job, material): SUM(per-unit rate x units) over ALL of the
    selected jobs' production receipts, whenever received."""
    values = ",\n        ".join(f"('{s}', p.[{s}])" for s in MATERIAL_SUBTYPES)
    return f"""
SELECT
    p.fJobNumber                          AS JobNumber,
    LTRIM(RTRIM(u.Material))              AS Material,
    SUM(u.Rate * p.fUnits)               AS Standard_Cost
FROM Reporting.vProductStockMovements AS p
CROSS APPLY (VALUES
        {values}
    ) AS u(Material, Rate)
WHERE p.MovementType = 'Received'
  AND p.fJobNumber IN ({_JOB_SET})
GROUP BY p.fJobNumber, LTRIM(RTRIM(u.Material))
HAVING SUM(u.Rate * p.fUnits) <> 0
"""


# Job header: JobDate = first production receipt (the anchor date shown in the table);
# UnitsProduced = full units across all receipts for the selected jobs.
_HEADER_SQL = """
SELECT
    p.fJobNumber                          AS JobNumber,
    MAX(p.JobDesc)                        AS JobDescription,
    MAX(p.Customer_Vendor)               AS CustomerName,
    CAST(MIN(p.MovementDate) AS date)    AS JobDate,
    SUM(p.fUnits)                        AS UnitsProduced
FROM Reporting.vProductStockMovements AS p
WHERE p.MovementType = 'Received'
GROUP BY p.fJobNumber
HAVING MIN(p.MovementDate) >= :date_from AND MIN(p.MovementDate) < :date_to
"""

# Actual RM issued for the selected jobs, netting Despatch (signed negative) against
# Return (signed positive). Every issue for the job counts, whenever it was issued.
_ACTUAL_SQL = f"""
SELECT
    s.fJobNumber                                                             AS JobNumber,
    LTRIM(RTRIM(s.CostType))                                                 AS Material,
    -SUM(CASE WHEN s.MovementType = 'Despatch' THEN s.MovementValue ELSE 0 END) AS Despatch_Cost,
     SUM(CASE WHEN s.MovementType = 'Return'   THEN s.MovementValue ELSE 0 END) AS Return_Cost,
    -SUM(CASE WHEN s.MovementType IN ('Despatch','Return') THEN s.MovementValue ELSE 0 END) AS Actual_Cost,
    -SUM(CASE WHEN s.MovementType IN ('Despatch','Return') THEN s.fUnits      ELSE 0 END) AS Actual_Units
FROM Reporting.vStockMovements AS s
WHERE s.MovementType IN ('Despatch','Return')
  AND s.fJobNumber IN ({_JOB_SET})
GROUP BY s.fJobNumber, LTRIM(RTRIM(s.CostType))
HAVING -SUM(CASE WHEN s.MovementType IN ('Despatch','Return') THEN s.MovementValue ELSE 0 END) <> 0
"""

# Standard required UNITS per (job, cost type) from the BOM requirement view. Grain is
# per cost sub type; we roll up to CostType to match both the Rand model's material key
# and vStockMovements.CostType (the actual-units key). RequiredUnits is the total
# requirement (not net-remaining). Covers all job statuses, incl. Complete (No WIP).
_STD_UNITS_SQL = f"""
SELECT
    r.JobNumber                        AS JobNumber,
    LTRIM(RTRIM(r.CostType))          AS Material,
    SUM(r.RequiredUnits)              AS Standard_Units
FROM Reporting.v_RMA_CurrentRequired_NoFilter AS r
WHERE r.JobNumber IN ({_JOB_SET})
GROUP BY r.JobNumber, LTRIM(RTRIM(r.CostType))
HAVING SUM(r.RequiredUnits) <> 0
"""


def _status(standard: float, actual: float) -> str:
    if standard == 0:
        return "Over-issued" if actual > 0 else "On-track"
    diff = (actual - standard) / standard
    if diff > TOLERANCE_PCT / 100:
        return "Over-issued"
    if diff < -TOLERANCE_PCT / 100:
        return "Under-issued"
    return "On-track"


def fetch_job_variance(engine, date_from: date, date_to: date) -> pd.DataFrame:
    """Flat one-row-per (job, material) frame of standard vs actual, in Rand.

    ``date_to`` is exclusive. The window selects jobs by first production receipt;
    both sides are then full job totals (see the module docstring).
    """
    from .db import read_sql

    params = {"date_from": date_from, "date_to": date_to}
    std = read_sql(engine, _standard_sql(), params)
    act = read_sql(engine, _ACTUAL_SQL, params)
    units = read_sql(engine, _STD_UNITS_SQL, params)
    hdr = read_sql(engine, _HEADER_SQL, params)

    merged = std.merge(act, on=["JobNumber", "Material"], how="outer")
    merged = merged.merge(units, on=["JobNumber", "Material"], how="outer")
    for col in ("Standard_Cost", "Despatch_Cost", "Return_Cost", "Actual_Cost",
                "Actual_Units", "Standard_Units"):
        merged[col] = pd.to_numeric(merged.get(col), errors="coerce").fillna(0.0)
    merged["Variance"] = merged["Standard_Cost"] - merged["Actual_Cost"]
    merged["Variance_Units"] = merged["Standard_Units"] - merged["Actual_Units"]

    merged = merged.merge(hdr, on="JobNumber", how="left")
    merged["JobDate"] = pd.to_datetime(merged["JobDate"]).dt.strftime("%Y-%m-%d")
    for col, default in (("JobDescription", ""), ("CustomerName", "")):
        merged[col] = merged[col].fillna(default).astype(str).str.strip()
    merged["JobDate"] = merged["JobDate"].fillna(date_from.strftime("%Y-%m-%d"))
    merged["VarianceStatus"] = [
        _status(s, a) for s, a in zip(merged["Standard_Cost"], merged["Actual_Cost"])
    ]
    return merged.sort_values(["JobNumber", "Material"]).reset_index(drop=True)


def build_payload(df: pd.DataFrame) -> list[dict]:
    """Shape the flat frame into the JSON records the dashboard embeds."""
    records = []
    for r in df.itertuples(index=False):
        records.append({
            "JobNumber": r.JobNumber,
            "JobDate": r.JobDate,
            "CustomerName": r.CustomerName,
            "JobDescription": r.JobDescription,
            "Material": r.Material,
            "Standard_Cost": round(float(r.Standard_Cost), 2),
            "Despatch_Cost": round(float(r.Despatch_Cost), 2),
            "Return_Cost": round(float(r.Return_Cost), 2),
            "Actual_Cost": round(float(r.Actual_Cost), 2),
            "Standard_Units": round(float(r.Standard_Units), 1),
            "Actual_Units": round(float(r.Actual_Units), 1),
            "Variance": round(float(r.Variance), 2),
            "Variance_Units": round(float(r.Variance_Units), 1),
            "VarianceStatus": r.VarianceStatus,
        })
    return records


def _template_path() -> Path:
    return Path(__file__).with_name("templates") / "job_variance.html"


def render_html(records: list[dict], title: str, subtitle: str, live: bool = False) -> str:
    """Render the dashboard. Static build embeds `records`; live mode (server)
    starts empty and fetches from /data on date change."""
    template = _template_path().read_text(encoding="utf-8")
    return (
        template
        .replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__LIVE__", "true" if live else "false")
        .replace('"__DATA__"', "[]" if live else json.dumps(records))
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the job material variance dashboard.")
    ap.add_argument("--from", dest="date_from", help="Start date (inclusive) YYYY-MM-DD.")
    ap.add_argument("--to", dest="date_to", help="End date (exclusive); defaults to today.")
    ap.add_argument("--out", default="dashboard.html", help="Output HTML file.")
    ap.add_argument("--mock", action="store_true",
                    help="Build from bundled mock data — no database connection needed.")
    args = ap.parse_args()

    if args.mock:
        from .mock import mock_records
        records = mock_records()
        subtitle = "Standard vs actual issued (Rand) · demo (mock data)"
    else:
        if not args.date_from:
            ap.error("--from is required (or use --mock)")
        from .db import get_engine
        d_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(args.date_to, "%Y-%m-%d").date() if args.date_to else date.today()
        df = fetch_job_variance(get_engine(), d_from, d_to)
        if df.empty:
            raise SystemExit("No jobs with standard or actual material movements in that window.")
        records = build_payload(df)
        subtitle = f"Standard vs actual issued (Rand) · {d_from} → {d_to} · iSync live"

    html = render_html(records, "Job Material Variance", subtitle)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    jobs = len({r["JobNumber"] for r in records})
    var = sum(r["Variance"] for r in records)
    print(f"Wrote {out} — {jobs} jobs, {len(records)} job/material lines, net variance R{var:,.0f}.")


if __name__ == "__main__":
    main()
