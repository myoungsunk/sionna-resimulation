"""BVK (cause check for the near range): BV block + kriging mean correction for rho < 3 m only (labels e = s_full - m at stations,
S0 near hyperparameters); near-bin table from the LOSO kriging residual; mid/far bins from the BV table."""
import sys, json, numpy as np
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut2"); sys.path.insert(0, "/home/claude/lut3"); sys.path.insert(0, "/home/claude/lut0")
from common import env
import h_ref as HR, bv_block as BVM, stage2_static as S2
e0 = env(); base, spec = e0["model"], e0["spec"]; SW = S2.SW; bv = BVM.BV(HR.ffd_s_fn(base), spec, SW)
Xs = np.c_[SW.x_eval, SW.y_eval, SW.psi, np.zeros(len(SW))]; m, J = bv.s_fn()(Xs, spec); a = J[:, 2]; e = SW.s_fp.values - m
prm = S2.KP["e_s|0"]["params"]; mu = np.full(len(e), np.nan); b0 = S2.BIN == 0
for st in np.unique(S2.POS[b0]):
    te = S2.POS == st; tr = (~te) & b0; Xt, yt = S2.X3[tr], e[tr]; m0 = yt.mean()
    for i in np.flatnonzero(te): mu[i] = S2.kr_one(Xt, yt, m0, S2.X3[i], prm)
T = bv.table(SW); c1, c0 = S2.fitB((e - mu)[b0], a[b0]); T["c1"][0], T["c0"][0] = c1, c0
np.save("ES_BV.npy", e); json.dump(T, open("TABLE_BVK.json", "w"))
print("near: label rms", np.sqrt(np.mean(e[b0]**2)), "LOSO resid rms", np.sqrt(np.mean((e - mu)[b0]**2)), "table", T)
