"""Frozen position table for the BLOCK_C M7 station-sweep extension (A1, A2, A3, B1, C1).
Centerline station P(n) is at x = 0.75 + 0.45 n, y = 0 (BLOCK_C_CENTERLINE_M7_20261118); anchor B x = 10, so rho = 10 - x on y = 0.
Existing 4 cm points (BLOCK_C_M7_NEAR_20261119): y = 0, dx in {+-4..+-16} cm around P016, P010, P003."""
import csv, itertools
X = lambda n: round(0.75 + 0.45 * n, 2)
C4 = (-16, -12, -8, -4, 4, 8, 12, 16)
EXIST = {(X(n) * 100, 0) for n in range(40)}
EXIST |= {(round(X(n) * 100) + d, 0) for n in (16, 10, 3) for d in C4}
rows, seen = [], set()
def add(s, sid, cen, x_cm, y_cm, yaws=36, reuse=False):
    k = (round(x_cm), round(y_cm))
    if not reuse:
        assert k not in EXIST and k not in seen, (s, sid, k); seen.add(k)
    rows.append(dict(set=s, station_id=sid, center_id=cen, x=round(x_cm / 100, 2), y=round(y_cm / 100, 2), z=0.45,
                     rho_center=round(10 - X(int(cen[1:4])), 2), n_yaw=yaws, yaw_step_deg=360 / yaws, reuse_existing=int(reuse)))
nm = lambda c, a, d: f"{c}_{a}_{'M' if d < 0 else 'P'}{abs(d):02d}CM"
# A1: fine y-lines at existing fine-x centers, 1 cm to +-8 cm and 4 cm to +-16 cm
for n in (16, 10, 3):
    c = f"P{n:03d}"
    for d in (-16, -12, -8, -7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16):
        add("A1", nm(c, "DY", d), c, X(n) * 100, d)
# A2: extra mid centers (centers reused from the centerline run) + off-centerline center at y = 0.30
for n in (13, 11, 8):
    c = f"P{n:03d}"
    for d in C4: add("A2", nm(c, "DX", d), c, X(n) * 100 + d, 0)
add("A2", "P010_Y30", "P010", X(10) * 100, 30)
for d in C4: add("A2", nm("P010_Y30", "DX", d), "P010", X(10) * 100 + d, 30)
# A3: extra far centers, x and y lines at 4 cm
for n in (6, 1):
    c = f"P{n:03d}"
    for d in C4: add("A3", nm(c, "DX", d), c, X(n) * 100 + d, 0)
    for d in C4: add("A3", nm(c, "DY", d), c, X(n) * 100, d)
# B1: 2D 9 x 9 patch, 4 cm, +-16 cm, excluding points already on the x-line (y = 0) or the A1 y-line (dx = 0)
for n in (16, 10, 3):
    c = f"P{n:03d}"
    for dx, dy in itertools.product(range(-16, 17, 4), repeat=2):
        if dx == 0 or dy == 0: continue
        add("B1", f"{c}_DX_{'M' if dx < 0 else 'P'}{abs(dx):02d}_DY_{'M' if dy < 0 else 'P'}{abs(dy):02d}CM", c, X(n) * 100 + dx, dy)
# C1: fine yaw (2.5 deg) at existing positions: centers and +-4 cm x points (re-trace; 36-yaw subset must be byte-equal)
for n in (16, 10, 3):
    c = f"P{n:03d}"
    for d in (-4, 0, 4): add("C1", c if d == 0 else nm(c, "DX", d), c, X(n) * 100 + d, 0, yaws=144, reuse=True)
with open("../POSITIONS_EXT.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
from collections import Counter
cnt = Counter(r["set"] for r in rows); print(cnt, len(rows))
