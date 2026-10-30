"""C3 run 40992589158: reproduction failures broken down by the size of the regenerated-input difference d_z."""
import pandas as pd
C = pd.read_csv("results/P2_C3_run_40992589158/C3_ROWS.csv", low_memory=False)
bad = (C.d_state_dref > 1e-6) | (C.d_cost > 1e-6) | (C.d_P_C10_rel > 1e-3) | (C.same_class_v3 != True)
print("rows", len(C), "repro-bad (state>1e-6 d_ref | cost>1e-6 | P_C10>1e-3 | class differs)", int(bad.sum()))
for lab, m in (("d_z == 0", C.d_z == 0), ("0 < d_z <= 1e-12", (C.d_z > 0) & (C.d_z <= 1e-12)),
               ("1e-12 < d_z < 1e-9", (C.d_z > 1e-12) & (C.d_z < 1e-9)), ("d_z >= 1e-9", C.d_z >= 1e-9)):
    d = C[m]
    print(f"{lab:20s} rows {len(d):4d}  bad {int(bad[m].sum()):3d}  max state {d.d_state_dref.max():.3g} d_ref  max cost {d.d_cost.max():.3g}  max P_C10 {d.d_P_C10_rel.max():.3g}"
          if len(d) else f"{lab:20s} rows 0")
print("cells with d_z >= 1e-9:", C[C.d_z >= 1e-9].groupby(["role", "cell"]).size().to_dict())
r = C.loc[C.d_state_dref.idxmax()]
print("largest deviation row:", {k: r[k] for k in ("field", "role", "cell", "sensor_seed", "arm", "d_z", "d_state_dref", "d_cost", "d_P_C10_rel", "conv", "class_v3", "kink_poses_at_E")})
print("STATE_STABILITY max row:", C.loc[C.E_vs_best_dref.idxmax(), ["field", "role", "cell", "sensor_seed", "arm", "E_vs_best_dref", "gap_E", "best_start"]].to_dict())
