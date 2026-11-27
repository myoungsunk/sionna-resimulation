"""EXPLORATORY (post hoc, added after C0-C4 results): C5 = learned arc length in near bin only (0.104 m), default 1 m / 10 deg elsewhere."""
"""Corridor R2/R4/R5 first-pass temporal-correlation arms (plan tcorr_first): SWB fullco block, S0-id range, F2 path. C0-C4; refs H2, H2S."""
import sys, os, json, time, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0", "/home/claude/tc", "/home/claude/bb"]
ROUTES = ("R2", "R4", "R5"); REFS = ("H2", "H2S"); CAND = ["C5"]; ARMS = (*REFS, *CAND); OUT = "/home/claude/tc/out_c5"
FC = json.load(open("/home/claude/v0/V0_BLOCK_RSS.json"))["c1a2c0_reproduced"]
KC = dict(arc_m=[0.104, 0.094, 0.124], yaw_deg=[10., 12.15, 26.75]); RK = dict(f=[0.282, 0.499, 0.0], l_m=[0.025, 0.087, 0.073])
KN = dict(arc_m=[0.104, 1.0, 1.0], yaw_deg=[10., 10., 10.])
MODE = {"C5": dict(kern=KN), "C0": {}, "C1": dict(kern=KC), "C2": dict(range_mode="skip_repeat"), "C3": dict(range_mode="ki", rk=RK), "C4": dict(kern=KC, range_mode="ki", rk=RK)}
def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import packet, TRUTH, env, scorers, m7_kwargs, R7
    import h_ref as HR, sw_block_fullco as SB, m8x_t as MK
    from run_m8s3 import sweep_packet, ZERO_SB
    from m7_assess import COVERAGE, assess_group, assess_seed
    e0 = env(); eF = HR.swap_env(e0, HR.ffd_s_fn(e0["model"])); eS = HR.swap_env(e0, SB.SWB().s_fn()); ft, swb, bm = scorers(); t0 = time.time()
    B0id = np.load("/home/claude/lut0/S0ID_CAL.npz"); truth, times, rows, br, rng = {}, {}, {}, {}, {}
    for r in ROUTES:
        p = packet(cond, seed, r); truth[r] = TRUTH[r]["truth"]; times[r] = p["t"]; tr = {}
        tr["H2"] = R7.replay(p, eF, "H2", **m7_kwargs("H2", r, cond, "own"))
        ps0 = sweep_packet(p, B0id[f"{r}/mu_r"], B0id[f"{r}/mu_s"], B0id[f"{r}/Rrr"], B0id[f"{r}/Rss"])
        tr["H2S"] = R7.replay(ps0, eF, "H2", sigma_b=ZERO_SB, condition=cond, rref_policy="own", sigma_rad=0.)
        psz = sweep_packet(p, B0id[f"{r}/mu_r"], np.zeros_like(B0id[f"{r}/mu_s"]), B0id[f"{r}/Rrr"], B0id[f"{r}/Rss"])
        for a in CAND:
            tr[a] = MK.replay_m8(psz, eS, "F2x", table=FC, sigma_b=ZERO_SB, condition=cond, mu_s_fn=lambda nav, distance, i: 0.0,
                                 white="model", corr="c0", gm=("table",), **MODE[a])
        rows[r] = {a: np.asarray(ft(tr[a], truth[r])) for a in ARMS}; br[r] = {a: bm(tr[a], truth[r], times[r]) for a in ARMS}
        rng[r] = {a: dict(rr_infl_med=float(np.median(tr[a]["Reff"][:, 0, 0] / tr[a]["R_ref"][:, 0, 0])), skipped=float(np.mean(tr[a]["Reff"][:, 0, 0] > 1e5))) for a in CAND}
    sc = swb(rows, times, [(a, ref) for ref in REFS for a in ARMS if a != ref], blocks=(5, 10, 20))
    point, b10 = sc["point"], sc["blocks"]["10"]; assessed = {}
    for arm in ARMS:
        groups = {}
        for g in (*ROUTES, "pooled"):
            ci = b10["by_group"][g]; lower = {m: ci["absolute_ci95"][arm][m][0] for m in COVERAGE}; pooled = g == "pooled"
            mir = sum(br[q][arm]["mirror_fail_count"] for q in ROUTES) if pooled else br[g][arm]["mirror_fail_count"]
            nb = min(b10["full_blocks"].values()) if pooled else b10["full_blocks"][g]
            groups[g] = assess_group(point[g][arm], lower, point[g]["H2S"], pooled=pooled, effective_blocks=nb, reference_only=bool(ci["reference_only"]), mirror_fail=mir)
        sa = assess_seed(seed if 10 <= seed < 30 else 10, groups); assessed[arm] = dict(I_seed=bool(sa["I_seed"]))
    os.makedirs(d, exist_ok=True)
    json.dump(dict(point=point, I=assessed, mirror={r: {a: br[r][a]["mirror_fail_count"] for a in ARMS} for r in ROUTES}, range=rng),
              open(d + "/GROUP.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
    return key, "done", time.time() - t0
if __name__ == "__main__":
    nw = int(sys.argv[1]); keys = [("B0", s) for s in range(10, 30)] if len(sys.argv) < 3 else [("B0", int(sys.argv[2]))]
    with Pool(nw, maxtasksperchild=1) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
