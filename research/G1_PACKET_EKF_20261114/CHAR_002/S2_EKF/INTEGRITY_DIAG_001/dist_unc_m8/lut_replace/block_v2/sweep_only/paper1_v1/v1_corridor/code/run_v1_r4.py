"""V1 runner. usage: run_v1.py dev|confirm. Arms per route (R2, R5):
 H0 (DR, M7) | H1S (range-only, U3 mu_r, Rrr table) | H2S-SWB (G0 white: F0 with c1=0, c0=Rss simple; SWB block; U3 mu_r; Rrr table)
 diag: H2S-SWB-U0 (mu_r = 0) | ref: H2 (M7 LORO, FFD)."""
import sys, os, json, time, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/v1"); from v1_common import *
ROUTES = ("R4",); ARMS = ("H0", "H1S", "H2S-SWB", "H2S-SWB-U0", "H2")
OUT = "/home/claude/v1/out_r4"; _G = {}
def init():
    from common import env, scorers; import h_ref as HR, sw_block_fullco as SB
    import pickle; g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); F = pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
    e = env(); _G.update(g=g, Rrr=np.array(Rrr), Rss=np.array(Rss), F=F, e=e, eS=HR.swap_env(e, SB.SWB().s_fn()), sc=scorers())
def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/RES.json"): return key, "reuse", 0
    if not _G: init()
    from common import packet, TRUTH, m7_kwargs, R7; from run_m8s3 import sweep_packet, ZERO_SB; import m8_replay as M
    ft, swb, bm = _G["sc"]; t0 = time.time(); res = {}
    for r in ROUTES:
        p = packet(cond, seed, r); T = _G["F"][_G["F"].case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
        bh = bin3(rho_hat(p["z"][:, 0])); mu = _G["g"].predict(T[EXIST]); Rr = _G["Rrr"][bh]; Rs = _G["Rss"][bh]; z0 = np.zeros(len(mu))
        ps = sweep_packet(p, mu, z0, Rr, Rs); p0 = sweep_packet(p, z0, z0, Rr, Rs)
        tab = dict(edges=E3.tolist(), c1=[0., 0., 0.], c0=_G["Rss"].tolist())
        tr = {"H0": R7.replay(p, _G["e"], "H0", **m7_kwargs("H0", r, cond)),
              "H1S": R7.replay(ps, _G["e"], "H1", sigma_b=ZERO_SB, condition=cond, rref_policy="own", sigma_rad=0.),
              "H2S-SWB": M.replay_m8(ps, _G["eS"], "F0", table=tab, sigma_b=ZERO_SB, condition=cond, **M.ARM_MODES["F0"]),
              "H2S-SWB-U0": M.replay_m8(p0, _G["eS"], "F0", table=tab, sigma_b=ZERO_SB, condition=cond, **M.ARM_MODES["F0"]),
              "H2": R7.replay(p, _G["e"], "H2", **m7_kwargs("H2", r, cond))}
        truth = TRUTH[r]["truth"]; res[r] = {}
        for a, t in tr.items():
            rows = np.asarray(ft(t, truth)); b = bm(t, truth, p["t"])
            hb = float(np.degrees(np.mean((t["x"][:, 2] - truth[:, 2] + np.pi) % (2 * np.pi) - np.pi)))
            res[r][a] = dict(n=len(rows), sums=rows.sum(0).tolist(), mirror=int(b["mirror_fail_count"]), hbias_deg=hb,
                             accept=float(np.mean(t["mask"])) if "mask" in t else None)
    os.makedirs(d, exist_ok=True); json.dump(res, open(d + "/RES.json", "w")); return key, "done", time.time() - t0
if __name__ == "__main__":
    seeds = range(10, 30) if sys.argv[1] == "dev" else range(70, 90)
    keys = [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in seeds]
    with Pool(int(sys.argv[2]) if len(sys.argv) > 2 else 4, initializer=init) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
