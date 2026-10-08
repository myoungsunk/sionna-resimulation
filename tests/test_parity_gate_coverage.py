import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location("parity_gate_under_test", ROOT / "scripts" / "drive_sim" / "parity_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_or_unusable_positions_fail_the_gate_even_when_the_remaining_rows_pass():
    pg = _load()
    rep = dict(passed=True, checks=dict(abs_ds_max=True))
    ok = pg.coverage_checked(rep, [], [])
    assert ok["passed"] is True and ok["checks"]["coverage_complete"] is True
    for miss, bad in ((["x1_y0"], []), ([], ["x2_y0"]), (["a"], ["b"])):
        r = pg.coverage_checked(rep, miss, bad)
        assert r["passed"] is False and r["checks"]["coverage_complete"] is False and r["missing"] == miss and r["unusable"] == bad
    assert pg.coverage_checked(dict(passed=False, checks={}), [], [])["passed"] is False
