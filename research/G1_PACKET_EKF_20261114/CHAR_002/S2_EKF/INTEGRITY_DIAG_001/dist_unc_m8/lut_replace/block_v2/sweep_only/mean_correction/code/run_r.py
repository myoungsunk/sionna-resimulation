"""Stage 2 filter replays (plan section 6, amendment 02 B4/B5). F2SKRWV code path (m8_replay), env = FFD' via SwapS.
  2a_P   : FFD'_P, S0-id calibration (labels s_full - h_FFD), S0-id V table, kriging on S0-id labels, S0 hyperparameters
  2b_P   : FFD'_P, calibration rebuilt on s_full - h'_P (CAL_P.npz, STAGE2_STATIC.json tableV), kriging on ES_P, S0 hyperparameters
  2bcv_P1: as 2b_P1 with re-selected kriging hyperparameters
  S0id   : FFD, S0-id calibration (identical to lut0/out_c0/C03; confirm seeds only)
H2 / H2S replayed with FFD (references). Mean heading error (bias) stored per route and arm.
usage: run_s2.py dev | confirm\nCOPY (run_r.py): SWB-R = SWB block + S0-style mean correction on SWB labels (kriging < 6 m, POWER (b) >= 6 m), full column-out table, original range calibration, dev seeds 10-29."""
import sys, os, json, time, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut0"); sys.path.insert(0, "/home/claude/lut2"); sys.path.insert(0, "/home/claude/lut3"); sys.path.insert(0, "/home/claude/lut5")
ROUTES = ("R2", "R4", "R5"); REFS = ("H2", "H2S"); EDG = np.array([0, 3, 6, 10]); L2 = "/home/claude/lut2"
MODE = "bv"
CAND = ["SWB-R"]
ARMS = ("H2", "H2S", *CAND); OUT = "/home/claude/lut7/out_r"


def krige_fn(es, far_mu_s, prms, near_limit=6.0):
    SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["e_s"] = es; SW["psi"] = np.radians(SW.yaw_deg)
    SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2)
    BI = {b: dict(X=SW[SW.b == b][["x_eval", "y_eval", "psi"]].to_numpy(), y=SW[SW.b == b].e_s.to_numpy(), mu0=float(SW[SW.b == b].e_s.mean()), prm=prms[b]) for b in range(3)}
    wrap = lambda a: (a + np.pi) % (2 * np.pi) - np.pi
    def kr(x, y, psi, rho, maxn=150):
        b = int(np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2)); B = BI[b]; lx, ly, lp, nug = B["prm"]; X = B["X"]
        d = np.abs(X[:, 0] - x) / lx + np.abs(X[:, 1] - y) / ly + np.abs(wrap(X[:, 2] - psi)) / lp
        idx = np.argpartition(d, maxn)[:maxn]; Xi = X[idx]
        K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
        w = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-d[idx])); return B["mu0"] + w @ (B["y"][idx] - B["mu0"])
    return lambda nav, distance, i: float(kr(nav[0], nav[1], nav[2], distance)) if distance < near_limit else float(far_mu_s[i])


def arm_setup(arm):
    """-> (perturbation or None, CAL npz path, V table, label array, kriging params)"""
    KP = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); p0 = {k: KP[f"e_s|{k}"]["params"] for k in range(3)}
    ST = json.load(open(f"{L2}/STAGE2_STATIC.json")); V0 = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
    ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); C0 = "/home/claude/lut0/S0ID_CAL.npz"
    if arm == "S0id": return None, C0, V0, ES0, p0
    kind, P = arm.split("_")
    if kind == "2a": return P, C0, V0, ES0, p0
    if kind == "2b": return P, f"{L2}/CAL_{P}.npz", ST[P]["tableV"], np.load(f"{L2}/ES_{P}.npy"), p0
    pc = {int(k): v for k, v in ST["P1cv"]["krige_params"].items()}
    return P, f"{L2}/CAL_P1cv.npz", ST["P1cv"]["tableV"], np.load(f"{L2}/ES_P1.npy"), pc


