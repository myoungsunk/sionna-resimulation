"""Parity check: re-run the M7 EKF replay (H1, H2) here and compare with the published traces."""
import sys, json, numpy as np
from pathlib import Path
REPO = Path("/home/claude/sionna-resimulation")
M = REPO / "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1"
sys.path.insert(0, str(M))
import m7_replay as R7
A2 = M / "attempt_02"
CON = json.load(open(A2 / "replay/RUN_CONTRACT.json")); P = CON["parameters"]["R2"]
env = R7.load_environment("/home/claude/fgv1/base.json")
Z = np.load(A2 / "input_generation/inputs/B0/seed10/R2_online.npz")
pkt = {k: Z[k] for k in ("t","pose_id","z","muMB","muBASE","R","D","x0","P0","ds","gy","dt")}
print({k: v.shape for k, v in pkt.items()})
for arm in ("H1", "H2"):
    tr = R7.replay(pkt, env, arm, sigma_b=P["sigma_b"], condition="B0", rref_policy="own", sigma_rad=0.)
    ref = np.load(A2 / f"replay/cells/B0/own/seed10/R2/{arm}/trace.npz")
    common = [k for k in ref.files if k in tr]
    worst = {k: float(np.nanmax(np.abs(np.asarray(tr[k], float) - ref[k].astype(float)))) for k in common if ref[k].dtype.kind in "fc" and np.asarray(tr[k]).shape == ref[k].shape}
    print(arm, "fields", len(common), "max|diff| x:", worst.get("x"), "P:", worst.get("P"), "overall:", max(worst.values()) if worst else None)
