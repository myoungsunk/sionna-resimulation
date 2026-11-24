"""V0-1b: route-level judgment of range mean-correction candidates at true poses (R2, R5; RF realisation is seed-independent).
U0 none | U1 3-bin mean on rho_hat (from measured range, online-valid) | U3 CAL_U HGB(EXIST), uniform station weights.
Rule (fixed before run): pass = |mean| <= 2 cm in every true-rho bin [0,3),[3,6),[6,10) on both R2 and R5; among passing, min pooled RMS; none pass -> U1."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8")
from common import packet, TRUTH, env
from sklearn.ensemble import HistGradientBoostingRegressor
FZ = "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_inputs/OFFICE_CORRIDOR_TRANSFER_FIX_20261026"
EXIST = ['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); F = pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
B_OLD = float(np.median(SW.range_m - SW.e_r - SW.d3)); DH = 2.65 - 0.45
rho_hat = lambda rng: np.sqrt(np.maximum((np.asarray(rng) - B_OLD)**2 - DH**2, 0.))
E3 = np.array([0, 3, 6, 10.]); bin3 = lambda r: np.clip(np.searchsorted(E3, r, side="right") - 1, 0, 2)
U1 = pd.Series(SW.e_r.values).groupby(bin3(rho_hat(SW.range_m))).mean().reindex(range(3)).values
g = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(SW[EXIST], SW.e_r)
e = env(); out = dict(B_OLD=B_OLD, U1_table_cm=(100 * U1).tolist(), routes={})
for r in ("R2", "R5"):
    p = packet("B0", 10, r); T = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    assert np.max(np.abs(T[["range_m", "s_fp"]].to_numpy() - p["z"])) < 1e-9
    tr = TRUTH[r]; ix = pd.Index(tr["pose_id"]).get_indexer(p["pose_id"]); X = tr["truth"][ix]
    h, H = e["model"].batch(np.c_[X[:, :3], np.zeros(len(X))], e["spec"])
    er = p["z"][:, 0] - h[:, 0]                                   # residual vs model range prediction at true pose
    rho = np.hypot(X[:, 0] - 10, X[:, 1]); b = bin3(rho)
    cand = dict(U0=np.zeros(len(er)), U1=U1[bin3(rho_hat(p["z"][:, 0]))], U3=g.predict(T[EXIST]))
    out["routes"][r] = dict(n=int(len(er)), label_check_cm=float(100 * np.max(np.abs(er - T.e_r.values))), bins={})
    for k, mu in cand.items():
        res = er - mu
        out["routes"][r]["bins"][k] = [dict(bin=int(q), n=int((b == q).sum()), mean_cm=float(100 * res[b == q].mean()) if (b == q).any() else None,
                                            rms_cm=float(100 * np.sqrt(np.mean(res[b == q]**2))) if (b == q).any() else None) for q in range(3)]
        out["routes"][r]["bins"][k].append(dict(bin="all", rms_cm=float(100 * np.sqrt(np.mean(res**2)))))
dec = {}
for k in ("U1", "U3"):
    ok = all(abs(x["mean_cm"]) <= 2 for r in ("R2", "R5") for x in out["routes"][r]["bins"][k][:3] if x["mean_cm"] is not None)
    rms = float(np.sqrt(np.mean([x["rms_cm"]**2 for r in ("R2", "R5") for x in out["routes"][r]["bins"][k][3:]])))
    dec[k] = dict(pass_=ok, pooled_rms_cm=rms)
passing = [k for k in dec if dec[k]["pass_"]]; out["decision"] = dict(candidates=dec, selected=min(passing, key=lambda k: dec[k]["pooled_rms_cm"]) if passing else "U1")
json.dump(out, open("V0_1B.json", "w"), indent=1)
print("B_OLD", round(B_OLD, 4), "U1 table cm", np.round(100 * U1, 2))
for r in ("R2", "R5"):
    print(r, "label check cm", round(out["routes"][r]["label_check_cm"], 4))
    for k, v in out["routes"][r]["bins"].items(): print("  ", k, " | ".join(f"b{x['bin']} n{x.get('n','')} mean {x.get('mean_cm') if x.get('mean_cm') is None else round(x['mean_cm'],2)} rms {round(x['rms_cm'],2) if x['rms_cm'] is not None else None}" for x in v))
print(json.dumps(out["decision"]))
