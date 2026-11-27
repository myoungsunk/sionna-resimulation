"""EXPLORATORY (post hoc): N-F2 with N2-N6 learned near arc length only."""
"""N1 mirror diagnostics (B0, seeds 10-29), V1 range, SWB fullco: N-B, N-T, N-F2 (ABL parity), N-T-near0, N-F2-near0, N-F2-K (kernel from N2-N6).
Info diagnostic: accepted-update y-information sum(H[:,1]^2 / diag(R_eff)) over the first 15 s."""
import sys, os, json, time, pickle, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path[:0] = ["/home/claude/v1", "/home/claude/tc"]; from v1_common import *
ROOT = "/home/claude/n1n6"; OUT = "/home/claude/tc/out_n1b"; FC = json.load(open("/home/claude/v0/V0_BLOCK_RSS.json"))["c1a2c0_reproduced"]; _G = {}
KN1 = dict(arc_m=[0.096, 1.0, 1.0], yaw_deg=[10., 10., 10.])
def init():
    from common import env, scorers; import h_ref as HR, sw_block_fullco as SB
    g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); F = pd.read_csv(f"{ROOT}/cir_features/OBSERVATION_FEATURES.csv.gz")
    e = env(); r = "N1"; rf = dict(np.load(f"{ROOT}/v1_h2_inputs/{r}_aB_m0.npz")); ev = dict(np.load(f"{ROOT}/v1_controls/{r}_evaluator.npz"))
    rows = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[rf["pose_id"]]; assert np.max(np.abs(rows[["range_m", "s_fp"]].to_numpy() - rf["z"])) < 1e-12
    _G.update(g=g, Rrr=np.array(Rrr), Rss=np.array(Rss), case=(rf, ev["truth"], rows), eS=HR.swap_env(e, SB.SWB().s_fn()), sc=scorers())
def job(seed):
    from run_m8s3 import sweep_packet, ZERO_SB; import m8x_t as M
    ft, swb, bm = _G["sc"]; rf, truth, rows = _G["case"]; t0 = time.time(); res = {}
    simple = dict(edges=E3.tolist(), c1=[0.] * 3, c0=_G["Rss"].tolist()); full = dict(edges=E3.tolist(), c1=FC["c1"], c0=FC["c0"])
    T = dict(white="model", corr="c0", gm=None); F2 = dict(white="model", corr="c0", gm=("table",))
    cfg = {"N-F2-Knear": ("F2x", full, dict(F2, kern=KN1))}
    p = dict(np.load(f"{ROOT}/v1_controls/B0/seed{seed}/N1_controls.npz")); p.update({k: rf[k] for k in ("z", "muMB", "muBASE", "R", "D")})
    bh = bin3(rho_hat(p["z"][:, 0])); ps = sweep_packet(p, _G["g"].predict(rows[EXIST]), np.zeros(len(rows)), _G["Rrr"][bh], _G["Rss"][bh])
    for a, (arm, tab, mode) in cfg.items():
        t = M.replay_m8(ps, _G["eS"], arm, table=tab, sigma_b=ZERO_SB, condition="B0", mu_s_fn=lambda nav, distance, i: 0.0, **mode)
        rw = np.asarray(ft(t, truth)); b = bm(t, truth, p["t"]); k = (p["t"] - p["t"][0] <= 15.) & t["mask"]
        Hy = t["H"][:, :, 1]; Rd = np.stack([t["Reff"][:, 0, 0], t["Reff"][:, 1, 1]], 1)
        iy = (Hy**2 / Rd)[k]; eh = np.degrees((t["x"][:, 2] - truth[:, 2] + np.pi) % (2 * np.pi) - np.pi); ey = t["x"][:, 1] - truth[:, 1]
        res[a] = dict(n=len(rw), sums=rw.sum(0).tolist(), mirror=int(b["mirror_fail_count"]), info_y_r=float(iy[:, 0].sum()), info_y_s=float(iy[:, 1].sum()),
                      ey_end15=float(ey[p["t"] - p["t"][0] <= 15.][-1]), sy_end15=float(np.sqrt(t["P"][p["t"] - p["t"][0] <= 15.][-1][1, 1])), h_rmse=float(np.sqrt(np.mean(eh**2))),
                      xy_rmse_cm=float(100 * np.sqrt(np.mean(np.sum((t["x"][:, :2] - truth[:, :2])**2, 1)))))
    return seed, res, time.time() - t0
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True); allr = {}
    with Pool(2, initializer=init) as pool:
        for s, res, dt in pool.imap_unordered(job, range(10, 30)): allr[s] = res; print(json.dumps(dict(seed=s, sec=round(dt, 1))), flush=True)
    json.dump(allr, open(f"{OUT}/N1_RES.json", "w"))
