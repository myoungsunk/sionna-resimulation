"""Stage 1: first-path s for every pose of runs A, B, C and the reference runs (centerline M7, 4 cm near), plus GX.
Usage: python extract_ext.py <result-branch checkout root>   -> writes ../EXT_S.csv.gz, ../GX.csv"""
import sys, json, numpy as np, pandas as pd
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0",
                "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8/step3_sweep/dev_02/code"]
import feats as FT
from common import env
import h_ref as HR

ROOT = sys.argv[1]
RUNS = {"A": "BLOCK_C_M7_EXT_A_20261127_ZTuwVf7S", "B": "BLOCK_C_M7_EXT_B_20261127_J85C8uA7", "C": "BLOCK_C_M7_EXT_C_20261127_Wqwau3Xq",
        "CL": "BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5", "NEAR": "BLOCK_C_M7_NEAR_20261119_2ujQQZVt"}
CENTERS_X = [7.95, 6.60, 5.70, 5.25, 4.35, 3.45, 2.10, 1.20]   # P016 P013 P011 P010 P008 P006 P003 P001
e0 = env(); ffd = HR.ffd_s_fn(e0["model"])
out = []
for run, rid in RUNS.items():
    d = f"{ROOT}/artifacts/{rid}/results"
    P = pd.DataFrame(json.load(open(f"{d}/poses/BLOCKC_B/rf_poses.json")))
    Hf = np.load(f"{d}/H/BLOCKC_B/H_full.npy", mmap_mode="r"); Hl = np.load(f"{d}/H/BLOCKC_B/H_LoS.npy", mmap_mode="r")
    assert len(P) == len(Hf) == len(Hl) and (P.pose_id.values == np.arange(len(P))).all()
    keep = np.ones(len(P), bool)
    if run == "CL":   # only the centerline centers used in this analysis
        keep = np.isin(np.round(P.x.values, 2), CENTERS_X) & np.isclose(P.y.values, 0.0)
    idx = np.flatnonzero(keep)
    Ff = FT.features(Hf[idx]); Fl = FT.features(Hl[idx])
    Q = P.iloc[idx].reset_index(drop=True).copy()
    Q["run"] = run; Q["s_full"] = Ff.s_fp.values; Q["s_los"] = Fl.s_fp.values; Q["valid"] = Ff.valid.values.astype(bool)
    st = np.c_[Q.x.values, Q.y.values, np.radians(Q.yaw_body_deg.values), np.zeros(len(Q))]
    Q["s_ffd"] = np.concatenate([ffd(st[k:k + 512], e0["spec"])[0] for k in range(0, len(st), 512)])
    out.append(Q); print(run, len(Q), flush=True)
S = pd.concat(out, ignore_index=True)
S["x"] = S.x.round(2); S["y"] = S.y.round(2); S["e"] = S.s_full - S.s_los
S.to_csv("../EXT_S.csv.gz", index=False)
G = (S.assign(d=(S.s_los - S.s_ffd).abs()).groupby(["run", "x", "y"])
     .agg(n=("d", "size"), p90=("d", lambda v: np.quantile(v, 0.9)), valid=("valid", "mean")).reset_index())
G["pass"] = (G.p90 <= 0.005) & (G.valid >= 0.99)
G.to_csv("../GX.csv", index=False)
print(G.groupby("run").agg(n=("pass", "size"), passed=("pass", "sum"), p90max=("p90", "max"), vmin=("valid", "min")))
