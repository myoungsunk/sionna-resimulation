"""O3 Office LoS-route replay. Arms: H0, H2 (Office route LORO G0), F2L (Office route LORO F2),
F2T0 (corridor sweep), F2T1nK (Office sweep, no kriging), F2T1 (Office sweep + kriging), F2T1V (+ V table)."""
import sys, os, json, time, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/m8")
O = "/home/claude/office"; OUT = f"{O}/out_o3"
ROUTES = ("O01", "O02", "O03L"); ARMS = ("H0", "H2", "F2L", "F2T0", "F2T1nK", "F2T1", "F2T1V")
SPEC_O = {"anchor": (5., 2.2, 2.65), "robot_z_m": .45, "mount_deg": 0.}
SB = dict(knots_m=[0., 1.5, 3., 6., 10.], sigma_b=[.005] * 5)            # M7 frozen sigma_b (all routes 0.005)
ZERO = dict(knots_m=[0., 20.], sigma_b=[0., 0.])
EDG = np.array([0., 3., 6., 10.])


def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi


def office_env():
    from common import env
    e = dict(env()); e["spec"] = dict(SPEC_O); e["native"] = (e["core"], e["online"], e["model"], dict(SPEC_O)); return e


def make_krige(far_mu_s):
    import pandas as pd
    D = pd.read_csv(f"{O}/O3_KRIGE_DATA.csv", float_precision="round_trip"); KP = json.load(open(f"{O}/O3_INFO.json"))["krige_office"]
    B = {k: dict(X=D[D.b == k][["x_eval", "y_eval", "psi"]].to_numpy(), y=D[D.b == k].e_s.to_numpy(), prm=KP[str(k)]["params"]) for k in range(3)}
    for k in B: B[k]["mu0"] = float(B[k]["y"].mean())
    def kr(x, y, psi, rho, maxn=150):
        b = int(np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2)); Bk = B[b]; lx, ly, lp, nug = Bk["prm"]; X = Bk["X"]
        d = np.abs(X[:, 0] - x) / lx + np.abs(X[:, 1] - y) / ly + np.abs(wrap(X[:, 2] - psi)) / lp
        idx = np.argpartition(d, maxn)[:maxn] if len(d) > maxn else np.arange(len(d)); Xi = X[idx]
        K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
        w = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-d[idx])); return Bk["mu0"] + w @ (Bk["y"][idx] - Bk["mu0"])
    def fn(nav, distance, i):
        return float(kr(nav[0], nav[1], nav[2], distance)) if distance < 6. else float(far_mu_s[i])
    return fn


def pk(base, c):
    q = dict(base); q["muMB"] = np.c_[c["mu_r"], c["mu_s"]]; q["muBASE"] = q["muMB"].copy(); q["D"] = np.zeros(len(base["t"]))
    R = np.zeros((len(base["t"]), 2, 2)); R[:, 0, 0] = c["Rrr"]; R[:, 1, 1] = c["Rss"]; q["R"] = R; return q


def gross(x, truth, t, thr=1.0, dur=10.):
    err = np.linalg.norm(x[:, :2] - truth[:, :2], axis=1); bad = err > thr; n = 0; i = 0
    while i < len(bad):
        if bad[i]:
            j = i
            while j + 1 < len(bad) and bad[j + 1]: j += 1
            if t[j] - t[i] >= dur: n += 1
            i = j + 1
        else: i += 1
    return n


def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import R7, scorers
    import m8_replay as M
    from m7_assess import COVERAGE, assess_group, assess_seed
    e = office_env(); ft, swb, _ = scorers(); t0 = time.time()
    C = np.load(f"{O}/O3_CAL.npz"); RT = np.load(f"{O}/O3_ROUTES.npz"); INFO = json.load(open(f"{O}/O3_INFO.json"))
    tab = lambda t_: dict(edges=t_["edges"], c1=t_["c1"], c0=t_["c0"])
    traces, truth, times, rows, gro = {}, {}, {}, {}, {}
    for r in ROUTES:
        b = dict(np.load(f"{O}/inputs/{r}_{cond}_{seed}.npz")); truth[r] = RT[f"{r}/truth"]; times[r] = b["t"]
        cal = {a: {k: C[f"{r}/{a}/{k}"] for k in ("mu_r", "mu_s", "Rrr", "Rss")} for a in ("H2", "T0", "T1")}
        pH2, pT0, pT1 = pk(b, cal["H2"]), pk(b, cal["T0"]), pk(b, cal["T1"])
        tr = {}
        tr["H0"] = R7.replay(pH2, e, "H0", sigma_b=SB, condition=cond, rref_policy="own", sigma_rad=0.)
        tr["H2"] = R7.replay(pH2, e, "H2", sigma_b=SB, condition=cond, rref_policy="own", sigma_rad=0.)
        F2 = lambda p, tb, sb, fn=None: M.replay_m8(p, e, "F2", table=tb, sigma_b=sb, condition=cond, mu_s_fn=fn, **M.ARM_MODES["F2"])
        tr["F2L"] = F2(pH2, tab(INFO[f"table_F2L_{r}"]), SB)
        tr["F2T0"] = F2(pT0, tab(INFO["table_corridor"]), ZERO)
        tr["F2T1nK"] = F2(pT1, tab(INFO["table_office"]), ZERO)
        tr["F2T1"] = F2(pT1, tab(INFO["table_office"]), ZERO, make_krige(cal["T1"]["mu_s"]))
        tr["F2T1V"] = F2(pT1, tab(INFO["table_V"]), ZERO, make_krige(cal["T1"]["mu_s"]))
        traces[r] = tr
        rows[r] = {a: np.asarray(ft(tr[a], truth[r])) for a in ARMS}
        gro[r] = {a: gross(np.asarray(tr[a]["x"]), truth[r], times[r]) for a in ARMS}
    sc = swb(rows, times, [(a, "H2") for a in ARMS if a != "H2"], blocks=(5, 10, 20))
    point, b10 = sc["point"], sc["blocks"]["10"]; assessed = {}
    for arm in ARMS:
        groups = {}
        for g in (*ROUTES, "pooled"):
            ci = b10["by_group"][g]; lower = {m: ci["absolute_ci95"][arm][m][0] for m in COVERAGE}; pooled = g == "pooled"
            mir = sum(gro[q][arm] for q in ROUTES) if pooled else gro[g][arm]
            blocks = min(b10["full_blocks"].values()) if pooled else b10["full_blocks"][g]
            groups[g] = assess_group(point[g][arm], lower, point[g]["H2"], pooled=pooled, effective_blocks=blocks,
                                     reference_only=bool(ci["reference_only"]), mirror_fail=mir)
        # m7_assess.assess_seed requires the M7 group labels; map O01->R2, O02->R4, O03L->R5 (labels only) and back
        lab = dict(zip(ROUTES, ("R2", "R4", "R5"))); back = {v: k for k, v in lab.items()}
        sa = assess_seed(seed, {lab.get(g, g): v for g, v in groups.items()})
        sa["groups"] = {back.get(g, g): v for g, v in sa["groups"].items()}; assessed[arm] = sa
    os.makedirs(d, exist_ok=True)
    json.dump(dict(seed=seed, condition=cond, point=point, gross=gro, seed_assessments=assessed,
                   full_blocks=b10["full_blocks"]), open(d + "/GROUP.json", "w"),
              default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
    return key, "done", time.time() - t0


if __name__ == "__main__":
    keys = [("B0", 10)] if sys.argv[1] == "one" else [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)]
    with Pool(2) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
