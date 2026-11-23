"""Interpolation check: build the sweep block from the LoS (FFD) station curves instead of s_full; compare with FFD at packet poses.
Isolates the error of the block construction / interpolation itself (no multipath)."""
import sys, numpy as np, pandas as pd
for p in ("/home/claude/m8", "/home/claude/m8cal", "/home/claude/lut2", "/home/claude/lut0", "/home/claude/lut4"): sys.path.insert(0, p)
from common import env, packet
import h_ref as HR, stage2_static as S2, sw_block as SB
e0 = env(); base, spec = e0["model"], e0["spec"]; ffd = HR.ffd_s_fn(base)
ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); L = np.full_like(SB.F, np.nan); L[SB.ix, SB.iy, SB.ip] = SB.SW.s_fp.values - ES0
SB.F = L; B = SB.SWB(); rows = []
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); T = S2.F[S2.F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    X = np.c_[T.x_eval, T.y_eval, T.yaw_eval_rad, np.zeros(len(T))]; rho = np.hypot(T.x_eval - 10, T.y_eval).values; b = np.clip(np.searchsorted(SB.EDG, rho, side="right") - 1, 0, 2)
    hF, JF = ffd(X, spec); s, _, _, _ = B.eval(X[:, 0], X[:, 1], X[:, 2]); d = s - hF; ins = (T.y_eval.values >= -0.45) & (T.y_eval.values <= 0.45)
    for q in range(3):
        for lab, m in (("all", b == q), ("|y|<=0.45", (b == q) & ins)):
            rows.append(dict(route=r, bin=q, sel=lab, n=int(m.sum()), rms=np.sqrt(np.mean(d[m]**2)), head_eq=np.degrees(-np.mean(d[m] * JF[m, 2]) / np.mean(JF[m, 2]**2))))
D = pd.DataFrame(rows); print(D.groupby(["bin", "sel"]).apply(lambda q: pd.Series(dict(n=q.n.sum(), rms=np.sqrt(np.average(q.rms**2, weights=q.n)), head_eq=np.average(q.head_eq, weights=q.n), by_route=list(np.round(q.head_eq, 2))))).to_string())
