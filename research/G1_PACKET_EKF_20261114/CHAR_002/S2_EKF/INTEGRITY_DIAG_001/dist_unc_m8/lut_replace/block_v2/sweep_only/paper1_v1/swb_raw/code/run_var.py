"""Block variants without distance-specific processing: SWB-AVG (all stations = +-3 col x 5 line average), SWB-RAW (all stations = measured curve).
Range channel as V1 (U3 mu_r, R_rr by rho_hat bin); R_ss = own column-out mean-square by prior-rho bin; white G0 (F0, c1 = 0). B0, dev seeds 10-29, routes R2/R4/R5 + N1-N6."""
import sys, os, json, time, pickle, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/v1"); from v1_common import *
OUT = "/home/claude/v1/out_var"; RV = json.load(open("/home/claude/v1/RSS_VARIANTS.json")); _G = {}
NR = [f"N{i}" for i in range(1, 7)]; RR = ["R2", "R4", "R5"]
def init():
    from common import env, scorers; import h_ref as HR, sw_block_allavg as BA, sw_block_allraw as BR
    g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); e = env()
    FN = pd.read_csv("/home/claude/n1n6/cir_features/OBSERVATION_FEATURES.csv.gz"); FR = pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); FR = FR[FR.channel == "full"]
    _G.update(g=g, Rrr=np.array(Rrr), FN=FN, FR=FR, envs={"SWB-AVG": HR.swap_env(e, BA.SWB().s_fn()), "SWB-RAW": HR.swap_env(e, BR.SWB().s_fn())}, sc=scorers())
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
    from run_m8s3 import sweep_packet, ZERO_SB; import m8_replay as M
    ft, swb, bm = _G["sc"]; t0 = time.time(); res = {}
    for r in RR + NR:
        p, truth, T = get(r, seed); bh = bin3(rho_hat(p["z"][:, 0])); mu = _G["g"].predict(T[EXIST]); res[r] = {}
        for a, key in (("SWB-AVG", "allavg"), ("SWB-RAW", "allraw")):
            Rs = np.array(RV[key]["Rss"]); ps = sweep_packet(p, mu, np.zeros(len(mu)), _G["Rrr"][bh], Rs[bh])
            t = M.replay_m8(ps, _G["envs"][a], "F0", table=dict(edges=E3.tolist(), c1=[0.] * 3, c0=Rs.tolist()), sigma_b=ZERO_SB, condition="B0", **M.ARM_MODES["F0"])
            rw = np.asarray(ft(t, truth)); b = bm(t, truth, p["t"])
            res[r][a] = dict(n=len(rw), sums=rw.sum(0).tolist(), mirror=int(b["mirror_fail_count"]))
    os.makedirs(os.path.dirname(f), exist_ok=True); json.dump(res, open(f, "w")); return seed, "done", time.time() - t0
if __name__ == "__main__":
    with Pool(2, initializer=init) as pool:
        for s, st, dt in pool.imap_unordered(job, range(10, 30)): print(json.dumps(dict(seed=s, status=st, sec=round(dt, 1))), flush=True)
