"""Trilinear surrogate of the FFD observation model on (x, y, psi). psi is periodic; outside the x/y box it falls back to FFD."""
import numpy as np, glob, os
from common import SUR
GRID = SUR + "/ffd_grid.npz"
X0, DX, NX = 0.5, 0.025, 761
Y0, DY, NY = -1.0, 0.05, 41
P0, DP, NP = -np.pi, np.radians(4.0), 90
_g = None
def _load():
    global _g
    if _g is None:
        if not os.path.exists(GRID):
            ch = sorted(glob.glob(SUR + "/chunk_*.npz"))
            h = np.concatenate([np.load(c)["h"] for c in ch]); H = np.concatenate([np.load(c)["H"] for c in ch])
            assert h.shape[0] == NX
            np.savez(GRID, h=h.astype(np.float64), H=H.astype(np.float64))
        Z = np.load(GRID); _g = (Z["h"], Z["H"])
    return _g
STATS = {"calls": 0, "fallback": 0}
def batch(X):
    """X[n,3] -> h[n,2], H[n,2,3]"""
    h, H = _load(); X = np.atleast_2d(X); n = len(X)
    fx = (X[:, 0] - X0) / DX; fy = (X[:, 1] - Y0) / DY; fp = ((X[:, 2] - P0) % (2 * np.pi)) / DP
    ix = np.floor(fx).astype(int); iy = np.floor(fy).astype(int); ip = np.floor(fp).astype(int) % NP
    inside = (ix >= 0) & (ix < NX - 1) & (iy >= 0) & (iy < NY - 1)
    STATS["calls"] += n; STATS["fallback"] += int((~inside).sum())
    oh = np.empty((n, 2)); oH = np.empty((n, 2, 3))
    if inside.any():
        a = ix[inside]; b = iy[inside]; c = ip[inside]; c1 = (c + 1) % NP
        tx = (fx[inside] - a)[:, None]; ty = (fy[inside] - b)[:, None]; tp = (fp[inside] - np.floor(fp[inside]))[:, None]
        acc_h = 0; acc_H = 0
        for dx, wx in ((0, 1 - tx), (1, tx)):
            for dy, wy in ((0, 1 - ty), (1, ty)):
                for cc, wp in ((c, 1 - tp), (c1, tp)):
                    w = wx * wy * wp
                    acc_h = acc_h + w * h[a + dx, b + dy, cc]; acc_H = acc_H + w[:, :, None] * H[a + dx, b + dy, cc]
        oh[inside] = acc_h; oH[inside] = acc_H
    if (~inside).any():
        from common import env
        e = env(); hh, HH = e["model"].batch(np.c_[X[~inside], np.zeros((~inside).sum())], e["spec"]); oh[~inside] = hh; oH[~inside] = HH[:, :, :3]
    return oh, oH
def sur_h(nav3):
    h, H = batch(np.asarray(nav3, float)[None]); return h[0], H[0]
