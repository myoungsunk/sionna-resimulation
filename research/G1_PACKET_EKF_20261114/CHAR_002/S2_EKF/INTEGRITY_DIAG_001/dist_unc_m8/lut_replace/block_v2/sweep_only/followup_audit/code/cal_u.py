"""Route-yaw-free sweep calibration CAL_U (pre-declared single change from cal_b.py): the evaluator truth-yaw histogram weights of the
evaluated route are replaced by the station site weights n4b.site_weights (no route information). Everything else as cal_b / s0id_refit:
mu_r = HGB(EXIST features) on e_r with those weights; mu_s, R_rr, R_ss from POWER_BIN_JOINT with the same weights, s label = S0-id label
(s_full - h_FFD). Used identically for S0-id-U and SWB-U (SWB uses mu_r, R_rr only)."""
import sys, json, hashlib, importlib.util, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8cal"); sys.path.insert(0, "/home/claude/m8")
from feats import FE, FZ, EXIST
from common import packet
from sklearn.ensemble import HistGradientBoostingRegressor
s = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py"); n4b = importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["e_s"] = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
F = pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
w = np.asarray(n4b.site_weights(np, pd, SW), float); w = w / w.mean()
g = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(SW[EXIST], SW.e_r, sample_weight=w)
out, chk = {}, dict(rule="route truth-yaw weights -> n4b.site_weights", w_eff=float(w.sum()**2 / (w**2).sum()), w_sha256=hashlib.sha256(w.tobytes()).hexdigest())
B0 = np.load("/home/claude/lut0/S0ID_CAL.npz")
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); T = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    mu, cov, _ = n4b.fit_model(np, SW, T, w, "POWER_BIN_JOINT", FE.GROUPS)
    out.update({f"{r}/mu_r": g.predict(T[EXIST]), f"{r}/mu_s": mu[:, 1], f"{r}/Rrr": cov[:, 0, 0], f"{r}/Rss": cov[:, 1, 1]})
    chk[r] = {k: dict(rms_change=float(np.sqrt(np.mean((out[f"{r}/{k}"] - B0[f"{r}/{k}"])**2))), median_U=float(np.median(out[f"{r}/{k}"])), median_B=float(np.median(B0[f"{r}/{k}"])))
              for k in ("mu_r", "mu_s", "Rrr", "Rss")}
np.savez("CAL_U.npz", **out); json.dump(chk, open("CAL_U_CHECK.json", "w"), indent=1); print(json.dumps(chk, indent=1)[:1500])
