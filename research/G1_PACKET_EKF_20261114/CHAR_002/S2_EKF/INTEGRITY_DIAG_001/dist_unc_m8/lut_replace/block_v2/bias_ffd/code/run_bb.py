"""Bias-aware FFD corridor replays (plan PLAN_BIAS_FFD_KO.md). F2 code path, range channel = S0-id (mu_r, R_rr), mu_s = 0 except kriging arms.
arms: BV0, BVK (parity with stored run), P0 (scalar bin offset), P1 (heading-type bin x side mean), P2 (P1 + near kriging),
      P3 (BVK + per-bin kernel lengths), P4 (BVK, far-bin correlation off). refs H2, H2S (scoring).
usage: run_bb.py [n_workers]"""
import sys, os, json, time, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0", "/home/claude/lut3", "/home/claude/bb"]
ROUTES = ("R2", "R4", "R5"); REFS = ("H2", "H2S"); EDG = np.array([0, 3, 6, 10.])
CAND = ["BV0", "BVK", "P0", "P1", "P2", "P3", "P4"]; ARMS = ("H2", "H2S", *CAND); OUT = "/home/claude/bb/out"
KERN = dict(arc_m=[0.4, 0.15, 0.15], yaw_deg=[25., 20., 15.])


def krige_fn(es, prm, near_limit=3.0):
    SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["e_s"] = es; SW["psi"] = np.radians(SW.yaw_deg)
    q = SW.rho.values < near_limit; X = SW[q][["x_eval", "y_eval", "psi"]].to_numpy(); y = SW[q].e_s.to_numpy(); mu0 = float(y.mean())
    import bb_block as BB
    return lambda nav, distance, i: float(BB.kr_one(X, y, mu0, (nav[0], nav[1], nav[2]), prm)) if distance < near_limit else 0.0


def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import packet, TRUTH, env, scorers, m7_kwargs, R7
    import h_ref as HR, bb_block as BB, m8_replay_k as MK, m8_replay as M
    from run_m8s3 import sweep_packet, ZERO_SB
    from m7_assess import COVERAGE, assess_group, assess_seed
    e0 = env(); base = e0["model"]; spec = e0["spec"]; ffd = HR.ffd_s_fn(base); eF = HR.swap_env(e0, ffd); ft, swb, bm = scorers(); t0 = time.time()
    SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); TB = json.load(open("/home/claude/bb/BB_TABLES.json"))
    prm0 = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json"))["e_s|0"]["params"]
    blk = {"BV0": BB.BB(ffd, spec, SW, field="zero"), "BV": BB.BB(ffd, spec, SW, field="smooth"),
           "P0": BB.BB(ffd, spec, SW, field="zero", off="bin"), "P1": BB.BB(ffd, spec, SW, field="bin", off="bin")}
    use = {"BV0": "BV0", "BVK": "BV", "P0": "P0", "P1": "P1", "P2": "P1", "P3": "BV", "P4": "BV"}
    tabk = {"BV0": "BV0", "BVK": "BVK", "P0": "P0", "P1": "P1", "P2": "P2", "P3": "BVK", "P4": "BVK"}
    envs = {a: HR.swap_env(e0, blk[use[a]].s_fn()) for a in CAND}
    kf = {"BV": krige_fn(np.load("/home/claude/bb/ES_BV.npy"), prm0), "P1": krige_fn(np.load("/home/claude/bb/ES_P1.npy"), prm0)}
    zero = lambda nav, distance, i: 0.0
    mus = {"BV0": zero, "P0": zero, "P1": zero, "BVK": kf["BV"], "P2": kf["P1"], "P3": kf["BV"], "P4": kf["BV"]}
    extra = {"P3": dict(kern=KERN), "P4": dict(far_corr_off=True)}
    B0id = np.load("/home/claude/lut0/S0ID_CAL.npz")
    truth, times, rows, br, diag = {}, {}, {}, {}, {}
    for r in ROUTES:
        p = packet(cond, seed, r); truth[r] = TRUTH[r]["truth"]; times[r] = p["t"]; tr = {}
        tr["H2"] = R7.replay(p, eF, "H2", **m7_kwargs("H2", r, cond, "own"))
        ps0 = sweep_packet(p, B0id[f"{r}/mu_r"], B0id[f"{r}/mu_s"], B0id[f"{r}/Rrr"], B0id[f"{r}/Rss"])
        tr["H2S"] = R7.replay(ps0, eF, "H2", sigma_b=ZERO_SB, condition=cond, rref_policy="own", sigma_rad=0.)
        psz = sweep_packet(p, B0id[f"{r}/mu_r"], np.zeros_like(B0id[f"{r}/mu_s"]), B0id[f"{r}/Rrr"], B0id[f"{r}/Rss"])
        for a in CAND:
            tr[a] = MK.replay_m8(psz, envs[a], "F2SKRWV", table=TB[tabk[a]], sigma_b=ZERO_SB, condition=cond, mu_s_fn=mus[a],
                                 **M.ARM_MODES["F2"], **extra.get(a, {}))
        rows[r] = {a: np.asarray(ft(tr[a], truth[r])) for a in ARMS}; br[r] = {a: bm(tr[a], truth[r], times[r]) for a in ARMS}
        T = truth[r]; rho = np.hypot(T[:, 0] - 10., T[:, 1]); b = np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2); diag[r] = {}
        for a in ARMS:
            eh = (tr[a]["x"][:, 2] - T[:, 2] + np.pi) % (2 * np.pi) - np.pi; z = eh / np.sqrt(tr[a]["P"][:, 2, 2])
            diag[r][a] = dict(hbias_deg=float(np.degrees(eh.mean())), by_bin={str(i): dict(n=int((b == i).sum()), hbias_deg=float(np.degrees(eh[b == i].mean())),
                              hrms_deg=float(np.degrees(np.sqrt(np.mean(eh[b == i] ** 2)))), zrms=float(np.sqrt(np.mean(z[b == i] ** 2)))) for i in range(3) if (b == i).any()})
    sc = swb(rows, times, [(a, ref) for ref in REFS for a in ARMS if a != ref], blocks=(5, 10, 20))
    point, b10 = sc["point"], sc["blocks"]["10"]; assessed = {ref: {} for ref in REFS}
    for ref in REFS:
        for arm in ARMS:
            groups = {}
            for g in (*ROUTES, "pooled"):
                ci = b10["by_group"][g]; lower = {m: ci["absolute_ci95"][arm][m][0] for m in COVERAGE}; pooled = g == "pooled"
                mir = sum(br[q][arm]["mirror_fail_count"] for q in ROUTES) if pooled else br[g][arm]["mirror_fail_count"]
                nb = min(b10["full_blocks"].values()) if pooled else b10["full_blocks"][g]
                groups[g] = assess_group(point[g][arm], lower, point[g][ref], pooled=pooled, effective_blocks=nb,
                                         reference_only=bool(ci["reference_only"]), mirror_fail=mir)
            sa = assess_seed(seed if 10 <= seed < 30 else 10, groups); sa["seed"] = seed; assessed[ref][arm] = sa
    os.makedirs(d, exist_ok=True)
    json.dump(dict(point=point, seed_assessments=assessed, diag=diag, mirror={r: {a: br[r][a]["mirror_fail_count"] for a in ARMS} for r in ROUTES}),
              open(d + "/GROUP.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
    return key, "done", time.time() - t0


if __name__ == "__main__":
    nw = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    keys = [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)] if len(sys.argv) < 3 else [("B0", int(sys.argv[2]))]
    with Pool(nw) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
