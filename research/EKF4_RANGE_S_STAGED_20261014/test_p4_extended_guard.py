"""Independent fail-closed export guard regression for original R5 pilot issues.

Blocked output is NOT old smooth CONVERGED, and no positive objective
slack (including tiny eps) is accepted.
"""
import math
import pytest
from p4_extended_validation import classify_export_objective

@pytest.mark.parametrize("c0,d_internal,c_export,expected", [
    (1.0,-1e-3,0.999,"ELIGIBLE_NONINCREASING"),
    (1.0,0.0,1.0,"ELIGIBLE_NONINCREASING"),
    (1.0,-1e-14,1.0+1e-14,"EXPORT_OBJECTIVE_INCREASE_BLOCKED"),
    (1.0,1e-15,1.0,"INTERNAL_OBJECTIVE_INCREASE_BLOCKED"),
    (1.0,-1e-5,1.0+1e-8,"EXPORT_OBJECTIVE_INCREASE_BLOCKED"),
    (1.0,-1e-4,1.0-1e-7,"INCONSISTENT_OBJECTIVE_EXPORT_BLOCKED"),
    (1.0,float("nan"),1.0,"NONFINITE_OBJECTIVE_EXPORT_BLOCKED"),
])
def test_strict_export_contract(c0,d_internal,c_export,expected):
    assert classify_export_objective(c0,d_internal,c_export)==expected
