"""FFD grid for the surrogate. usage: gen_grid.py i0 i1  (x-index range). Grid: x 0.5..19.5 step .025, y -1..1 step .05, psi 90 x 4deg."""
import sys, numpy as np, math, time
from multiprocessing import Pool
XS = np.round(np.arange(0.5, 19.5 + 1e-9, 0.025), 6); YS = np.round(np.arange(-1.0, 1.0 + 1e-9, 0.05), 6)
PS = np.radians(np.arange(-180, 180, 4.0))
def work(ix):
    from common import env
    e = env(); m, sp = e["model"], e["spec"]
    out_h = np.empty((len(ix), len(YS), len(PS), 2), np.float64); out_H = np.empty((len(ix), len(YS), len(PS), 2, 3), np.float64)
    for a, i in enumerate(ix):
        Y, Pp = np.meshgrid(YS, PS, indexing="ij")
        X = np.c_[np.full(Y.size, XS[i]), Y.ravel(), Pp.ravel(), np.zeros(Y.size)]
        h, H = m.batch(X, sp)
        out_h[a] = h.reshape(len(YS), len(PS), 2); out_H[a] = H[:, :, :3].reshape(len(YS), len(PS), 2, 3)
    return ix[0], out_h, out_H
if __name__ == "__main__":
    i0, i1 = int(sys.argv[1]), min(int(sys.argv[2]), len(XS)); t = time.time()
    idx = np.arange(i0, i1); parts = np.array_split(idx, 2 * max(1, len(idx) // 20))
    with Pool(2) as pool: res = pool.map(work, parts)
    res.sort(key=lambda r: r[0])
    import os; from common import SUR; os.makedirs(SUR, exist_ok=True)
    np.savez(f"{SUR}/chunk_{i0:04d}_{i1:04d}.npz", ix=idx, h=np.concatenate([r[1] for r in res]), H=np.concatenate([r[2] for r in res]))
    print(f"x-index {i0}..{i1} ({len(idx)} rows) done in {time.time()-t:.0f}s")
