"""Stage 2: judgments of PLAN_SWEEP_EXT_KO.md (sections 6-7) from ../EXT_S.csv.gz.
Usage: python ana_ext.py <result-branch checkout root>
Implementation choices fixed here before the stage-2 numbers are produced (plan leaves them open):
 - B1 prediction uses the full per-position traces of run B (all paths), not PATHS_NEAR (stored window is only dL <= 0.30 m,
   which would drop paths the plan's sinc^2 weight keeps). A PATHS_NEAR-window variant (dL <= 0.2991 m) is reported alongside.
 - Path gradient g_k: quadratic LSQ fit of dL_k(dx, dy) over the 64 run-B positions of the patch, gradient at the patch center.
   Paths matched across positions by trace signature. Path power |a_k|^2: Frobenius power of the trace Jones, mean over present nodes.
 - B1 y direction: l_obs from the A1 1 cm line (line mean removed); if that is '> max' (8 cm), the patch y value is used.
 - C1 eta: RMS over the 108 off-grid yaws of (e - e_interp) divided by RMS of e over all 144 yaws."""
import sys, json, glob, numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0", "/home/claude/bvb"]
from common import env
import h_ref as HR

ROOT = sys.argv[1]
C0 = 299792458.0; LAM = C0 / 6.5e9; BW = 499.2e6; IE = 1 / np.e
S = pd.read_csv("../EXT_S.csv.gz")
e0 = env(); ffd = HR.ffd_s_fn(e0["model"])
XC = {"P016": 7.95, "P013": 6.60, "P011": 5.70, "P010": 5.25, "P008": 4.35, "P006": 3.45, "P003": 2.10, "P001": 1.20}


def uc(a, b):
    a, b = np.ravel(a), np.ravel(b); return float(np.sum(a * b) / np.sqrt(np.sum(a * a) * np.sum(b * b)))


def comps(x, y, yaw, e):
    st = np.c_[np.full(len(yaw), x), np.full(len(yaw), y), np.radians(yaw), np.zeros(len(yaw))]
    h, J = ffd(st, e0["spec"]); X = np.c_[np.ones(len(yaw)), J[:, 2], h]
    return np.linalg.lstsq(X, e, rcond=None)[0]   # offset, delta (rad), kappa


def e_len(seps, vals):
    seps, vals = np.asarray(seps, float), np.asarray(vals, float)
    if vals[0] < IE: return dict(status="unresolved", value=float(seps[0]))
    for k in range(1, len(seps)):
        if vals[k] < IE:
            return dict(status="resolved", value=float(seps[k - 1] + (vals[k - 1] - IE) / (vals[k - 1] - vals[k]) * (seps[k] - seps[k - 1])))
    return dict(status="gt_max", value=float(seps[-1]))


# 36-yaw curves: new runs A/B first, then 4 cm near run, then centerline centers. Run C is used only for C1.
CUR = {}
for run in ("A", "B", "NEAR", "CL"):
    for (x, y), g in S[S.run == run].groupby(["x", "y"]):
        k = (int(round(x * 100)), int(round(y * 100)))
        if k in CUR: continue
        g = g.sort_values("yaw_body_deg"); assert len(g) == 36
        e = g.e.values; c = comps(x, y, g.yaw_body_deg.values, e)
        CUR[k] = dict(e=e, delta=np.degrees(c[1]), off=c[0], kappa=c[2], run=run)


def line_stats(name, axis, cx, cy, offs, tag):
    keys = [((cx + o, cy) if axis == "x" else (cx, cy + o)) for o in offs]
    E = np.array([CUR[k]["e"] for k in keys]); D = np.array([CUR[k]["delta"] for k in keys]); R = E - E.mean(0)
    rows = []
    step = offs[1] - offs[0]
    for n in range(1, len(offs)):
        pr = [(i, i + n) for i in range(len(offs) - n)]
        a, b = [i for i, _ in pr], [j for _, j in pr]
        rows.append(dict(center=name, axis=axis, grid=tag, sep_m=n * step / 100, pairs=len(pr), u=uc(E[a], E[b]), rho_c=uc(R[a], R[b]),
                         D_e=float(np.sqrt(np.mean((E[a] - E[b]) ** 2))), D_delta_deg=float(np.sqrt(np.mean((D[a] - D[b]) ** 2)))))
    return rows


O4 = list(range(-16, 17, 4)); O1 = list(range(-8, 9))
L = []
for c, x in XC.items():
    cx = int(round(x * 100))
    if (cx - 16, 0) in CUR: L += line_stats(c, "x", cx, 0, O4, "4cm")
    if (cx, -16) in CUR: L += line_stats(c, "y", cx, 0, O4, "4cm")
    if (cx, -8) in CUR and (cx, -1) in CUR: L += line_stats(c, "y", cx, 0, O1, "1cm")
