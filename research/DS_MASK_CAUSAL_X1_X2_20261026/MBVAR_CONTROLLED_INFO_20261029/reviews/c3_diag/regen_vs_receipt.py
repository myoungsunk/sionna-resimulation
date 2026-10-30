"""Third-machine check: regenerate S1V3 DEV2 field-10 inputs locally and compare z with the committed S1V3 receipt.
Run from the experiment directory with REFLECT_ROOT set (reflect_model/fetch_inputs.sh, FETCH_RF=0)."""
import sys; sys.path.insert(0, "code")
import numpy as np, s0v2 as S0V2, s1_mc as M, s1v2 as V, s1v3 as T
lk = S0V2.lock_v2(); S = V.setup(lk); root = M.seed_root()
with np.load("results/P2_S1V3_run_40981032471/S1V3_INPUTS_DEV2_10.zip") as z:
    rec = {k: z[k] for k in z.files}
for cn in ("LOWCORR", "POSE_HIGH", "TIME_5"):
    cell = S["cells"][cn]
    pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], 10, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
    for role in ("LOW", "HIGH"):
        inp = T.make_inputs(S, root, 10, cn, S["wins"][role], 0, pf)
        print(cn, role, "max|z_local - z_receipt| = %.3g" % np.abs(inp["z"] - rec[f"10|{role}|{cn}|0|z"]).max())
print("world pose kernel sqrt", S["Lhalf"].shape, "eig range", S["psd"])
