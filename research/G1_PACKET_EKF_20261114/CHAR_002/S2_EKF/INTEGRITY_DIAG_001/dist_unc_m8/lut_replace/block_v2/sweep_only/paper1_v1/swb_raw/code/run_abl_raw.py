"""SWB-RAW + sensitivity (S) / time-correlation (T) ablation. Block: all stations = measured curve harmonics (sw_block_allraw).
Tables from the RAW block's own column-out residuals (RSS_VARIANTS.json: allraw Rss, c1, c0). Range channel V1 (U3 mu_r, R_rr).
Arms as run_ablate.py: B (white simple), S (white c1 a^2 + c0), T (simple + KI), S+T (F1), F2 (GM + KI). B0, dev seeds 10-29, R2/R4/R5 + N1-N6."""
import sys, os, json, time, pickle, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/v1"); from v1_common import *
OUT = "/home/claude/v1/out_abl_raw"; RV = json.load(open("/home/claude/v1/RSS_VARIANTS.json"))["allraw"]; _G = {}
ROUTES = ["R2", "R4", "R5"] + [f"N{i}" for i in range(1, 7)]
def init():
    from common import env, scorers; import h_ref as HR, sw_block_allraw as BR
    g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); e = env()
    FN = pd.read_csv("/home/claude/n1n6/cir_features/OBSERVATION_FEATURES.csv.gz"); FR = pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); FR = FR[FR.channel == "full"]
    _G.update(g=g, Rrr=np.array(Rrr), FN=FN, FR=FR, eR=HR.swap_env(e, BR.SWB().s_fn()), sc=scorers())
def get(r, seed):
    from common import packet, TRUTH
    if r[0] == "R":
        p = packet("B0", seed, r); T = _G["FR"][_G["FR"].case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]]; return p, TRUTH[r]["truth"], T
    rf = dict(np.load(f"/home/claude/n1n6/v1_h2_inputs/{r}_aB_m0.npz")); p = dict(np.load(f"/home/claude/n1n6/v1_controls/B0/seed{seed}/{r}_controls.npz"))
    p.update({k: rf[k] for k in ("z", "muMB", "muBASE", "R", "D")}); T = _G["FN"][_G["FN"].case == f"{r}_aB_m0"].set_index("pose_id").loc[rf["pose_id"]]
    return p, np.load(f"/home/claude/n1n6/v1_controls/{r}_evaluator.npz")["truth"], T
def job(seed):
    f = f"{OUT}/B0/seed{seed}/RES.json"
    if os.path.exists(f): return seed, "reuse", 0
    from run_m8s3 import sweep_packet, ZERO_SB; import m8x as M
    ft, swb, bm = _G["sc"]; t0 = time.time(); res = {}
    simple = dict(edges=E3.tolist(), c1=[0.] * 3, c0=RV["Rss"]); full = dict(edges=E3.tolist(), c1=RV["c1c0"]["c1"], c0=RV["c1c0"]["c0"])
    cfg = {"B": ("F0", simple, dict(white="model", corr=None, gm=None)), "S": ("F0", full, dict(white="model", corr=None, gm=None)),
           "T": ("F2x", simple, dict(white="model", corr="c0", gm=None)), "S+T": ("F1", full, dict(white="model", corr="C", gm=None)),
           "F2": ("F2x", full, dict(white="model", corr="c0", gm=("table",)))}
    for r in ROUTES:
        p, truth, T = get(r, seed); bh = bin3(rho_hat(p["z"][:, 0])); ps = sweep_packet(p, _G["g"].predict(T[EXIST]), np.zeros(len(T)), _G["Rrr"][bh], np.array(RV["Rss"])[bh]); res[r] = {}
        for a, (arm, tab, mode) in cfg.items():
            t = M.replay_m8(ps, _G["eR"], arm, table=tab, sigma_b=ZERO_SB, condition="B0", mu_s_fn=lambda nav, distance, i: 0.0, **mode)
            rw = np.asarray(ft(t, truth)); b = bm(t, truth, p["t"])
            res[r][a] = dict(n=len(rw), sums=rw.sum(0).tolist(), mirror=int(b["mirror_fail_count"]), xy_p95_cm=100 * float(np.quantile(np.hypot(t["x"][:, 0] - truth[:, 0], t["x"][:, 1] - truth[:, 1]), .95)),
                             head_p95=float(np.quantile(np.abs(np.degrees((t["x"][:, 2] - truth[:, 2] + np.pi) % (2 * np.pi) - np.pi)), .95)))
    os.makedirs(os.path.dirname(f), exist_ok=True); json.dump(res, open(f, "w")); return seed, "done", time.time() - t0
if __name__ == "__main__":
    with Pool(2, initializer=init) as pool:
        for s, st, dt in pool.imap_unordered(job, range(10, 30)): print(json.dumps(dict(seed=s, status=st, sec=round(dt, 1))), flush=True)
