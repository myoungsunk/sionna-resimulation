"""C0-1 / C0-3 replays (Corridor). Arms H2, H2S, F2SKRWV only; same code path as run_m8s3.job, with the swappable
observation interface (h_ref = FFD). Scored with the pinned M7 functions; compared against the stored S0 GROUP.json.
  C01 : interface pass-through test (S0 calibration)            seeds 10 and 30, B0  -> must be bit-identical
  C03 : S0-id (calibration refit on e_s = s_full - h_FFD)      seeds 10-29, B0 + L2 -> same decisions, |score diff| <= 1e-3"""
import sys, os, json, time, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut0")
OUT = "/home/claude/lut0/out_c0"; ARMS = ("H2", "H2S", "F2SKRWV"); REFS = ("H2", "H2S"); ROUTES = ("R2", "R4", "R5")
EDG = np.array([0, 3, 6, 10])


def krige_fn(es, far_mu_s, near_limit=6.0):
    SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["e_s"] = es; SW["psi"] = np.radians(SW.yaw_deg)
    SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2); P = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json"))
    BI = {b: dict(X=SW[SW.b == b][["x_eval", "y_eval", "psi"]].to_numpy(), y=SW[SW.b == b].e_s.to_numpy(), mu0=float(SW[SW.b == b].e_s.mean()),
                  prm=P[f"e_s|{b}"]["params"]) for b in range(3)}
    wrap = lambda a: (a + np.pi) % (2 * np.pi) - np.pi
    def kr(x, y, psi, rho, maxn=150):
        b = int(np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2)); B = BI[b]; lx, ly, lp, nug = B["prm"]; X = B["X"]
        d = np.abs(X[:, 0] - x) / lx + np.abs(X[:, 1] - y) / ly + np.abs(wrap(X[:, 2] - psi)) / lp
        idx = np.argpartition(d, maxn)[:maxn]; Xi = X[idx]
        K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
        w = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-d[idx])); return B["mu0"] + w @ (B["y"][idx] - B["mu0"])
    return lambda nav, distance, i: float(kr(nav[0], nav[1], nav[2], distance)) if distance < near_limit else float(far_mu_s[i])


def job(key):
    variant, cond, seed = key; d = f"{OUT}/{variant}/{cond}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import packet, TRUTH, env, scorers, m7_kwargs, R7
    import m8_replay as M, krige_online as KO, h_ref as HR
    from run_m8s3 import sweep_packet, ZERO_SB
    from m7_assess import COVERAGE, assess_group, assess_seed
    e0 = env(); e = HR.swap_env(e0, HR.ffd_s_fn(e0["model"])); ft, swb, bm = scorers(); t0 = time.time()
    if variant == "C01":
        B = np.load("/home/claude/m8cal/SWEEP_CAL_B.npz"); VT = json.load(open("/home/claude/m8cal/SWEEP_TABLE_V.json")); kfn = lambda ms: KO.make_fn(ms)
    else:
        B = np.load("/home/claude/lut0/S0ID_CAL.npz"); VT = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
        es = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); kfn = lambda ms: krige_fn(es, ms)
    vtab = dict(edges=VT["edges"], c1=VT["c1"], c0=VT["c0"])
    traces, truth, times, rows, br = {}, {}, {}, {}, {}
    for r in ROUTES:
        p = packet(cond, seed, r); truth[r] = TRUTH[r]["truth"]; times[r] = p["t"]; tr = {}
        tr["H2"] = R7.replay(p, e, "H2", **m7_kwargs("H2", r, cond, "own"))
        ps = sweep_packet(p, B[f"{r}/mu_r"], B[f"{r}/mu_s"], B[f"{r}/Rrr"], B[f"{r}/Rss"])
        tr["H2S"] = R7.replay(ps, e, "H2", sigma_b=ZERO_SB, condition=cond, rref_policy="own", sigma_rad=0.)
        tr["F2SKRWV"] = M.replay_m8(ps, e, "F2SKRWV", table=vtab, sigma_b=ZERO_SB, condition=cond, mu_s_fn=kfn(B[f"{r}/mu_s"]), **M.ARM_MODES["F2"])
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
    keys = [("C01", "B0", 10), ("C01", "B0", 30)] if sys.argv[1] == "C01" else [("C03", c, s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)]
    with Pool(2) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