L += line_stats("P010_Y30", "x", 525, 30, O4, "4cm")
L = pd.DataFrame(L); L.to_csv("../EXT_LINES.csv", index=False)


def get(center, axis, grid):
    return L[(L.center == center) & (L.axis == axis) & (L.grid == grid)].sort_values("sep_m")


def lens(center, axis, grid):
    g = get(center, axis, grid); return dict(u=e_len(g.sep_m, g.u), rho_c=e_len(g.sep_m, g.rho_c))


DEC = {}
# ---- A2
a2 = {c: float(get(c, "x", "4cm").set_index("sep_m").D_delta_deg.loc[0.2]) for c in ("P013", "P011", "P008", "P010_Y30")}
n2 = sum(v >= 2.0 for v in a2.values())
DEC["A2"] = dict(D_delta_20cm_deg=a2, count_ge_2deg=n2,
                 ref={c: float(get(c, "x", "4cm").set_index("sep_m").D_delta_deg.loc[0.2]) for c in ("P016", "P010", "P003")},
                 verdict="general" if n2 >= 3 else ("singular" if n2 <= 1 else "location_dependent"),
                 center_delta_deg={c: float(CUR[(int(round(XC.get(c, 5.25) * 100)), 30 if c == "P010_Y30" else 0)]["delta"]) for c in a2})
# ---- A1
a1 = {}
for c in ("P016", "P010", "P003"):
    gx, gy = get(c, "x", "4cm").set_index("sep_m"), get(c, "y", "4cm").set_index("sep_m")
    r = {h: float(gy.D_e.loc[h] / gx.D_e.loc[h]) for h in (0.04, 0.16)}
    cls = "isotropic" if all(0.5 <= v <= 2 for v in r.values()) else ("y_longer" if all(v < 0.5 for v in r.values()) else ("y_shorter" if all(v > 2 for v in r.values()) else "mixed"))
    a1[c] = dict(R=r, cls=cls, len_x4=lens(c, "x", "4cm"), len_y4=lens(c, "y", "4cm"), len_y1=lens(c, "y", "1cm"))
DEC["A1"] = dict(centers=a1, verdict="isotropic_kernel" if all(a1[c]["cls"] == "isotropic" for c in ("P016", "P010")) else "direction_split")
# ---- A3
a3 = {}
for c in ("P006", "P001", "P003"):
    lx, ly = lens(c, "x", "4cm")["u"], lens(c, "y", "4cm")["u"]
    ok = all(v["status"] == "resolved" and 0.11 <= v["value"] <= 0.56 for v in (lx, ly)) and 0.5 <= ly["value"] / lx["value"] <= 2
    a3[c] = dict(L_x=lx, L_y=ly, passed=bool(ok), offset=float(CUR[(int(round(XC[c] * 100)), 0)]["off"]), delta_deg=float(CUR[(int(round(XC[c] * 100)), 0)]["delta"]))
DEC["A3"] = dict(centers=a3, verdict="general" if all(v["passed"] for v in a3.values()) else "not_general")
# ---- B1 condition
xr = {c: lens(c, "x", "4cm")["rho_c"] for c in ("P013", "P011", "P008", "P010_Y30", "P006", "P001", "P003")}
res = [v["value"] for v in xr.values() if v["status"] == "resolved"]
ratio = max(res) / min(res) if len(res) >= 2 else None
DEC["B1_condition"] = dict(A2_location_dependent=DEC["A2"]["verdict"] == "location_dependent", A3_not_general=DEC["A3"]["verdict"] != "general",
                           x_rho_c_lengths=xr, resolved_ratio=ratio, ratio_ge_2=bool(ratio is not None and ratio >= 2))
DEC["B1_condition"]["met"] = bool(DEC["B1_condition"]["A2_location_dependent"] or DEC["B1_condition"]["A3_not_general"] or DEC["B1_condition"]["ratio_ge_2"])

# ---- B1 observation
DIRS = {"x": (1, 0), "y": (0, 1), "d1": (1, 1), "d2": (1, -1)}
tasks = {t["task_id"]: t for t in json.load(open(f"{ROOT}/artifacts/BLOCK_C_M7_EXT_B_20261127_J85C8uA7/results/poses/BLOCKC_B/rf_tasks.json"))}
TR = {}
for f in sorted(glob.glob(f"{ROOT}/artifacts/BLOCK_C_M7_EXT_B_20261127_J85C8uA7/results/traces/BLOCKC_B/task_*_trace.npz")):
    z = np.load(f); TR[(int(round(float(z["x"]) * 100)), int(round(float(z["y"]) * 100)))] = z


