"""Variance math + payload contract — no DB."""

from __future__ import annotations

import pandas as pd

from jobvariance.build import _status, build_payload
from jobvariance.mock import mock_records


def test_status_boundaries():
    # Within +/-2% tolerance → on-track.
    assert _status(100.0, 101.0) == "On-track"
    assert _status(100.0, 99.0) == "On-track"
    # Beyond tolerance.
    assert _status(100.0, 103.0) == "Over-issued"
    assert _status(100.0, 97.0) == "Under-issued"


def test_status_zero_standard():
    assert _status(0.0, 0.0) == "On-track"
    assert _status(0.0, 50.0) == "Over-issued"


def test_variance_sign_convention():
    # Variance = standard - actual. Positive = under-issued (saved).
    assert _status(100.0, 90.0) == "Under-issued"   # actual < standard
    assert _status(100.0, 110.0) == "Over-issued"   # actual > standard


def test_build_payload_from_mock_frame():
    records = mock_records()
    df = pd.DataFrame(records)
    out = build_payload(df)
    assert len(out) == len(records)
    keys = {
        "JobNumber", "JobDate", "CustomerName", "JobDescription", "Material",
        "Standard_Cost", "Despatch_Cost", "Return_Cost", "Actual_Cost",
        "Standard_Units", "Actual_Units", "Variance", "Variance_Units",
        "VarianceStatus",
    }
    assert keys <= set(out[0])
    # Variance identity holds per row.
    for r in out:
        assert round(r["Variance"], 2) == round(r["Standard_Cost"] - r["Actual_Cost"], 2)
