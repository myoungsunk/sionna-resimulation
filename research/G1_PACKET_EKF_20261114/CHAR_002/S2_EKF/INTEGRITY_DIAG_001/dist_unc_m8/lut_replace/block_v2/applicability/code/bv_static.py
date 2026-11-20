"""Static applicability at ROUTE poses (RT Corridor R2/R4/R5, case *_aB_m0, full channel): residual s_full - prediction for
   LoS       : h_FFD
   S0-id     : h_FFD + kriging mean (S0 hyperparameters, S0-id labels) for rho < 6 m (far POWER is packet-indexed: not evaluated here)
   BV        : block from FFD
   BV_P1     : block from FFD' P1 (+5 deg reference error)
   2b_P1     : h'_P1 + kriging on P1 labels (Stage 2 arm, rho < 6 m)
Per bin: mean residual, heading-equivalent mean (deg), RMS, and z coverage with the arm's own table (BV: table from bv_block)."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/m8cal"); sys.path.insert(0, "/home/claude/lut2"); sys.path.insert(0, "/home/claude/lut3"); sys.path.insert(0, "/home/claude/lut0")
from feats import FZ
from common import env
import pert, h_ref as HR, bv_block as BVM
import importlib.util as _iu; _s = _iu.spec_from_file_location("lut2_run_s2", "/home/claude/lut2/run_s2.py"); _m = _iu.module_from_spec(_s); _s.loader.exec_module(_m); krige_fn = _m.krige_fn
e0 = env(); base, spec = e0["model"], e0["spec"]; ffd = HR.ffd_s_fn(base); p1 = pert.make(base, "P1")
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz")
bv = BVM.BV(ffd, spec, SW); bv1 = BVM.BV(p1, spec, SW); tabs = {"BV": bv.table(SW), "BV_P1": bv1.table(SW)}
print("dbar/kbar at rho 1,2,4,5,7,8 (side -1):", [(r, round(float(np.degrees(np.interp(r, BVM.RG, bv.grid[-1][0]))), 2), round(float(np.interp(r, BVM.RG, bv.grid[-1][1])), 3)) for r in (1, 2, 4, 5, 7, 8)])
print("tables BV", json.dumps(tabs["BV"]), "\nBV_P1", json.dumps(tabs["BV_P1"]))
V0 = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]; ST2 = json.load(open("/home/claude/lut2/STAGE2_STATIC.json"))
KP = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); p0 = {k: KP[f"e_s|{k}"]["params"] for k in range(3)}
kr0 = krige_fn(np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"), np.zeros(5000), p0); kr1 = krige_fn(np.load("/home/claude/lut2/ES_P1.npy"), np.zeros(5000), p0)
O = pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz", usecols=["case", "channel", "pose_id", "x_eval", "y_eval", "yaw_eval_rad", "s_fp"])
rows = []
for r in ("R2", "R4", "R5"):
    g = O[(O.case == f"{r}_aB_m0") & (O.channel == "full")].sort_values("pose_id"); X = np.c_[g.x_eval, g.y_eval, g.yaw_eval_rad, np.zeros(len(g))]
    rho = np.hypot(g.x_eval - 10, g.y_eval).values; s = g.s_fp.values; b = np.clip(np.searchsorted(BVM.EDG, rho, side="right") - 1, 0, 2)
    hF, JF = ffd(X, spec); h1, J1 = p1(X, spec)
    near = rho < 6
    k0 = np.array([kr0(x, rr, 0) if rr < 6 else np.nan for x, rr in zip(X, rho)]); k1 = np.array([kr1(x, rr, 0) if rr < 6 else np.nan for x, rr in zip(X, rho)])
    preds = {"LoS": (hF, JF[:, 2], V0), "S0-id": (hF + k0, JF[:, 2], V0), "2b_P1": (h1 + k1, J1[:, 2], ST2["P1"]["tableV"])}
    for nm, B in (("BV", bv), ("BV_P1", bv1)):
        m, J = B.s_fn()(X, spec); preds[nm] = (m, J[:, 2], tabs[nm])
    for nm, (pr, a, T) in preds.items():
        e = s - pr; var = np.array(T["c1"])[b] * a**2 + np.array(T["c0"])[b]
        for i in range(3):
            q = (b == i) & np.isfinite(e)
            if not q.any(): continue
            rows.append(dict(route=r, bin=["<3 m", "3-6 m", ">=6 m"][i], arm=nm, n=int(q.sum()), mean=e[q].mean(), head_eq_deg=np.degrees(-np.mean(e[q] * a[q]) / np.mean(a[q]**2)),
                             rms=np.sqrt(np.mean(e[q]**2)), zcov=np.mean(np.abs(e[q]) / np.sqrt(var[q]) <= 1.96)))
D = pd.DataFrame(rows); D.to_csv("/home/claude/lut3/BV_STATIC_ROUTE.csv", index=False)
agg = D.assign(w=D.n).groupby(["bin", "arm"]).apply(lambda q: pd.Series(dict(n=q.n.sum(), mean=np.average(q["mean"], weights=q.n), head_eq_deg=np.average(q.head_eq_deg, weights=q.n),
      rms=np.sqrt(np.average(q.rms**2, weights=q.n)), zcov=np.average(q.zcov, weights=q.n), head_eq_by_route=list(np.round(q.head_eq_deg, 2)))))
pd.set_option("display.width", 250); print(agg.round(4).to_string())