def predict(c, near_only=False):
    cx = int(round(XC[c] * 100)); rec = {}
    for (px, py), z in TR.items():
        if abs(px - cx) > 16 or abs(py) > 16: continue
        sig = z["signature"]; tau = z["tau"]; pres = z["present"]; J = z["jones"]
        i0 = int(np.flatnonzero(sig == "LOS")[0])
        pw = np.array([np.mean(np.sum(np.abs(J[pres[:, k], k]) ** 2, axis=(1, 2))) if pres[:, k].any() else 0.0 for k in range(len(sig))])
        for k, s in enumerate(sig):
            if k == i0: continue
            rec.setdefault(str(s), []).append(((px - cx) / 100, py / 100, C0 * (tau[k] - tau[i0]), pw[k]))
    P = []
    for s, v in rec.items():
        if len(v) < 20: continue
        v = np.array(v); X = np.c_[np.ones(len(v)), v[:, 0], v[:, 1], v[:, 0] ** 2, v[:, 1] ** 2, v[:, 0] * v[:, 1]]
        b = np.linalg.lstsq(X, v[:, 2], rcond=None)[0]; dl0 = b[0]
        if near_only and dl0 > 0.2991: continue
        P.append(dict(sig=s, dL=dl0, gx=b[1], gy=b[2], w=float(np.median(v[:, 3]) * np.sinc(dl0 * BW / C0) ** 2), n=len(v)))
    P = pd.DataFrame(P); hh = np.arange(0, 0.6005, 0.0005); out = {}
    for d, (a, bb) in DIRS.items():
        u = np.array([a, bb]) / np.hypot(a, bb); gu = P.gx.values * u[0] + P.gy.values * u[1]
        rp = (P.w.values[None, :] * np.cos(2 * np.pi * gu[None, :] * hh[:, None] / LAM)).sum(1) / P.w.sum()
        k = np.flatnonzero(rp < IE); out[d] = float(hh[k[0]]) if len(k) else np.inf
    return out, P


B1 = []; SP = []
for c in ("P016", "P010", "P003"):
    cx = int(round(XC[c] * 100)); keys = [(cx + dx, dy) for dy in O4 for dx in O4]
    E = np.array([CUR[k]["e"] for k in keys]).reshape(9, 9, 36); R = E - E.reshape(81, 36).mean(0)
    pred, PP = predict(c); predn, _ = predict(c, near_only=True)
    PP.assign(center=c).to_csv(f"../B1_PATHS_{c}.csv", index=False)
    for d, (a, bb) in DIRS.items():
        seps, vals = [], []
        for k in range(1, 9):
            pa, pb = [], []
            for iy in range(9):
                for ix in range(9):
                    jx, jy = ix + a * k, iy + bb * k
                    if 0 <= jx < 9 and 0 <= jy < 9: pa.append(R[iy, ix]); pb.append(R[jy, jx])
            if pa: seps.append(0.04 * k * np.hypot(a, bb)); vals.append(uc(np.array(pa), np.array(pb)))
        lo = e_len(seps, vals); src = "patch"
        if d == "y":
            l1 = lens(c, "y", "1cm")["rho_c"]
            if l1["status"] != "gt_max": lo, src = l1, "A1_1cm"
        B1.append(dict(center=c, dir=d, obs_status=lo["status"], l_obs=lo["value"], obs_src=src, l_pred=pred[d], l_pred_nearwin=predn[d],
                       rho_c=json.dumps([round(v, 3) for v in vals])))
    for s in (8, 16, 32):
        sub = [o for o in O4 if (o + 16) % s == 0]; ii = [O4.index(o) for o in sub]; err = []
        for iy, oy in enumerate(O4):
            for ix, ox in enumerate(O4):
                if ox in sub and oy in sub: continue
                jx = np.searchsorted(sub, ox, side="right") - 1; jx = min(jx, len(sub) - 2); jy = min(np.searchsorted(sub, oy, side="right") - 1, len(sub) - 2)
                tx = (ox - sub[jx]) / (sub[jx + 1] - sub[jx]); ty = (oy - sub[jy]) / (sub[jy + 1] - sub[jy])
                q = lambda a_, b_: E[ii[b_], ii[a_]]
                est = (1 - tx) * (1 - ty) * q(jx, jy) + tx * (1 - ty) * q(jx + 1, jy) + (1 - tx) * ty * q(jx, jy + 1) + tx * ty * q(jx + 1, jy + 1)
                err.append(E[iy, ix] - est)
        err = np.array(err); SP.append(dict(center=c, spacing_m=s / 100, rms_err=float(np.sqrt(np.mean(err ** 2))),
                                            rms_e=float(np.sqrt(np.mean(E ** 2))), rms_resid=float(np.sqrt(np.mean(R ** 2)))))
