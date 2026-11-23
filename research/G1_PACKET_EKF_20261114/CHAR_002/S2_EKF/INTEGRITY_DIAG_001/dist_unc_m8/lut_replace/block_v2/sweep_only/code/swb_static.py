"""Static check at packet poses (truth, RT Corridor R2/R4/R5): residual s_full - prediction by distance bin, plus table z coverage.
   LoS (FFD) | S0-id (FFD + kriging < 6 m + POWER >= 6 m) | BVK (FFD-based block + near kriging) | SWB (sweep-only block, column-out table)
   and curve quality of the sweep-only LoS-like curve (mode 'los') against FFD: RMS and 2-psi angle difference at packet poses."""
import sys, json, numpy as np, pandas as pd, importlib.util as iu
for p in ("/home/claude/m8", "/home/claude/m8cal", "/home/claude/lut2", "/home/claude/lut3", "/home/claude/lut0", "/home/claude/lut4"): sys.path.insert(0, p)
from common import env, packet
import h_ref as HR, bv_block as BVM, stage2_static as S2, sw_block as SB
sp_ = iu.spec_from_file_location("r2", "/home/claude/lut2/run_s2.py"); r2 = iu.module_from_spec(sp_); sp_.loader.exec_module(r2)
e0 = env(); base, spec = e0["model"], e0["spec"]; ffd = HR.ffd_s_fn(base)
KP = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); p0 = {k: KP[f"e_s|{k}"]["params"] for k in range(3)}
V0 = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]; B0 = np.load("/home/claude/lut0/S0ID_CAL.npz")
bv = BVM.BV(ffd, spec, S2.SW); TBVK = json.load(open("/home/claude/lut3/TABLE_BVK.json")); kBV = r2.krige_fn(np.load("/home/claude/lut3/ES_BV.npy"), np.zeros(20000), p0, near_limit=3.0)
kS0 = r2.krige_fn(np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"), np.zeros(20000), p0)
swb = SB.SWB(); los = SB.SWB(mode="los"); TSW, _, _ = SB.column_out_table(); json.dump(TSW, open("TABLE_SWB.json", "w")); print("SWB table", json.dumps(TSW))
rows = []
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); T = S2.F[S2.F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    X = np.c_[T.x_eval, T.y_eval, T.yaw_eval_rad, np.zeros(len(T))]; s = T.s_fp.values; rho = np.hypot(T.x_eval - 10, T.y_eval).values
    b = np.clip(np.searchsorted(SB.EDG, rho, side="right") - 1, 0, 2); hF, JF = ffd(X, spec)
    mu0 = np.array([kS0(x, rr, 0) if rr < 6 else B0[f"{r}/mu_s"][i] for i, (x, rr) in enumerate(zip(X, rho))])
    mB, JB = bv.s_fn()(X, spec); muB = np.array([kBV(x, rr, 0) for x, rr in zip(X, rho)])
    sS, _, _, aS = swb.eval(X[:, 0], X[:, 1], X[:, 2]); sL, _, _, _ = los.eval(X[:, 0], X[:, 1], X[:, 2])
    arms = {"LoS (FFD)": (hF, JF[:, 2], V0), "S0-id": (hF + mu0, JF[:, 2], V0), "BVK": (mB + muB, JB[:, 2], TBVK), "SWB": (sS, aS, TSW)}
    for nm, (pr, a, Tb) in arms.items():
        e = s - pr; var = np.array(Tb["c1"])[b] * a**2 + np.array(Tb["c0"])[b]
        for q in range(3):
            m = b == q; rows.append(dict(route=r, bin=["<3 m", "3-6 m", ">=6 m"][q], arm=nm, n=int(m.sum()), mean=e[m].mean(), head_eq=np.degrees(-np.mean(e[m] * a[m]) / np.mean(a[m]**2)),
                                         rms=np.sqrt(np.mean(e[m]**2)), zcov=np.mean(np.abs(e[m]) / np.sqrt(var[m]) <= 1.96)))
    d = sL - hF
    for q in range(3):
        m = b == q; rows.append(dict(route=r, bin=["<3 m", "3-6 m", ">=6 m"][q], arm="sweep LoS-like vs FFD", n=int(m.sum()), mean=d[m].mean(),
                                     head_eq=np.degrees(-np.mean(d[m] * JF[m, 2]) / np.mean(JF[m, 2]**2)), rms=np.sqrt(np.mean(d[m]**2)), zcov=np.nan))
D = pd.DataFrame(rows); D.to_csv("SWB_STATIC.csv", index=False)
A = D.groupby(["bin", "arm"], sort=False).apply(lambda q: pd.Series(dict(n=q.n.sum(), mean=np.average(q["mean"], weights=q.n), head_eq=np.average(q.head_eq, weights=q.n),
      rms=np.sqrt(np.average(q.rms**2, weights=q.n)), zcov=np.average(q.zcov, weights=q.n)))).reset_index()
pd.set_option("display.width", 200); print(A.round(4).to_string(index=False))
