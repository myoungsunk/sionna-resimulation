"""Shared paths, loaders and filter primitives for the reflection-model experiments (V0-V3).

Directory layout (REFLECT_ROOT, default = folder of this file):
  repo/        sparse copy of myoungsunk/sionna-resimulation code (qclean_uwb src, FFD_P0P3, EKF4 core)  -- fetch_inputs.sh
  banks/       LP_plus45_bank.npz, LP_minus45_bank.npz (sha256 checked)
  rf/          H_<case>.npy (full), H_LoS_<case>.npy, SAMPLES_<case>.json
  traces/      <case>_<bias>_CONTROL.npz  (why_ds_worse E1 control traces, commit 9bcd5da)
  out/         results
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("REFLECT_ROOT", Path(__file__).resolve().parent))
REPO = ROOT / "repo"
OUT = ROOT / "out"
for p in (REPO / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src",
          REPO / "research/EKF4_RANGE_S_STAGED_20261014",
          REPO / "research/FFD_P0P3_20261016",
          Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))
os.makedirs(ROOT / "ffd_p0p3/out", exist_ok=True)      # p0_initial writes here at import

BANK_SHA = {"LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
            "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"}
HZ = 2.2
OFF = 0.5315983906250129
DT = 0.2
CASES = {
    "R2_aA_m0": dict(anchor=(4.0, 0.0, 2.65), robot_z_m=0.45, mount_deg=0.0),
    "R2_aB_m0": dict(anchor=(10.0, 0.0, 2.65), robot_z_m=0.45, mount_deg=0.0),
    "R2_aA_m45": dict(anchor=(4.0, 0.0, 2.65), robot_z_m=0.45, mount_deg=45.0),
    "R4_aA_m0": dict(anchor=(4.0, 0.0, 2.65), robot_z_m=0.45, mount_deg=0.0),
    "R4_aB_m0": dict(anchor=(10.0, 0.0, 2.65), robot_z_m=0.45, mount_deg=0.0),
    "R5_aA_m0": dict(anchor=(4.0, 0.0, 2.65), robot_z_m=0.45, mount_deg=0.0),
    "R5_aB_m0": dict(anchor=(10.0, 0.0, 2.65), robot_z_m=0.45, mount_deg=0.0),
}
PRIMARY = ("R2_aA_m45", "R4_aA_m0", "R4_aB_m0")
BIASES = ("B0", "L2")
DIST_BINS = (0.0, 1.5, 3.0, 6.0, 99.0)


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


_BASE = None


def base_model():
    """Original LOS-only SourceFFD with the verified banks."""
    global _BASE
    if _BASE is None:
        from qclean_uwb.drivesim import pattern_apply as PA
        import source_model
        banks = []
        for name, digest in BANK_SHA.items():
            path = ROOT / "banks" / name
            if sha256(path) != digest:
                raise RuntimeError(f"BANK_SHA_MISMATCH {name}")
            with np.load(path, allow_pickle=False) as z:
                banks.append(PA.Bank(dict(z)))
        _BASE = source_model.SourceFFD(banks=banks)
    return _BASE


def load_control(case: str, bias: str) -> dict:
    """E1 control trace: arms OFF_BB (mu_B, j=0) and OFF_MB (mu_M, j=1), mask A_B."""
    z = np.load(ROOT / "traces" / f"{case}_{bias}_CONTROL.npz")
    names = [str(n) for n in z["names"]]
    jb, jm = names.index("OFF_BB"), names.index("OFF_MB")
    d = {k: z[k] for k in z.files}
    d["jb"], d["jm"] = jb, jm
    return d


def load_rf(case: str):
    Hf = np.load(ROOT / "rf" / f"H_{case}.npy", mmap_mode="r")
    Hl = np.load(ROOT / "rf" / f"H_LoS_{case}.npy", mmap_mode="r")
    samples = json.loads((ROOT / "rf" / f"SAMPLES_{case}.json").read_text())
    return Hf, Hl, samples


def smooth(v: np.ndarray, L: int = 25) -> np.ndarray:
    v = np.asarray(v, float)
    pad = np.r_[np.full(L // 2, v[0]), v, np.full(L // 2, v[-1])]
    return np.convolve(pad, np.ones(L) / L, "valid")


def write_manifest(stage: str, config: dict, outputs: list) -> None:
    """Run manifest required by AGENTS.md: config snapshot + hash, inputs, outputs, timestamp, command line."""
    import time
    lock = ROOT / "out" / "INPUT_LOCK.sha256"
    cfg = json.dumps(config, sort_keys=True, default=str)
    man = dict(stage=stage, utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), command=sys.argv,
               git_sha=os.environ.get("GITHUB_SHA"), run_id=os.environ.get("GITHUB_RUN_ID"),
               config=config, config_sha256=hashlib.sha256(cfg.encode()).hexdigest(),
               input_lock=lock.read_text().splitlines() if lock.exists() else "MISSING: run fetch_inputs.sh",
               code_sha256={p.name: sha256(p) for p in sorted(Path(__file__).resolve().parent.glob("*.py"))},
               outputs={str(o): sha256(OUT / o) for o in outputs if (OUT / o).exists()})
    (OUT / f"MANIFEST_{stage}.json").write_text(json.dumps(man, indent=1, default=str))


def wrap(a):
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def predict_one(x, P, ds, gyro, dt):
    """Original prediction: core.predict with q = diag(2e-5|ds|, (0.015 deg)^2 dt, 0)."""
    from core import predict
    q = np.diag([2e-5 * abs(ds), math.radians(.015) ** 2 * dt, 0.0])
    y, Pp, _, _ = predict(x, P, float(ds), float(gyro), float(dt), q)
    return y, Pp


def controls_from(x_post: np.ndarray, prior: np.ndarray, t: np.ndarray):
    """Recover (ds, gyro, dt) exactly from one stored arm (prior_k = f(x_{k-1}, u_k)); verified to 1e-16."""
    n = len(t)
    ds, gy = np.zeros(n), np.zeros(n)
    dt = np.r_[0.0, np.diff(t)]
    for k in range(1, n):
        xp, pr = x_post[k - 1], prior[k]
        a = float(wrap(pr[2] - xp[2]))
        gy[k] = a + xp[3] * dt[k]
        c = math.sin(a / 2) / (a / 2) if abs(a) > 1e-12 else 1.0
        phi = xp[2] + a / 2
        ds[k] = float((pr[:2] - xp[:2]) @ np.array([math.cos(phi), math.sin(phi)])) / c
    return ds, gy, dt


def first_pass(rg: np.ndarray):
    near = np.flatnonzero(rg < 1.5)
    brk = np.flatnonzero(np.diff(near) > 1)
    eps = np.split(near, brk + 1)
    return eps


def pass_windows(t, rg, first_only=False, pad_s=10.0):
    eps = first_pass(rg)
    if first_only:
        eps = eps[:1]
    w = np.zeros(len(t), bool)
    for e in eps:
        w |= (t >= t[e[0]] - pad_s - 1e-8) & (t <= t[e[-1]] + pad_s + 1e-8)
    return w
