"""Pre-diagnostic 3b: rotate the R5 truth trajectory (k=0..156) about X_0 by theta (positions about T[0], headings + theta); r, s, prior, odom costs with real z."""
import json
from sw_common import *
K = 156; an = env()["spec"]["anchor"]; T = truth("R5")[:K + 1]; p = packet("B0", 10, "R5"); N = ekf3.GYRO_N["B0"]
ek = ekf3.replay(p, S.sur_h, "B0", nstate=3, anchor=an); mask = ek["mask"][:K + 1]; Reff = ek["Reff"][:K + 1]
def rot(th):
    c, s = np.cos(th), np.sin(th); d = T[:, :2] - T[0, :2]; A = T.copy(); A[:, :2] = T[0, :2] + np.c_[c * d[:, 0] - s * d[:, 1], s * d[:, 0] + c * d[:, 1]]; A[:, 2] = fg3.wrap(T[:, 2] + th); return A
def costs(A, hfun):
    cr = cs = 0.
    for k in range(K + 1):
        if not mask[k]: continue
        h, _ = hfun(A[k]); res = h + p["muMB"][k] - p["z"][k]; cr += .5 * res[0] ** 2 / Reff[k][0, 0]; cs += .5 * res[1] ** 2 / Reff[k][1, 1]
    e = A[0] - p["x0"][:3]; e[2] = fg3.wrap(e[2]); cp = .5 * e @ np.linalg.solve(p["P0"][:3, :3], e)
    co = 0.
    for k in range(1, K + 1):
        ds, gy, dt = (float(p[q][k]) for q in ("ds", "gy", "dt")); y, _, _ = ekf3.transition(A[k - 1], ds, gy, dt); r = A[k] - y; r[2] = fg3.wrap(r[2])
        C = fg3.odom_cov(A[k - 1], ds, gy, dt, N, 1e-4); co += .5 * r @ np.linalg.solve(C, r)
    return {"r": cr, "s": cs, "prior": cp, "odom_lat1e-4": co}
ths = [-10, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 10]; out = {}
for name, hf in (("surrogate", S.sur_h), ("FFD", ffd_h)):
    tab = {th: costs(rot(np.radians(th)), hf) for th in ths}; base = tab[0]
    out[name] = {str(th): {k: round(v - base[k], 2) for k, v in c.items()} for th, c in tab.items()}
    print(name, "delta cost vs theta=0 (r, s, prior, odom):")
    for th in ths: print(f"  {th:+4d} deg  r {tab[th]['r']-base['r']:+9.2f}  s {tab[th]['s']-base['s']:+8.2f}  prior {tab[th]['prior']-base['prior']:+7.2f}  odom {tab[th]['odom_lat1e-4']-base['odom_lat1e-4']:+7.2f}")
    r1 = (tab[1]["r"] + tab[-1]["r"]) / 2 - base["r"]; r5 = (tab[5]["r"] + tab[-5]["r"]) / 2 - base["r"]
    s_lin = (tab[1]["s"] - tab[-1]["s"]) / 2; s_quad = (tab[1]["s"] + tab[-1]["s"]) / 2 - base["s"]
    out[name]["range_quadratic_check"] = dict(sym_rise_1deg=r1, sym_rise_5deg=r5, ratio_5_over_1=r5 / r1 if r1 else None, range_slope_per_deg=(tab[1]["r"] - tab[-1]["r"]) / 2)
    out[name]["s_slope_per_deg"] = s_lin; out[name]["s_curv_rise_1deg"] = s_quad
    print("  range: sym rise 1deg %.3f, 5deg %.2f (ratio %.1f, quadratic=25), slope/deg %.3f | s slope/deg %.3f curvature rise 1deg %.3f" % (r1, r5, r5 / r1 if r1 else float('nan'), out[name]["range_quadratic_check"]["range_slope_per_deg"], s_lin, s_quad))
json.dump(out, open(OUT + "/pre_asym/rotation_about_X0_costs.json", "w"), indent=1)
