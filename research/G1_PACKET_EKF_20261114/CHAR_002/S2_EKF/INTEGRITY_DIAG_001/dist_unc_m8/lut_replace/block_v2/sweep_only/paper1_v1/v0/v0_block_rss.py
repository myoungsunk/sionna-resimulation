"""V0-3 block freeze + V0-2 simple distance-bin R_ss (no a^2 term). Sweep-only (RT Corridor BLOCK_C, anchor B)."""
import json, hashlib, numpy as np, sw_block_fullco as B
blk = B.SWB()                                   # full-column block (frozen candidate)
C, info = B.build_station_coefs()
Y = np.concatenate([C.real, C.imag], 2)
h = lambda a: hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
tab_fullco, E, A = B.column_out_table()        # x-column-out residuals e = s_full - m_(-col), a = dm/dpsi
b = np.clip(np.searchsorted(B.EDG, B.RHO, side="right") - 1, 0, 2)
out = dict(block=dict(K=B.K, XS=[float(B.XS[0]), float(B.XS[-1]), len(B.XS)], YS=B.YS.tolist(), n_yaw=36,
                      coef_sha256=h(Y), grid_rule="x: cubic spline inside [1.2,18.75], extrapolation outside; y: linear inside [-0.45,0.45], clamped outside with dm/dy=0"),
           c1a2c0_reproduced=tab_fullco, simple=[])
for q in range(3):
    e = E[b == q].ravel(); a = A[b == q].ravel()
    hi = np.abs(a) >= np.quantile(np.abs(a), .8); lo = np.abs(a) <= np.quantile(np.abs(a), .2)
    out["simple"].append(dict(bin=[float(B.EDG[q]), float(B.EDG[q+1])], n=int(e.size), mean=float(e.mean()), var=float(e.var()), sd=float(e.std()),
        cov95_simple=float(np.mean(np.abs(e - e.mean()) <= 1.96 * e.std())),
        ratio_e2_over_var_top_abs_a=float(np.mean(e[hi]**2) / e.var()), ratio_e2_over_var_bottom_abs_a=float(np.mean(e[lo]**2) / e.var()),
        model_c1a2c0_mean=float(np.mean(tab_fullco["c1"][q] * a**2 + tab_fullco["c0"][q]))))
json.dump(out, open("V0_BLOCK_RSS.json", "w"), indent=1)
np.savez("V0_COLOUT.npz", E=E, A=A, RHO=B.RHO, XS=B.XS, YS=B.YS)
print(json.dumps(out, indent=1))
