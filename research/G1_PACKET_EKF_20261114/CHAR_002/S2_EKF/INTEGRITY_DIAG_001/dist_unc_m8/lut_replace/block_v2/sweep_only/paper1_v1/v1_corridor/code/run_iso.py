"""V1 failure branch (pre-declared order mu_r -> R_rr -> far block). dev seeds 10-29, R2+R5, B0/L2.
A: U3 mu_r, Rrr mean-square (=V1 H2S-SWB) | B: U3, Rrr robust (MAD) | C: U3, Rrr mean-square, far block = station curve (Rss far from its col-out) | D: U0, Rrr mean-square."""
import sys, os, json, time, pickle, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/v1"); from v1_common import *
OUT = "/home/claude/v1/out_iso"; _G = {}
def init():
    from common import env, scorers; import h_ref as HR, sw_block_fullco as SB, sw_block_farst as SF
    g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); F = pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
    e = env(); _G.update(g=g, Rrr=np.array(Rrr), Rrob=np.array(json.load(open("/home/claude/v1/RRR_ROBUST_U3.json"))["Rrr_robust"]), Rss=np.array(Rss),
        RssF=np.array(json.load(open("/home/claude/v1/RSS_FARST.json"))["Rss"]), F=F, eS=HR.swap_env(e, SB.SWB().s_fn()), eF=HR.swap_env(e, SF.SWB().s_fn()), sc=scorers())
def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/RES.json"): return key, "reuse", 0
    if not _G: init()
    from common import packet, TRUTH; from run_m8s3 import sweep_packet, ZERO_SB; import m8_replay as M
    ft, swb, bm = _G["sc"]; t0 = time.time(); res = {}
    for r in ("R2", "R5"):
        p = packet(cond, seed, r); T = _G["F"][_G["F"].case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
        bh = bin3(rho_hat(p["z"][:, 0])); mu = _G["g"].predict(T[EXIST]); z0 = np.zeros(len(mu))
        tabS = dict(edges=E3.tolist(), c1=[0.] * 3, c0=_G["Rss"].tolist()); tabF = dict(edges=E3.tolist(), c1=[0.] * 3, c0=_G["RssF"].tolist())
        cfg = {"A": (mu, _G["Rrr"], _G["eS"], tabS, _G["Rss"]), "B": (mu, _G["Rrob"], _G["eS"], tabS, _G["Rss"]),
               "C": (mu, _G["Rrr"], _G["eF"], tabF, _G["RssF"]), "D": (z0, _G["Rrr"], _G["eS"], tabS, _G["Rss"])}
        truth = TRUTH[r]["truth"]; res[r] = {}
        for a, (m, Rr, en, tb, Rs) in cfg.items():
            t = M.replay_m8(sweep_packet(p, m, z0, Rr[bh], Rs[bh]), en, "F0", table=tb, sigma_b=ZERO_SB, condition=cond, **M.ARM_MODES["F0"])
            rows = np.asarray(ft(t, truth)); b = bm(t, truth, p["t"])
            res[r][a] = dict(n=len(rows), sums=rows.sum(0).tolist(), mirror=int(b["mirror_fail_count"]),
                             hbias_deg=float(np.degrees(np.mean((t["x"][:, 2] - truth[:, 2] + np.pi) % (2 * np.pi) - np.pi))))
    os.makedirs(d, exist_ok=True); json.dump(res, open(d + "/RES.json", "w")); return key, "done", time.time() - t0
if __name__ == "__main__":
    keys = [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)]
    with Pool(2, initializer=init) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
