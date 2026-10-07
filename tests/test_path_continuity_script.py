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
