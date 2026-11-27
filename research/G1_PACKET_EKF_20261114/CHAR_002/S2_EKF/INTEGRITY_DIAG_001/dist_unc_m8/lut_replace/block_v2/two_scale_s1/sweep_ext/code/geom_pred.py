"""Geometry-only prediction (no RT data): first-order image paths in BLOCK_C (20 x 2.4 x 2.7 m, anchor B (10, 0, 2.65), tag z 0.45).
For each path k: excess length dL_k, first-path-tap weight sinc^2(dL_k B / c), gradient g_k = grad(dL_k) at the tag,
single-path length l_k(u) = lambda / (2 pi |g_k . u|) for u = x, y."""
import numpy as np, csv
A = np.array([10.0, 0.0, 2.65]); C = 299792458.0; LAM = C / 6.5e9; B = 499.2e6
IMG = {"floor": lambda a: [a[0], a[1], -a[2]], "ceiling": lambda a: [a[0], a[1], 2 * 2.7 - a[2]],
       "wall_y_pos": lambda a: [a[0], 2 * 1.2 - a[1], a[2]], "wall_y_neg": lambda a: [a[0], -2 * 1.2 - a[1], a[2]]}
rows = []
for n in (16, 13, 11, 10, 8, 6, 3, 1):
    x = round(0.75 + 0.45 * n, 2); t = np.array([x, 0.0, 0.45]); L0 = np.linalg.norm(t - A)
    for k, f in IMG.items():
        I = np.array(f(A)); L = np.linalg.norm(t - I); dL = L - L0; g = (t - I) / L - (t - A) / L0
        lx = LAM / (2 * np.pi * abs(g[0])) if abs(g[0]) > 1e-12 else np.inf
        ly = LAM / (2 * np.pi * abs(g[1])) if abs(g[1]) > 1e-12 else np.inf
        rows.append(dict(center=f"P{n:03d}", rho=round(10 - x, 2), path=k, dL_m=round(dL, 3), tap_w=round(float(np.sinc(dL * B / C) ** 2), 3),
                         l_x_m=round(lx, 3), l_y_m=round(ly, 4)))
with open("../PRED_GEOM_IMAGE.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for r in rows: print(r)
