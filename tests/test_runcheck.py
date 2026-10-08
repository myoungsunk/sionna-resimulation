"""The audit reproductions as regression tests: incomplete / inconsistent outputs must NOT validate, and the run script must not report success."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from qclean_uwb.runcheck import Expect, check_position, check_run

ROOT = Path(__file__).resolve().parents[1]
YAWS = [0.0, 10.0, 20.0]
FREQ = 6.2504e9 + 1.953125e6 * np.arange(257)


def make_exp(**kw):
    base = dict(yaw_deg=YAWS, bin_stride=64, freq_grid_hz=FREQ, solver={"max_depth": 3}, adapter_sha256="ad", bank_sha256={"a": "1"}, anchor_m=[5.0, 2.2, 2.65],
                setup_config_sha256="cfg", runner_sha256="run", materials=[("floor", "concrete", 0.2)], los_expected=lambda x, y: True, require_scene_files=1, scenario="office")
    base.update(kw)
    return Expect(**base)


def write_valid(folder: Path, tag: str, xy, exp: Expect, los=True):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "scene").mkdir(exist_ok=True)
    (folder / "scene" / "floor.ply").write_text("ply\n")
    bins = list(range(0, len(exp.freq_grid_hz), exp.bin_stride))
    ny, nb = len(exp.yaw_deg), len(bins)
    rng = np.random.default_rng(0)
    H = (rng.normal(size=(ny, nb, 2, 2)) + 1j * rng.normal(size=(ny, nb, 2, 2))) + 1.0
    counts = np.full((ny, nb), 2, np.int32)
    offsets = np.concatenate([[0], np.cumsum(counts.T.ravel())])
    n = int(offsets[-1])
    inter = np.zeros((1, n), np.int8)
    inter[0, 1::2] = 1  # per call: path 0 has no interaction (LoS), path 1 has one
    if not los:
        inter[0, :] = 1
    np.save(folder / f"{tag}_H.npy", H)
    np.savez_compressed(folder / f"{tag}_sweep.npz", H=H, yaw_deg=np.array(exp.yaw_deg), bin_index=np.array(bins), freqs_hz=exp.freq_grid_hz[bins], path_counts=counts, offsets=offsets,
                        tau_cat=np.zeros(n), a_cat=np.zeros((2, 2, n), np.complex64), interactions_cat=inter, objects_cat=np.zeros((1, n), np.int64),
                        robot_xy_m=np.array(xy), anchor_m=np.array(exp.anchor_m), robot_antenna_m=np.array([xy[0], xy[1], 0.45]), ports=np.array(["LP_plus45", "LP_minus45"]))
    rc = dict(scenario=exp.scenario, setup_config_sha256=exp.setup_config_sha256, robot_xy_m=list(xy), yaws=exp.yaw_deg, n_bins=nb, bin_stride=exp.bin_stride, pathsolver_calls=ny * nb,
              solver=exp.solver, adapter_sha256=exp.adapter_sha256, bank_sha256=exp.bank_sha256, runner_sha256=exp.runner_sha256, mean_paths=2.0, tag=tag, versions={"sionna-rt": "2.0.1"},
              materials=[dict(object=a, itu_type=b, thickness_m=c) for a, b, c in exp.materials])
    (folder / f"{tag}_receipt.json").write_text(json.dumps(rc))
    (folder / "SETUP_SNAPSHOT.json").write_text(json.dumps(dict(config_sha256=exp.setup_config_sha256)))


def test_valid_fixture_passes(tmp_path):
    exp = make_exp()
    write_valid(tmp_path / "t", "t", (1.0, 2.0), exp)
    assert check_position(tmp_path / "t", "t", (1.0, 2.0), exp) == []


def test_repro_A_zero_channel_without_sweep_npz_and_mismatched_receipt(tmp_path):
    exp = make_exp(bin_stride=1)
    f = tmp_path / "t"
    f.mkdir()
    np.save(f / "t_H.npy", np.zeros((19, 257, 2, 2), complex))
    (f / "t_receipt.json").write_text(json.dumps(dict(robot_xy_m=[9, 9], yaws=[0.0], n_bins=3, bin_stride=128, pathsolver_calls=3)))
    (f / "SETUP_SNAPSHOT.json").write_text("{}")
    assert check_position(f, "t", (1.0, 2.0), exp)


def test_repro_B_one_yaw_one_bin_minimal_npz_wrong_runner_hash(tmp_path):
    exp = make_exp()
    write_valid(tmp_path / "t", "t", (1.0, 2.0), exp)
    f = tmp_path / "t"
    np.save(f / "t_H.npy", np.ones((1, 1, 2, 2), complex))
    np.savez_compressed(f / "t_sweep.npz", H=np.ones((1, 1, 2, 2), complex))
    rc = json.loads((f / "t_receipt.json").read_text())
    rc["runner_sha256"] = "wrong"
    (f / "t_receipt.json").write_text(json.dumps(rc))
    issues = check_position(f, "t", (1.0, 2.0), exp)
    assert any("H shape" in i for i in issues) and any("lacks" in i for i in issues) and any("runner hash" in i for i in issues)


def test_receipt_only_is_not_valid(tmp_path):
    f = tmp_path / "t"
    f.mkdir()
    (f / "t_receipt.json").write_text("{}")
    assert check_position(f, "t", (1.0, 2.0), make_exp())


def test_stride_128_output_does_not_satisfy_a_stride_1_request(tmp_path):
    exp128 = make_exp(bin_stride=128)
    write_valid(tmp_path / "t", "t", (1.0, 2.0), exp128)
    assert check_position(tmp_path / "t", "t", (1.0, 2.0), exp128) == []
    assert check_position(tmp_path / "t", "t", (1.0, 2.0), make_exp(bin_stride=1))


def test_los_disagreement_and_zero_channels_are_caught(tmp_path):
    exp = make_exp()
    write_valid(tmp_path / "a", "a", (1.0, 2.0), exp, los=False)
    assert any("LoS" in i for i in check_position(tmp_path / "a", "a", (1.0, 2.0), exp))
    write_valid(tmp_path / "b", "b", (1.0, 2.0), exp)
    H = np.load(tmp_path / "b" / "b_H.npy")
    H[1, 0] = 0
    np.save(tmp_path / "b" / "b_H.npy", H)
    assert any("all-zero" in i for i in check_position(tmp_path / "b", "b", (1.0, 2.0), exp))


def test_check_run_missing_duplicate_unexpected(tmp_path):
    exp = make_exp()
    tag = lambda x, y: f"p_{x}_{y}"
    write_valid(tmp_path / tag(1.0, 2.0), tag(1.0, 2.0), (1.0, 2.0), exp)
    (tmp_path / "stray").mkdir()
    res = check_run(tmp_path, [(1.0, 2.0), (3.0, 4.0), (1.0, 2.0)], tag, exp)
    assert not res["ok"] and res["duplicates"] == [tag(1.0, 2.0)] and res["unexpected"] == ["stray"] and res["positions"][tag(3.0, 4.0)] == ["missing folder"]


def run_script(tmp_path, positions, env_extra, pre=None):
    out = tmp_path / "out"
    if pre:
        pre(out)
    pos = tmp_path / "pos.txt"
    pos.write_text(positions)
    env = dict(os.environ, SCENARIO="office", POSITIONS=str(pos), OUT=str(out), BIN_STRIDE="128", CORES="2", VERIFY_PYTHON=sys.executable)
    env.update(env_extra)
    r = subprocess.run(["bash", str(ROOT / "scripts" / "sweep_run.sh")], env=env, capture_output=True, text=True)
    return r, out


def test_run_script_failing_runner_gives_nonzero_exit_and_no_complete_marker(tmp_path):
    r, out = run_script(tmp_path, "5.0 0.75\n0.5 5.25\n", dict(PYTHON="false"))
    assert r.returncode == 1 and not (out / "logs" / "SWEEP_COMPLETE").exists()
    assert len((out / "logs" / "FAILED").read_text().splitlines()) == 2


def test_run_script_receipt_only_folders_are_not_resumed_and_are_kept(tmp_path):
    def pre(out):
        for tag in ("office_x5.0_y0.75", "office_x0.5_y5.25"):
            (out / tag).mkdir(parents=True)
            (out / tag / f"{tag}_receipt.json").write_text("{}")
    r, out = run_script(tmp_path, "5.0 0.75\n0.5 5.25\n", dict(PYTHON="false"), pre)
    assert r.returncode == 1 and not (out / "logs" / "SWEEP_COMPLETE").exists()
    kept = list((out / "_superseded").glob("office_x*/*_receipt.json"))
    assert len(kept) == 2  # the old folders were preserved, not deleted


def test_run_script_refuses_a_different_request_on_the_same_directory(tmp_path):
    r1, out = run_script(tmp_path, "5.0 0.75\n", dict(PYTHON="false"))
    assert r1.returncode == 1
    r2, _ = run_script(tmp_path, "5.0 0.75\n", dict(PYTHON="false", BIN_STRIDE="1"))
    assert r2.returncode == 2 and "REQUEST_MISMATCH" in r2.stderr
