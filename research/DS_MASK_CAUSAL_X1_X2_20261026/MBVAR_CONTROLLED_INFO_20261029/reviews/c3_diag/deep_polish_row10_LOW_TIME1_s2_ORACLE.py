import sys, time; sys.path.insert(0, "code")
import numpy as np, s0v2 as S0V2, s1_mc as M, s1v2 as V, s1v3 as T, s1v4 as S4, filters as FL, world as Wd
lk = S0V2.lock_v2(); S = V.setup(lk); root = M.seed_root()
f, role, cn, sn, arm = 10, "LOW", "TIME_1", 2, "ORACLE_CORR_BATCH"
w = S["wins"][role]; inp0 = T.make_inputs(S, root, f, cn, w, sn, None); _, models = T.arm_models(S, w, cn); Sm = models[arm]
hb = S4.hb_true_tap(w); rng = np.random.default_rng(1)
def run(inp, tol, mx):
    X, _, info = FL.batch_map_v2_ms(hb, inp["z"], np.zeros((60, 2)), Sm, inp["ds_m"], inp["gy_m"], w["dts"], inp["x0"], M.P0)
    S4.POLISH_TOL, S4.POLISH_MAX = tol, mx
    th, n, cap = S4.polish(hb, inp["z"], Sm, inp["ds_m"], inp["gy_m"], w["dts"], inp["x0"], info["theta"], 7)
    Lm, L0, qv = T._mats(Sm, inp["ds_m"], w["dts"])
    c, Xp = FL._v2_parts(hb, inp["z"], np.zeros((60, 2)), Lm, L0, inp["x0"], qv, inp["ds_m"], inp["gy_m"], w["dts"], th[0], th[1], jac=False)
    return info["cost"], X[-1], c, Xp[-1], n, cap
res = {}
for k in range(3):
    inp = dict(inp0); inp["z"] = inp0["z"] + (0 if k == 0 else 1e-14 * rng.standard_normal(inp0["z"].shape))
    for tol, mx in ((1e-3, 30), (1e-9, 300)):
        t = time.time(); cE, XE, cP, XP, n, cap = run(inp, tol, mx)
        res[(k, tol)] = (cE, XE, cP, XP)
        print(f"pert{k} tol={tol:g}: cost_E={cE:.9f} cost_Ep={cP:.9f} steps={n} cap={cap} t={time.time()-t:.0f}s", flush=True)
for tol in (1e-3, 1e-9):
    a = [res[(k, tol)] for k in range(3)]
    dE = max(T.dref_diff(a[i][1], a[j][1]) for i in range(3) for j in range(3)); dP = max(T.dref_diff(a[i][3], a[j][3]) for i in range(3) for j in range(3))
    cP = max(abs(a[i][2] - a[j][2]) for i in range(3) for j in range(3))
    print(f"tol={tol:g}: spread E {dE:.3g} d_ref | spread E' {dP:.3g} d_ref | cost spread E' {cP:.3g}")