B1 = pd.DataFrame(B1); B1.to_csv("../B1_POINTS.csv", index=False); pd.DataFrame(SP).to_csv("../B1_SPARSE.csv", index=False)
ok = B1[(B1.obs_status == "resolved") & np.isfinite(B1.l_pred)]
if len(ok) >= 8:
    rs = float(spearmanr(ok.l_obs, ok.l_pred).correlation); ml = float(np.median(np.abs(np.log(ok.l_obs / ok.l_pred))))
    v = "geometry_predictable" if (rs >= 0.6 and ml <= np.log(2)) else "not_predictable"
else:
    rs = ml = None; v = "not_judgeable_n_lt_8"
okn = B1[(B1.obs_status == "resolved") & np.isfinite(B1.l_pred_nearwin)]
DEC["B1"] = dict(n_points=int(len(ok)), spearman=rs, median_abs_log_ratio=ml, verdict=v,
                 nearwin=dict(n_points=int(len(okn)), spearman=float(spearmanr(okn.l_obs, okn.l_pred_nearwin).correlation) if len(okn) >= 3 else None,
                              median_abs_log_ratio=float(np.median(np.abs(np.log(okn.l_obs / okn.l_pred_nearwin)))) if len(okn) else None))

# ---- C1
Cd = S[S.run == "C"].copy(); C1 = []; YL = []
BIN = {"P016": "near", "P010": "mid", "P003": "far"}
for (x, y), g in Cd.groupby(["x", "y"]):
    g = g.sort_values("yaw_body_deg"); assert len(g) == 144; e = g.e.values; yw = g.yaw_body_deg.values
    on = np.isclose(np.mod(yw, 10.0), 0.0); assert on.sum() == 36 and on[0]
    eh = np.fft.irfft(np.fft.rfft(e[on]), n=144) * 144 / 36
    cen = min(XC, key=lambda k: abs(XC[k] - x) if k in BIN else 9)
    C1.append(dict(center=cen, bin=BIN[cen], x=x, y=y, eta=float(np.sqrt(np.mean((e[~on] - eh[~on]) ** 2)) / np.sqrt(np.mean(e ** 2))),
                   rms_e=float(np.sqrt(np.mean(e ** 2)))))
    YL.append((cen, e))
C1 = pd.DataFrame(C1); C1.to_csv("../C1_ETA.csv", index=False)
yl = []
for cen in BIN:
    Es = [e for c, e in YL if c == cen]
    for kind in ("u", "centered"):
        vals = [uc(np.concatenate([(e - (e.mean() if kind == "centered" else 0)) for e in Es]),
                   np.concatenate([np.roll(e - (e.mean() if kind == "centered" else 0), -k) for e in Es])) for k in range(1, 37)]
        yl.append(dict(center=cen, kind=kind, **{f"lag{2.5 * k:g}": round(v, 4) for k, v in zip(range(1, 37), vals)},
                       len_deg=json.dumps(e_len(2.5 * np.arange(1, 37), vals))))
pd.DataFrame(yl).to_csv("../C1_YAWLEN.csv", index=False)
med = C1.groupby("bin").eta.median().to_dict()
DEC["C1"] = dict(eta_median=med, verdict={b: ("no_sub10deg" if v <= 0.10 else ("two_scale" if v > 0.25 else "intermediate")) for b, v in med.items()},
                 yaw_len={d["center"] + "_" + d["kind"]: json.loads(d["len_deg"]) for d in yl})

# ---- GP: P010_Y30 vs SWB grid
from load import load
G = load(); g = G[(G.col == 525) & (G.row == 30)].copy(); g["yk"] = np.mod(np.round(g.yaw), 360)
n = S[(S.run == "A") & np.isclose(S.x, 5.25) & np.isclose(S.y, 0.30)].copy(); n["yk"] = np.mod(np.round(n.yaw_body_deg), 360)
m = n.merge(g[["yk", "s"]], on="yk"); DEC["GP"] = dict(n=int(len(m)), u_s=uc(m.s_full, m.s), max_abs_diff=float(np.max(np.abs(m.s_full - m.s))))
json.dump(DEC, open("../EXT_DECISIONS.json", "w"), indent=1, default=float)
print(json.dumps(DEC, indent=1, default=float))
