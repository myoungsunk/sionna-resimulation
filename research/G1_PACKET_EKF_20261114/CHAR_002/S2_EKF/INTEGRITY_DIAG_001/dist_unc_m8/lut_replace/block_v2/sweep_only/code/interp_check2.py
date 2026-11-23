"""Where does the interpolation error come from? Block built from LoS station curves; compared with FFD at
 (a) station positions, (b) mid-column x (+0.225 m) on station lines, (c) station x between lines (y midpoints), (d) psi off-grid (+5 deg)."""
import sys, numpy as np
for p in ("/home/claude/m8", "/home/claude/lut0", "/home/claude/lut4"): sys.path.insert(0, p)
from common import env
import h_ref as HR, sw_block as SB
e0 = env(); base, spec = e0["model"], e0["spec"]; ffd = HR.ffd_s_fn(base)
ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); L = np.full_like(SB.F, np.nan); L[SB.ix, SB.iy, SB.ip] = SB.SW.s_fp.values - ES0; SB.F = L; B = SB.SWB()
def test(name, xs, ys, dpsi=0.):
    out = {0: [], 1: [], 2: []}
    for x in xs:
        for y in ys:
            rho = np.hypot(x - 10, y); q = int(np.clip(np.searchsorted(SB.EDG, rho, side="right") - 1, 0, 2)); ps = SB.PSI + np.radians(dpsi)
            s = B.eval(np.full(36, x), np.full(36, y), ps)[0]; h, J = ffd(np.c_[np.full(36, x), np.full(36, y), ps, np.zeros(36)], spec)
            out[q].append((np.sqrt(np.mean((s - h)**2)), np.degrees(-np.mean((s - h) * J[:, 2]) / np.mean(J[:, 2]**2))))
    print(name, {["<3", "3-6", ">=6"][q]: (round(float(np.sqrt(np.mean(np.array(v)[:, 0]**2))), 4), round(float(np.mean(np.array(v)[:, 1])), 2), round(float(np.std(np.array(v)[:, 1])), 2)) for q, v in out.items() if v})
test("stations      ", SB.XS, SB.YS)
test("x mid-column  ", (SB.XS[:-1] + SB.XS[1:]) / 2, SB.YS)
test("y mid-line    ", SB.XS, (SB.YS[:-1] + SB.YS[1:]) / 2)
test("psi +5 deg    ", SB.XS, SB.YS, 5.)
