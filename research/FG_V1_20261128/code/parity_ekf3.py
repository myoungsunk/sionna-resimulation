import numpy as np
from common import *
import ekf3
anchor = env()["spec"]["anchor"]
for cond in ("B0", "L2_GYRO_ARW"):
    p = packet(cond, 10, "R2"); ref = np.load(f"{M}/attempt_02/replay/cells/{cond}/own/seed10/R2/H2/trace.npz")
    tr = ekf3.replay(p, ffd_h, cond, nstate=4, anchor=anchor)
    print(cond, "4-state vs M7 H2: max|dx|", np.abs(tr["x"] - ref["x"]).max(), " max|dP|", np.abs(tr["P"] - ref["P"]).max(), " mask equal", bool((tr["mask"] == ref["mask"]).all()))