def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import packet, TRUTH, env, scorers, m7_kwargs, R7
    import m8_replay as M, h_ref as HR, pert
    from run_m8s3 import sweep_packet, ZERO_SB
    from m7_assess import COVERAGE, assess_group, assess_seed
    e0 = env(); base = e0["model"]; eF = HR.swap_env(e0, HR.ffd_s_fn(base)); ft, swb, bm = scorers(); t0 = time.time()
    import bv_block as BVM, pandas as pd
    SWt = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); spec = e0["spec"]; ffd = HR.ffd_s_fn(base)
    import sw_block as SB
    TFC = json.load(open("/home/claude/lut5/TABLE_SWB_FULLCO.json")); V0 = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
    eS = HR.swap_env(e0, SB.SWB().s_fn()); CU = np.load("/home/claude/lut5/CAL_U.npz"); CB = np.load("/home/claude/lut0/S0ID_CAL.npz")
    KP = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); p0 = {k: KP[f"e_s|{k}"]["params"] for k in range(3)}; ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
    CR = np.load("/home/claude/lut7/CAL_SWBR.npz"); ES0 = np.load("/home/claude/lut7/ES_SWB.npy")
    setup = {"SWB-R": (eS, CR, TFC, "krige")}
    B0id = np.load("/home/claude/lut0/S0ID_CAL.npz")
    traces, truth, times, rows, br, hbias = {}, {}, {}, {}, {}, {}
    for r in ROUTES:
        p = packet(cond, seed, r); truth[r] = TRUTH[r]["truth"]; times[r] = p["t"]; tr = {}
        tr["H2"] = R7.replay(p, eF, "H2", **m7_kwargs("H2", r, cond, "own"))
        ps0 = sweep_packet(p, B0id[f"{r}/mu_r"], B0id[f"{r}/mu_s"], B0id[f"{r}/Rrr"], B0id[f"{r}/Rss"])
        tr["H2S"] = R7.replay(ps0, eF, "H2", sigma_b=ZERO_SB, condition=cond, rref_policy="own", sigma_rad=0.)
        for a in CAND:
            env_a, C, T, mode = setup[a]
            mus = C[f"{r}/mu_s"] if mode == "krige" else np.zeros_like(C[f"{r}/mu_s"])
            ps = sweep_packet(p, C[f"{r}/mu_r"], mus, C[f"{r}/Rrr"], C[f"{r}/Rss"])
            mfn = krige_fn(ES0, C[f"{r}/mu_s"], p0) if mode == "krige" else (lambda nav, distance, i: 0.0)
            tr[a] = M.replay_m8(ps, env_a, "F2SKRWV", table=T, sigma_b=ZERO_SB, condition=cond, mu_s_fn=mfn, **M.ARM_MODES["F2"])
        traces[r] = tr; rows[r] = {a: np.asarray(ft(tr[a], truth[r])) for a in ARMS}; br[r] = {a: bm(tr[a], truth[r], times[r]) for a in ARMS}
        hbias[r] = {a: float(np.degrees(np.mean((tr[a]["x"][:, 2] - truth[r][:, 2] + np.pi) % (2 * np.pi) - np.pi))) for a in ARMS}
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
    json.dump(dict(point=point, ci10={g: b10["by_group"][g] for g in (*ROUTES, "pooled")}, seed_assessments=assessed, heading_bias_deg=hbias,
                   mirror={r: {a: br[r][a]["mirror_fail_count"] for a in ARMS} for r in ROUTES}), open(d + "/GROUP.json", "w"),
              default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
    return key, "done", time.time() - t0


if __name__ == "__main__":
    seeds = range(10, 30)
    keys = [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in seeds]
    with Pool(2, maxtasksperchild=1) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
