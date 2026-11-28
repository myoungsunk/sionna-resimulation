"""Paths and loaders for FG-V1. All paths are relative to the repository root (this file: research/FG_V1_20261128/code/)."""
import os, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
FGV1 = HERE.parent                                   # research/FG_V1_20261128
REPO = Path(os.environ.get("FGV1_REPO", FGV1.parents[1]))
I = str(REPO / "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001")
M = I + "/m7_final_model_stage1"
OUT = str(FGV1 / "results")                          # small JSON results (committed)
SUR = str(FGV1 / "sur")                              # FFD grid (~180 MB, not committed; rebuild with gen_grid.py)
TRACE = str(FGV1 / "traces")                         # npz traces (not committed)
BASE = os.environ.get("FGV1_BASE", str(FGV1 / "native" / "base.json"))   # written by setup.sh
os.makedirs(OUT, exist_ok=True); os.makedirs(TRACE, exist_ok=True)
sys.path.insert(0, M); sys.path.insert(0, str(HERE))
import m7_replay as R7
_env = None
def env():
    global _env
    if _env is None: _env = R7.load_environment(BASE)
    return _env
def packet(cond, seed, route):
    Z = np.load(f"{M}/attempt_02/input_generation/inputs/{cond}/seed{seed}/{route}_online.npz")
    return {k: Z[k] for k in Z.files}
def truth(route):
    return np.load(f"{I}/gm_theta_m6/inputs/{route}_evaluator.npz")["truth"]
def ffd_h(nav3):
    e = env(); h, H = e["model"].batch(np.r_[nav3, 0.][None], e["spec"]); return h[0], H[0][:, :3]
