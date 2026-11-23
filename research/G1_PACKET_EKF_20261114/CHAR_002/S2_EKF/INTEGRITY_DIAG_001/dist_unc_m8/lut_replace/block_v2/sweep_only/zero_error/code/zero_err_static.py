"""Block error caused by the heading zero error, at the packet truth poses (B0 seed 10 routes): m_err - m_clean, heading-equivalent and RMS by bin;
and s_full residual RMS / heading-equivalent of each block."""
import sys, numpy as np, pandas as pd
for p in ("/home/claude/m8", "/home/claude/lut5", "/home/claude/lut6", "/home/claude/lut2", "/home/claude/m8cal"): sys.path.insert(0, p)
from common import packet
import zero_err as ZE, stage2_static as S2
B0, _ = ZE.build(None); blocks = {k: ZE.build(k)[0] for k in ("Z1", "Z2", "G2")}; rows = []
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); T = S2.F[S2.F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    x, y, ps = T.x_eval.values, T.y_eval.values, T.yaw_eval_rad.values; s = T.s_fp.values; rho = np.hypot(x - 10, y); b = np.clip(np.searchsorted([0, 3, 6, 10], rho, side="right") - 1, 0, 2)
    m0, _, _, a0 = B0.eval(x, y, ps)
    for k, B in blocks.items():
        m, _, _, a = B.eval(x, y, ps); d = m - m0; e = s - m
        for q in range(3):
            w = b == q; rows.append(dict(route=r, kind=k, bin=["<3 m", "3-6 m", ">=6 m"][q], n=int(w.sum()), dm_rms=np.sqrt(np.mean(d[w]**2)), dm_head_eq=np.degrees(-np.mean(d[w] * a0[w]) / np.mean(a0[w]**2)),
                                         res_rms=np.sqrt(np.mean(e[w]**2)), res_head_eq=np.degrees(-np.mean(e[w] * a[w]) / np.mean(a[w]**2))))
D = pd.DataFrame(rows); D.to_csv("ZERR_STATIC.csv", index=False)
A = D.groupby(["kind", "bin"]).apply(lambda q: pd.Series(dict(dm_rms=np.sqrt(np.average(q.dm_rms**2, weights=q.n)), dm_head_eq=np.average(q.dm_head_eq, weights=q.n),
      res_rms=np.sqrt(np.average(q.res_rms**2, weights=q.n)), res_head_eq=np.average(q.res_head_eq, weights=q.n)))).reset_index()
pd.set_option("display.width", 200); print(A.round(4).to_string(index=False))
