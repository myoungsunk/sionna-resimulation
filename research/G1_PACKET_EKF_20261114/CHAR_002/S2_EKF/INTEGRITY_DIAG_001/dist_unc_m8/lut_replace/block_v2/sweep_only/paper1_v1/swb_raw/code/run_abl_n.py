"""N1-N6 ablation (B0, dev seeds 10-29): arms B, S, T, S+T, F2 as in v1/run_ablate.py. Packets rebuilt as in code/run_n1_n6_v1.py (filter_one)."""
import sys, os, json, time, pickle, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/v1"); from v1_common import *
ROOT = "/home/claude/n1n6"; OUT = f"{ROOT}/out_abl"; FC = json.load(open("/home/claude/v0/V0_BLOCK_RSS.json"))["c1a2c0_reproduced"]; _G = {}
def init():
    from common import env, scorers; import h_ref as HR, sw_block_fullco as SB
    g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); F = pd.read_csv(f"{ROOT}/cir_features/OBSERVATION_FEATURES.csv.gz")
    e = env(); cases = {}
    for r in [f"N{i}" for i in range(1, 7)]:
        rf = dict(np.load(f"{ROOT}/v1_h2_inputs/{r}_aB_m0.npz")); ev = dict(np.load(f"{ROOT}/v1_controls/{r}_evaluator.npz"))
        rows = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[rf["pose_id"]]; assert np.max(np.abs(rows[["range_m", "s_fp"]].to_numpy() - rf["z"])) < 1e-12
        cases[r] = (rf, ev["truth"], rows)
    _G.update(g=g, Rrr=np.array(Rrr), Rss=np.array(Rss), cases=cases, eS=HR.swap_env(e, SB.SWB().s_fn()), sc=scorers())
def job(seed):
    d = f"{OUT}/B0/seed{seed}"
    if os.path.exists(d + "/RES.json"): return seed, "reuse", 0
    from run_m8s3 import sweep_packet, ZERO_SB; import m8x as M
    ft, swb, bm = _G["sc"]; t0 = time.time(); res = {}
    simple = dict(edges=E3.tolist(), c1=[0.] * 3, c0=_G["Rss"].tolist()); full = dict(edges=E3.tolist(), c1=FC["c1"], c0=FC["c0"])
    cfg = {"B": ("F0", simple, dict(white="model", corr=None, gm=None)), "S": ("F0", full, dict(white="model", corr=None, gm=None)),
           "T": ("F2x", simple, dict(white="model", corr="c0", gm=None)), "S+T": ("F1", full, dict(white="model", corr="C", gm=None)),
           "F2": ("F2x", full, dict(white="model", corr="c0", gm=("table",)))}
    for r, (rf, truth, rows) in _G["cases"].items():
        p = dict(np.load(f"{ROOT}/v1_controls/B0/seed{seed}/{r}_controls.npz")); assert np.array_equal(p["t"], rf["t"])
        p.update({k: rf[k] for k in ("z", "muMB", "muBASE", "R", "D")})
        bh = bin3(rho_hat(p["z"][:, 0])); ps = sweep_packet(p, _G["g"].predict(rows[EXIST]), np.zeros(len(rows)), _G["Rrr"][bh], _G["Rss"][bh]); res[r] = {}
        for a, (arm, tab, mode) in cfg.items():
            t = M.replay_m8(ps, _G["eS"], arm, table=tab, sigma_b=ZERO_SB, condition="B0", mu_s_fn=lambda nav, distance, i: 0.0, **mode)
            rw = np.asarray(ft(t, truth)); b = bm(t, truth, p["t"])
            res[r][a] = dict(n=len(rw), sums=rw.sum(0).tolist(), mirror=int(b["mirror_fail_count"]))
    os.makedirs(d, exist_ok=True); json.dump(res, open(d + "/RES.json", "w")); return seed, "done", time.time() - t0
if __name__ == "__main__":
    with Pool(2, initializer=init) as pool:
        for s, st, dt in pool.imap_unordered(job, range(10, 30)): print(json.dumps(dict(seed=s, status=st, sec=round(dt, 1))), flush=True)
