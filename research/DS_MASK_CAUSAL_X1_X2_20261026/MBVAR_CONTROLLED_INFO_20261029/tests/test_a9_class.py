"""AMENDMENT-009 F1: class v3.1 must not pass a point with a probe descent > tau, whatever the analytic decrement."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import a9_class as K  # noqa: E402


def test_auditor_counterexample_is_not_certified():
    assert K.class_v3_a008(0.0, -0.02) == "CONVERGED_SMOOTH"          # the A008 short-circuit (W1)
    assert K.class_v31(0.0, -0.02) == "NOT_CERTIFIED"


def test_smooth_and_certified_cases():
    assert K.class_v31(1e-12, -1e-11) == "CONVERGED_SMOOTH"
    assert K.class_v31(1e-3, -0.005) == "LOCAL_MIN_CERTIFIED"
    assert K.class_v31(1e-3, -0.0101) == "NOT_CERTIFIED"


def test_nan_probe_is_not_certified():
    assert K.class_v31(0.0, math.nan) == "NOT_CERTIFIED"


def test_v31_never_less_strict_than_a008():
    for dec in (0.0, 1e-11, 1e-9, 1e-3, 0.1):
        for d in (-1.0, -0.02, -0.01, -0.005, 0.0, 1e-3):
            if K.class_v3_a008(dec, d) == "NOT_CERTIFIED":
                assert K.class_v31(dec, d) == "NOT_CERTIFIED"
