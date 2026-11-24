"""SWB ablation: sensitivity term (S) vs time correlation (T). Fixed: SWB block (fullco), mu_s = 0, U3 mu_r, R_rr distance-bin table (V1).
 B    : white R_ss = c0_simple (bin total variance)                    [= V1 H2S-SWB]   S0 T0
 S    : white R_ss = c1(rho) a^2 + c0(rho)                                                 S1 T0
 T    : R_ss = c0_simple + KI accumulation (1 m / 10 deg kernel, 10 s)                    S0 T1
 S+T  : R_ss = (c1 a^2 + c0) + KI accumulation  (M8 F1)                                    S1 T1 (KI)
 GM   : GM heading-bias state (load a*sqrt(c1), 1 m / 10 deg), white R_ss = c0            S1 as correlated state, residual white
 F2   : GM state + R_ss = c0 + KI  (= SWB-c filter structure)                             S1 T1 (GM + KI)
dev seeds 10-29, B0 / L2_GYRO_ARW, routes R2 R4 R5."""
import sys, os, json, time, pickle, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/v1"); from v1_common import *
OUT = "/home/claude/v1/out_abl"; _G = {}
FC = json.load(open("/home/claude/v0/V0_BLOCK_RSS.json"))["c1a2c0_reproduced"]
def init():
    from common import env, scorers; import h_ref as HR, sw_block_fullco as SB
    g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); F = pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
    e = env(); _G.update(g=g, Rrr=np.array(Rrr), Rss=np.array(Rss), F=F, eS=HR.swap_env(e, SB.SWB().s_fn()), sc=scorers())
def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/RES.json"): return key, "reuse", 0
    from common import packet, TRUTH; from run_m8s3 import sweep_packet, ZERO_SB; import m8x as M
    ft, swb, bm = _G["sc"]; t0 = time.time(); res = {}
    simple = dict(edges=E3.tolist(), c1=[0.] * 3, c0=_G["Rss"].tolist()); full = dict(edges=E3.tolist(), c1=FC["c1"], c0=FC["c0"])
    cfg = {"B": ("F0", simple, dict(white="model", corr=None, gm=None)), "S": ("F0", full, dict(white="model", corr=None, gm=None)),
           "T": ("F2x", simple, dict(white="model", corr="c0", gm=None)), "S+T": ("F1", full, dict(white="model", corr="C", gm=None)),
           "GM": ("GMx", full, dict(white="c0", corr=None, gm=("table",))), "F2": ("F2x", full, dict(white="model", corr="c0", gm=("table",)))}
    for r in ("R2", "R4", "R5"):
        p = packet(cond, seed, r); T = _G["F"][_G["F"].case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
        bh = bin3(rho_hat(p["z"][:, 0])); ps = sweep_packet(p, _G["g"].predict(T[EXIST]), np.zeros(len(T)), _G["Rrr"][bh], _G["Rss"][bh])
        truth = TRUTH[r]["truth"]; res[r] = {}
        for a, (arm, tab, mode) in cfg.items():
            t = M.replay_m8(ps, _G["eS"], arm, table=tab, sigma_b=ZERO_SB, condition=cond, mu_s_fn=lambda nav, distance, i: 0.0, **mode)
            rows = np.asarray(ft(t, truth)); b = bm(t, truth, p["t"])
            res[r][a] = dict(n=len(rows), sums=rows.sum(0).tolist(), mirror=int(b["mirror_fail_count"]),
                             hbias_deg=float(np.degrees(np.mean((t["x"][:, 2] - truth[:, 2] + np.pi) % (2 * np.pi) - np.pi))),
                             s_infl_med=float(np.median(t["Reff"][:, 1, 1])), accept=float(np.mean(t["mask"])))
    os.makedirs(d, exist_ok=True); json.dump(res, open(d + "/RES.json", "w")); return key, "done", time.time() - t0
if __name__ == "__main__":
    keys = [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)]
    with Pool(2, initializer=init) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
