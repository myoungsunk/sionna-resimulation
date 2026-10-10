import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from test_parity_gate_coverage import _load


def row(x=5.5, yaw=-50., error=0.):
    return dict(xy=[x, .35], yaw_deg=yaw, pose_rel_err=error,
                per_bin_max=error, abs_ds=error, fp_index_match=True, range_diff_m=error)


def thresholds(pg, key="G2_B_per_bin_trace"):
    return {k: v["value"] for k, v in json.loads(pg.PREREG.read_text())["config"]["gates"][key].items()}


def test_valid_numeric_threshold_regression_and_empty():
    pg = _load()
    for key in ("G2_B_per_bin_trace", "G2p_B_node_interpolation"):
        thr = thresholds(pg, key)
        for error in (0., 1e-7, .003):
            rows = [row(error=error), row(yaw=230., error=error)]
            out = pg.summarize(rows, thr, key)
            assert out["pose_rel_err_median"] == error
            assert out["pose_rel_err_max"] == error
            assert out["abs_ds_max"] == error
            expected = error <= thr["abs_ds_max"] and error <= thr["range_diff_max_m"]
            if "h_rel_err_median_max" in thr:
                expected &= error <= thr["h_rel_err_median_max"] and error <= thr["h_rel_err_max"]
            assert out["passed"] == expected
        assert pg.summarize([], thr, key)["passed"] is False


def test_duplicate_nonfinite_and_invalid_h():
    pg = _load()
    with pytest.raises(ValueError, match="DUPLICATE"):
        pg.summarize([row(), row()], thresholds(pg), "G2")
    with pytest.raises(ValueError, match="INVALID"):
        pg.summarize([row(error=float("nan"))], thresholds(pg), "G2")
    freqs = np.linspace(3e9, 4e9, 8)
    h = np.ones((8, 2, 2), complex)
    assert pg.compare(h, h, freqs)["pose_rel_err"] == 0
    for candidate, ref, f in ((h[:2], h, freqs), (h*np.nan, h, freqs), (h, h*0, freqs), (h,h,freqs[::-1])):
        with pytest.raises(ValueError):
            pg.compare(candidate, ref, f)


def test_exact_g4_manifest_coverage(tmp_path):
    pg = _load()
    task = dict(task_id=0, tag=pg.tag_of(5.5,.35), x=5.5, y=.35, antenna_yaw_deg=[-50.,230.])
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([task]))
    expected = pg.expected_manifest_keys(path)
    rows = [row(), row(yaw=230.)]
    base = dict(passed=True, checks={})
    assert pg.g4_coverage_checked(base, rows, expected)["passed"]
    for actual in (rows[:1], rows+[row(yaw=250.)], rows+[row()]):
        assert not pg.g4_coverage_checked(base, actual, expected)["passed"]
    for tasks in ([], [task,task], [dict(task, antenna_yaw_deg=[])], [dict(task, antenna_yaw_deg=[-50.,-50.])], [dict(task,x=float("nan"))]):
        path.write_text(json.dumps(tasks))
        with pytest.raises(ValueError):
            pg.expected_manifest_keys(path)


@pytest.mark.parametrize("args,reason", [([], "NO_GATES_SELECTED"), (["--g4-only"], "NO_GATES_SELECTED"),
    (["--g4-a-dir","absent","--traces-all","absent"],"G4_REQUIRES_MANIFEST"),
    (["--g4-manifest","absent"],"NO_GATES_SELECTED")])
def test_cli_failure_before_banks(tmp_path, monkeypatch, args, reason):
    pg = _load()
    out = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["parity_gate", *args, "--out", str(out)])
    monkeypatch.setattr(pg, "load_banks", lambda: pytest.fail("must reject inputs before loading banks"))
    assert pg.main() == 1
    report = json.loads(out.read_text())
    assert not report["all_passed"]
    assert reason in report["input_errors"][0]


def test_cli_valid_g4_uses_strict_g2_and_records_manifest(tmp_path, monkeypatch):
    pg = _load()
    path = tmp_path/"tasks.json"
    path.write_text(json.dumps([dict(task_id=0,tag=pg.tag_of(5.5,.35),x=5.5,y=.35,antenna_yaw_deg=[-50.])]))
    out = tmp_path/"report.json"
    monkeypatch.setattr(sys,"argv",["parity_gate","--g4-only","--traces-nodes","traces","--g4-a-dir","direct","--g4-manifest",str(path),"--out",str(out)])
    monkeypatch.setattr(pg,"load_banks",lambda:[SimpleNamespace(freqs_hz=np.arange(8))])
    monkeypatch.setattr(pg,"run_g4",lambda *args:[row(error=2e-4)])
    # Node G2p permits 2e-4; frozen G4 (G2) H-relative threshold does not.
    assert pg.main() == 1
    report=json.loads(out.read_text())
    assert report["G4_out_of_range_yaw"]["thresholds"] == thresholds(pg)
    assert len(report["G4_out_of_range_yaw"]["manifest_sha256"]) == 64
    monkeypatch.setattr(pg,"run_g4",lambda *args:[row()])
    assert pg.main() == 0


def test_empty_reference_and_malformed_g4(tmp_path):
    pg = _load()
    with pytest.raises(ValueError, match="EMPTY_REFERENCE"):
        pg.run_set(tmp_path, [], [], np.arange(8))
    sub=tmp_path/pg.tag_of(5.5,.35); sub.mkdir()
    with pytest.raises(ValueError, match="INVALID_G4_FILES"):
        pg.run_g4(tmp_path,tmp_path,[],np.arange(8))

