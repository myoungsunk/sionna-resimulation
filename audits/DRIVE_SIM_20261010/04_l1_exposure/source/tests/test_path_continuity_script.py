import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "drive_sim" / "path_continuity.py"


def timeline(path: Path, phase: str, n=3):
    cols = "idx,t_s,drive_g,phase,x,y,yaw_body_deg,turn_phase,probe_id,probe_offset_deg,pose_id"
    rows = [f"{i},{0.2 * i},{i},{phase},{2.0 + 0.04 * i},0.45,0.0,False,-1,0.0,{i}" for i in range(n)]
    path.write_text("\n".join([cols] + rows) + "\n")


def trace(dirp: Path, x: float, y: float):
    from qclean_uwb.drivesim.paths import path_residuals
    from qclean_uwb.scenarios.corridor import CorridorSetup
    s = CorridorSetup()
    res, pick, cd, names = path_residuals([1e-8], s.anchor_position, s.robot_position(x, y), s.length_m, s.y_half, s.height_m)
    from qclean_uwb.features.reflection_attribution import image_delays
    tau = np.array([image_delays(s.anchor_position, s.robot_position(x, y), s.length_m, s.y_half, s.height_m)[()]])
    np.savez(dirp / f"x{round(x, 6):.4f}_y{round(y, 6):.4f}_trace.npz", tau=tau, x=x, y=y, status="OK")


@pytest.mark.parametrize("phase", ["drive", "drive_out"])
def test_stations_are_counted_for_both_phase_naming_schemes(tmp_path, phase):
    tl = tmp_path / "tl.csv"
    timeline(tl, phase)
    for i in range(3):
        trace(tmp_path, 2.0 + 0.04 * i, 0.45)
    out = tmp_path / "g3.json"
    subprocess.run([sys.executable, str(SCRIPT), "--timeline", str(tl), "--traces", str(tmp_path), "--out", str(out)], check=True, capture_output=True,
                   env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    rep = json.loads(out.read_text())
    assert rep["stations"] == 3 and rep["passed_strict_prereg_tol"] is True


def test_an_empty_check_cannot_pass(tmp_path):
    tl = tmp_path / "tl.csv"
    timeline(tl, "something_else")
    r = subprocess.run([sys.executable, str(SCRIPT), "--timeline", str(tl), "--traces", str(tmp_path), "--out", str(tmp_path / "g3.json")], capture_output=True, text=True,
                       env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    assert r.returncode != 0 and "NO_STATIONS_FOUND" in (r.stderr + r.stdout) and not (tmp_path / "g3.json").exists()


def _trace_with(dirp: Path, x: float, y: float, keys):
    from qclean_uwb.features.reflection_attribution import image_delays
    from qclean_uwb.scenarios.corridor import CorridorSetup
    s = CorridorSetup()
    d = image_delays(s.anchor_position, s.robot_position(x, y), s.length_m, s.y_half, s.height_m)
    np.savez(dirp / f"x{round(x, 6):.4f}_y{round(y, 6):.4f}_trace.npz", tau=np.array([d[k] for k in keys]), x=x, y=y, status="OK")


def test_every_set_change_is_stored_and_strict_unmatched_stations_are_listed(tmp_path):
    n = 70                                       # alternating path sets -> 69 changes (> the old truncation at 50)
    tl = tmp_path / "tl.csv"
    cols = "idx,t_s,drive_g,phase,x,y,yaw_body_deg,turn_phase,probe_id,probe_offset_deg,pose_id"
    xs = [2.0 + 0.04 * i for i in range(n)]
    tl.write_text("\n".join([cols] + [f"{i},{0.2 * i},{i},drive,{xs[i]},0.45,0.0,False,-1,0.0,{i}" for i in range(n)]) + "\n")
    for i, x in enumerate(xs):
        _trace_with(tmp_path, x, 0.45, [(), ("floor",)] if i % 2 else [()])
    # one station gets a delay that matches no image path within 5e-14 s
    from qclean_uwb.features.reflection_attribution import image_delays
    from qclean_uwb.scenarios.corridor import CorridorSetup
    s = CorridorSetup()
    d = image_delays(s.anchor_position, s.robot_position(xs[5], 0.45), s.length_m, s.y_half, s.height_m)
    np.savez(tmp_path / f"x{round(xs[5], 6):.4f}_y{round(0.45, 6):.4f}_trace.npz", tau=np.array([d[()], d[("floor",)] + 1e-13]), x=xs[5], y=0.45, status="OK")
    out = tmp_path / "g3.json"
    subprocess.run([sys.executable, str(SCRIPT), "--timeline", str(tl), "--traces", str(tmp_path), "--out", str(out)], check=True, capture_output=True,
                   env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    rep = json.loads(out.read_text())
    assert rep["n_set_changes"] == len(rep["set_changes"]) > 50
    assert [r["tag"] for r in rep["strict_unmatched_stations"]] == [f"x{round(xs[5], 6):.4f}_y0.4500"]
    assert rep["strict_unmatched_stations"][0]["n_unmatched"] == 1 and rep["passed_strict_prereg_tol"] is False and rep["passed_relaxed_2e13"] is True
