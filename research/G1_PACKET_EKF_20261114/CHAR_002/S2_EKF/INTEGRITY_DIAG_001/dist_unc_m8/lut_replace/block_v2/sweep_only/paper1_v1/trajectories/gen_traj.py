"""Candidate corridor trajectories for Paper 1 (TB3-feasible). Kinematics matched to R2/R4/R5:
v = 0.20 m/s, |omega| <= 25 deg/s, dt = 0.2 s, in-place rotation when heading error > 30 deg.
Corridor frame: anchor (10, 0), sweep grid x 1.20-18.75, y +-0.45. All routes keep |y| <= 0.45."""
import json, numpy as np, pandas as pd
DT, V, WMAX = 0.2, 0.20, np.radians(25.0); AX = (10.0, 0.0)
wrap = lambda a: (a + np.pi) % (2 * np.pi) - np.pi
def run(start, prims):
    x, y, th = start; rows = []; t = 0.0
    def push(v, w, mode):
        nonlocal x, y, th, t
        rows.append((t, x, y, th, v, w, mode)); th = wrap(th + w * DT); x += v * np.cos(th) * DT; y += v * np.sin(th) * DT; t += DT
    for p in prims:
        if p[0] == "rot":                                     # in-place rotation by given angle (deg)
            rem = np.radians(p[1])
            while abs(rem) > 1e-9:
                w = np.sign(rem) * min(WMAX, abs(rem) / DT); push(0.0, w, "rotate"); rem -= w * DT
        elif p[0] == "stop":
            for _ in range(int(round(p[1] / DT))): push(0.0, 0.0, "stop")
        else:                                                 # follow waypoint list
            for (gx, gy) in p[1]:
                for _ in range(5000):
                    d = np.hypot(gx - x, gy - y)
                    if d < 0.06: break
                    err = wrap(np.arctan2(gy - y, gx - x) - th)
                    if abs(err) > np.radians(30):
                        w = np.sign(err) * min(WMAX, abs(err) / DT); push(0.0, w, "rotate")
                    else:
                        push(min(V, d / DT), float(np.clip(2.0 * err, -WMAX, WMAX)), "drive")
    rows.append((t, x, y, th, 0.0, 0.0, "end"))
    return pd.DataFrame(rows, columns=["t", "x", "y", "yaw", "v", "omega", "mode"])
line = lambda *pts: ("wp", list(pts))
def sine(x0, x1, amp, lam, y0=0.0, n=None):
    xs = np.arange(x0, x1 + 1e-9, 0.15) if x1 > x0 else np.arange(x0, x1 - 1e-9, -0.15)
    return ("wp", [(float(a), float(y0 + amp * np.sin(2 * np.pi * (a - x0) / lam))) for a in xs[1:]])
rng = np.random.default_rng(20261124)
_xo = np.sort(rng.uniform(2.0, 18.0, 7)); _xr = np.sort(rng.uniform(2.0, 18.0, 7))[::-1]
rw = [(1.2, float(rng.uniform(-0.4, 0.4)))] + [(float(a), float(rng.uniform(-0.40, 0.40))) for a in _xo] + [(18.8, float(rng.uniform(-0.4, 0.4)))] \
     + [(float(a), float(rng.uniform(-0.40, 0.40))) for a in _xr] + [(1.2, float(rng.uniform(-0.4, 0.4)))]
ROUTES = {
 "N1": ("Center start, both sides", (10.5, 0.30, np.pi),
        [line((1.2, 0.30), (1.2, -0.30), (18.8, -0.30), (18.8, 0.30), (10.5, 0.30))]),
 "N2": ("Slalom out, straight back", (1.2, 0.0, 0.0),
        [sine(1.2, 18.6, 0.35, 4.0), line((18.8, 0.30)), line((1.2, 0.30))]),
 "N3": ("Anchor loops: 2 CCW (shrinking) + 1 CW", (6.0, -0.40, 0.0),
        [line((14.0, -0.40), (14.0, 0.40), (6.0, 0.40), (6.0, -0.25)), line((13.0, -0.25), (13.0, 0.25), (7.0, 0.25), (7.0, -0.40)),
         ("rot", -90), line((7.0, 0.40)), line((14.0, 0.40), (14.0, -0.40), (6.0, -0.40))]),
 "N4": ("Stop-and-look (+-45 deg) out, straight back", (1.2, -0.30, 0.0),
        sum([[line((x, -0.30)), ("stop", 1.0), ("rot", 45), ("stop", 1.0), ("rot", -90), ("stop", 1.0), ("rot", 45)] for x in np.arange(3.45, 18.0, 2.25)], [])
        + [line((18.8, -0.30), (18.8, 0.30), (1.2, 0.30))]),
 "N5": ("Far-end start, lane changes", (18.8, -0.35, np.pi),
        [line(*[(x, (-0.35 if k % 2 == 0 else 0.35)) for k, x in enumerate(np.arange(18.8, 1.1, -3.0))]), line((1.2, 0.0), (18.8, 0.0))]),
 "N6": ("Random wander out and back (seed 20261124)", (rw[0][0], rw[0][1], 0.0), [line(*rw[1:])]),
}
if __name__ == "__main__":
    out = {}
    for k, (name, st, prims) in ROUTES.items():
        D = run(st, prims); D.insert(0, "route", k); D.to_csv(f"{k}_trajectory.csv", index=False)
        rho = np.hypot(D.x - AX[0], D.y - AX[1]); sx = np.sign(D.x - AX[0]); cross = np.where(np.diff(sx) != 0)[0]
        out[k] = dict(name=name, duration_s=round(float(D.t.iloc[-1]), 1), path_m=round(float(np.sum(D.v) * DT), 1),
                      start_rho_m=round(float(rho.iloc[0]), 2), anchor_passes=int(len(cross)),
                      pass_sides=["+y" if D.y.iloc[i] > 0 else "-y" for i in cross], near_frac_rho_lt3=round(float((rho < 3).mean()), 2),
                      rotate_frac=round(float((D["mode"] == "rotate").mean()), 2), yaw_span_deg=int(np.ptp(np.degrees(np.unwrap(D.yaw)))),
                      x_range=[round(float(D.x.min()), 2), round(float(D.x.max()), 2)], y_absmax=round(float(D.y.abs().max()), 2),
                      max_v=round(float(D.v.max()), 3), max_omega_deg_s=round(float(np.degrees(D.omega.abs().max())), 1))
    json.dump(out, open("SUMMARY.json", "w"), indent=1); print(pd.DataFrame(out).T.drop(columns=["pass_sides"]).to_string())
