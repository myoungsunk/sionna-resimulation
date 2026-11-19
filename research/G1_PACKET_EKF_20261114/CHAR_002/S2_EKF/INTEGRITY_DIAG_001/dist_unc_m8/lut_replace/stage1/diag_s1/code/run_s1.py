"""Stage 1 diagnostic replays (amendment 02 B2): dev seeds 10-29, B0 + L2. DIAGNOSTIC ONLY.
Arms (F2SKRWV code path, S0-id calibration = labels e_s = s_full - h_FFD, S0-id tables, kriging on S0-id labels):
  S1h : EMP h and Jacobian (SwapS), loading sensitivity a from FFD
  S1a : FFD h and Jacobian, loading sensitivity a from EMP
  S1  : EMP h, Jacobian and a
H2 / H2S replayed with FFD (references). S0-id F2SKRWV taken from lut0/out_c0/C03."""
import sys, os, json, time, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut0"); sys.path.insert(0, "/home/claude/lut1")
OUT = "/home/claude/lut1/out_s1"; ARMS = ("H2", "H2S", "S1h", "S1a", "S1"); REFS = ("H2", "H2S"); ROUTES = ("R2", "R4", "R5")


def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import packet, TRUTH, env, scorers, m7_kwargs, R7
    import m8_replay_lut as M, h_ref as HR
    from run_m8s3 import sweep_packet, ZERO_SB
    from m7_assess import COVERAGE, assess_group, assess_seed
    from run_c0 import krige_fn
    from emp_lut import EmpLUT
    lut = EmpLUT.from_dict(json.load(open("/home/claude/lut1/STAGE1_STATIC.json"))["lut"])
    e0 = env(); eF = HR.swap_env(e0, HR.ffd_s_fn(e0["model"])); eE = HR.swap_env(e0, lut.s_fn()); ft, swb, bm = scorers(); t0 = time.time()
    spec = e0["spec"]; base = e0["model"]
    aF = lambda nav: float(base.batch(np.asarray(nav, float)[None], spec)[1][0, 1, 2])
    aE = lambda nav: float(lut.eval(np.array([nav[0]]), np.array([nav[1]]), np.array([nav[2]]))[3][0])
    B = np.load("/home/claude/lut0/S0ID_CAL.npz"); VT = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
    es = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); vtab = dict(edges=VT["edges"], c1=VT["c1"], c0=VT["c0"])
    traces, truth, times, rows, br = {}, {}, {}, {}, {}
    for r in ROUTES:
        p = packet(cond, seed, r); truth[r] = TRUTH[r]["truth"]; times[r] = p["t"]; tr = {}
        tr["H2"] = R7.replay(p, eF, "H2", **m7_kwargs("H2", r, cond, "own"))
        ps = sweep_packet(p, B[f"{r}/mu_r"], B[f"{r}/mu_s"], B[f"{r}/Rrr"], B[f"{r}/Rss"])
        tr["H2S"] = R7.replay(ps, eF, "H2", sigma_b=ZERO_SB, condition=cond, rref_policy="own", sigma_rad=0.)
        kw = dict(table=vtab, sigma_b=ZERO_SB, condition=cond, mu_s_fn=krige_fn(es, B[f"{r}/mu_s"]), **M.ARM_MODES["F2"])
        tr["S1h"] = M.replay_m8(ps, eE, "F2SKRWV", a_fn=aF, **kw)
        tr["S1a"] = M.replay_m8(ps, eF, "F2SKRWV", a_fn=aE, **kw)
        tr["S1"] = M.replay_m8(ps, eE, "F2SKRWV", **kw)
        traces[r] = tr; rows[r] = {a: np.asarray(ft(tr[a], truth[r])) for a in ARMS}; br[r] = {a: bm(tr[a], truth[r], times[r]) for a in ARMS}
    sc = swb(rows, times, [(a, ref) for ref in REFS for a in ARMS if a != ref], blocks=(5, 10, 20))
    point, b10 = sc["point"], sc["blocks"]["10"]; assessed = {ref: {} for ref in REFS}
    for ref in REFS:
        for arm in ARMS:
            groups = {}
            for g in (*ROUTES, "pooled"):
                ci = b10["by_group"][g]; lower = {m: ci["absolute_ci95"][arm][m][0] for m in COVERAGE}; pooled = g == "pooled"
                mir = sum(br[q][arm]["mirror_fail_count"] for q in ROUTES) if pooled else br[g][arm]["mirror_fail_count"]
                blocks = min(b10["full_blocks"].values()) if pooled else b10["full_blocks"][g]
                groups[g] = assess_group(point[g][arm], lower, point[g][ref], pooled=pooled, effective_blocks=blocks,
                                         reference_only=bool(ci["reference_only"]), mirror_fail=mir)
            sa = assess_seed(seed if 10 <= seed < 30 else 10, groups); sa["seed"] = seed; assessed[ref][arm] = sa
    os.makedirs(d, exist_ok=True)
    json.dump(dict(point=point, ci10={g: b10["by_group"][g] for g in (*ROUTES, "pooled")}, seed_assessments=assessed,
                   mirror={r: {a: br[r][a]["mirror_fail_count"] for a in ARMS} for r in ROUTES}), open(d + "/GROUP.json", "w"),
              default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
    return key, "done", time.time() - t0


if __name__ == "__main__":
    keys = [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)]
    with Pool(2) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
