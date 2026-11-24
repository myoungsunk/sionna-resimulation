"""COPY (run_c2o.py): SWB-C = Corridor-trained SWB (corr2office.py) + Corridor table, Office T1 range; SWB-C0 = same with Corridor sweep range T0. Office replay with the sweep block (DIAGNOSTIC). Arms: H2 (reference), F2T1V (existing best Office method: FFD + Office sweep kriging + V table),
SWB-O (Office 2-D sweep block, no FFD, no mean correction, station-out table). Range calibration for F2T1V and SWB-O: Office sweep T1 (as o3_run)."""
import sys, os, json, time, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/office"); sys.path.insert(0, "/home/claude/lut8"); sys.path.insert(0, "/home/claude/lut0")
import o3_run as O3
OUT = "/home/claude/lut8/out_c2o"; ROUTES = O3.ROUTES; ARMS = ("H2", "SWB-C", "SWB-C0")
def job(key):
    cond, seed = key; d = f"{OUT}/{cond}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import R7, scorers
    import m8_replay as M, h_ref as HR, corr2office as C2
    from m7_assess import COVERAGE, assess_group, assess_seed
    e = O3.office_env(); eS = HR.swap_env(e, C2.s_fn()); ft, swb, _ = scorers(); t0 = time.time()
    C = np.load(f"{O3.O}/O3_CAL.npz"); RT = np.load(f"{O3.O}/O3_ROUTES.npz"); INFO = json.load(open(f"{O3.O}/O3_INFO.json")); TS = json.load(open("/home/claude/lut5/TABLE_SWB_FULLCO.json"))
    tab = lambda t_: dict(edges=t_["edges"], c1=t_["c1"], c0=t_["c0"]); traces, truth, times, rows, gro, hb = {}, {}, {}, {}, {}, {}
    for r in ROUTES:
        b = dict(np.load(f"{O3.O}/inputs/{r}_{cond}_{seed}.npz")); truth[r] = RT[f"{r}/truth"]; times[r] = b["t"]
        cal = {a: {k: C[f"{r}/{a}/{k}"] for k in ("mu_r", "mu_s", "Rrr", "Rss")} for a in ("H2", "T0", "T1")}
        pH2, pT1 = O3.pk(b, cal["H2"]), O3.pk(b, cal["T1"]); pZ = O3.pk(b, dict(cal["T1"], mu_s=np.zeros_like(cal["T1"]["mu_s"]))); pZ0 = O3.pk(b, dict(cal["T0"], mu_s=np.zeros_like(cal["T0"]["mu_s"])))
        tr = {"H2": R7.replay(pH2, e, "H2", sigma_b=O3.SB, condition=cond, rref_policy="own", sigma_rad=0.)}
        tr["SWB-C"] = M.replay_m8(pZ, eS, "F2", table=tab(TS), sigma_b=O3.ZERO, condition=cond, mu_s_fn=lambda nav, distance, i: 0.0, **M.ARM_MODES["F2"])
        tr["SWB-C0"] = M.replay_m8(pZ0, eS, "F2", table=tab(TS), sigma_b=O3.ZERO, condition=cond, mu_s_fn=lambda nav, distance, i: 0.0, **M.ARM_MODES["F2"])
        rows[r] = {a: np.asarray(ft(tr[a], truth[r])) for a in ARMS}; gro[r] = {a: O3.gross(np.asarray(tr[a]["x"]), truth[r], times[r]) for a in ARMS}
        hb[r] = {a: float(np.degrees(np.mean(O3.wrap(np.asarray(tr[a]["x"])[:, 2] - truth[r][:, 2])))) for a in ARMS}
    sc = swb(rows, times, [(a, "H2") for a in ARMS if a != "H2"], blocks=(5, 10, 20)); point, b10 = sc["point"], sc["blocks"]["10"]; assessed = {}
    lab = dict(zip(ROUTES, ("R2", "R4", "R5"))); back = {v: k for k, v in lab.items()}
    for arm in ARMS:
        groups = {}
        for g in (*ROUTES, "pooled"):
            ci = b10["by_group"][g]; lower = {m: ci["absolute_ci95"][arm][m][0] for m in COVERAGE}; pooled = g == "pooled"
            mir = sum(gro[q][arm] for q in ROUTES) if pooled else gro[g][arm]; blocks = min(b10["full_blocks"].values()) if pooled else b10["full_blocks"][g]
            groups[g] = assess_group(point[g][arm], lower, point[g]["H2"], pooled=pooled, effective_blocks=blocks, reference_only=bool(ci["reference_only"]), mirror_fail=mir)
        sa = assess_seed(seed, {lab.get(g, g): v for g, v in groups.items()}); sa["groups"] = {back.get(g, g): v for g, v in sa["groups"].items()}; assessed[arm] = sa
    os.makedirs(d, exist_ok=True)
    json.dump(dict(seed=seed, condition=cond, point=point, gross=gro, heading_bias_deg=hb, seed_assessments=assessed), open(d + "/GROUP.json", "w"),
              default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
    return key, "done", time.time() - t0
if __name__ == "__main__":
    keys = [(c, s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)]
    with Pool(2, maxtasksperchild=1) as pool:
        for k, st, dt in pool.imap_unordered(job, keys): print(json.dumps(dict(key=k, status=st, sec=round(dt, 1))), flush=True)
