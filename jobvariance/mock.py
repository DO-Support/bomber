"""Bundled mock dataset for the demo dashboard — no real company data.

Same record schema as ``build.build_payload``. Customers, jobs and figures are
invented for demonstration only.
"""

from __future__ import annotations

TOL = 0.02


def _status(std: float, act: float) -> str:
    if std == 0:
        return "Over-issued" if act > 0 else "On-track"
    d = (act - std) / std
    return "Over-issued" if d > TOL else "Under-issued" if d < -TOL else "On-track"


# (JobNumber, JobDate, Customer, Description,
#  [(material, std_cost, despatch, return, std_units, actual_units)])
_JOBS = [
    ("DO-090001", "2026-06-02", "Acme Workwear", "Hi-vis two-piece conti suit", [
        ("Fabric", 89000.00, 92100.00, 900.00, 3050.0, 3120.0),
        ("Trims Zips", 10600.00, 10820.00, 0.00, 3050.0, 3050.0),
        ("Trims Labels", 5800.00, 5820.00, 0.00, 10600.0, 10600.0),
        ("Trims Cotton", 3100.00, 3040.00, 0.00, 1520.0, 1500.0),
    ]),
    ("DO-090002", "2026-06-05", "Sample Client A", "Flame-retardant bib brace", [
        ("Fabric", 132000.00, 121500.00, 2400.00, 3960.0, 3600.0),
        ("Trims Press Studs", 4200.00, 3980.00, 0.00, 6100.0, 6100.0),
        ("Trims Tape", 6900.00, 6120.00, 0.00, 3300.0, 3300.0),
    ]),
    ("DO-090003", "2026-06-11", "Demo Mining Co", "Arc-flash coverall 40cal", [
        ("Fabric", 240000.00, 268000.00, 3000.00, 6800.0, 7200.0),
        ("Trims Zips", 18000.00, 21500.00, 0.00, 4900.0, 5200.0),
        ("Trims Buttons", 1600.00, 1720.00, 0.00, 1500.0, 1500.0),
        ("Trims Sticker and Swing Tags", 165.00, 165.00, 0.00, 1500.0, 1500.0),
    ]),
    ("DO-090004", "2026-06-18", "Acme Workwear", "Chef jacket long-sleeve", [
        ("Fabric", 31500.00, 35200.00, 300.00, 720.0, 780.0),
        ("Trims Cotton", 2000.00, 2180.00, 0.00, 900.0, 900.0),
        ("Trims Buttons", 6000.00, 7000.00, 0.00, 1400.0, 1400.0),
        ("Customer Supplied", 0.00, 1800.00, 0.00, 0.0, 60.0),
    ]),
    ("DO-090005", "2026-06-24", "Sample Client B", "Acid-resistant apron", [
        ("Fabric", 45000.00, 41200.00, 500.00, 1500.0, 1400.0),
        ("Trims Elastic", 4500.00, 4180.00, 0.00, 640.0, 640.0),
        ("Trims Tape", 9000.00, 8600.00, 320.00, 3100.0, 3100.0),
    ]),
    ("DO-090006", "2026-07-01", "Demo Mining Co", "Winter lined jacket", [
        ("Fabric", 71500.00, 71600.00, 100.00, 1100.0, 1100.0),
        ("Trims Zips", 10500.00, 10520.00, 0.00, 3400.0, 3400.0),
        ("Trims Packaging", 4200.00, 4180.00, 0.00, 1500.0, 1500.0),
    ]),
    ("DO-090007", "2026-07-08", "Sample Client A", "Welding leather spats", [
        ("Fabric", 110000.00, 127500.00, 1500.00, 2400.0, 2600.0),
        ("Trims Drawcord", 3000.00, 3320.00, 0.00, 900.0, 900.0),
        ("Trims Buttons", 12000.00, 12800.00, 0.00, 6400.0, 6400.0),
    ]),
    ("DO-090008", "2026-07-13", "Acme Workwear", "Standard poly-cotton shirt", [
        ("Fabric", 72000.00, 66500.00, 800.00, 1800.0, 1700.0),
        ("Trims Cotton", 3000.00, 2900.00, 0.00, 1450.0, 1450.0),
        ("Trims Labels", 8000.00, 7900.00, 0.00, 8000.0, 8000.0),
    ]),
]


def mock_records() -> list[dict]:
    records = []
    for job, jdate, cust, desc, mats in _JOBS:
        for mat, std, desp, ret, std_units, act_units in mats:
            actual = round(desp - ret, 2)
            records.append({
                "JobNumber": job, "JobDate": jdate, "CustomerName": cust,
                "JobDescription": desc, "Material": mat,
                "Standard_Cost": round(std, 2),
                "Despatch_Cost": round(desp, 2),
                "Return_Cost": round(ret, 2),
                "Actual_Cost": actual,
                "Standard_Units": round(std_units, 1),
                "Actual_Units": round(act_units, 1),
                "Variance": round(std - actual, 2),
                "Variance_Units": round(std_units - act_units, 1),
                "VarianceStatus": _status(std, actual),
            })
    return records
