"""Sensitivity of h=[r, s] to a rigid rotation of the pose about the anchor's vertical axis vs heading-only rotation, along R5 k=0..156."""
import json, numpy as np
from common import *
import ekf3, surrogate as S
an = np.array(env()["spec"]["anchor"][:2]); p = packet("B0", 10, "R5"); T = truth("R5")
ekf = ekf3.replay(p, ffd_h, "B0", nstate=3, anchor=env()["spec"]["anchor"])
def h_at(x): return ffd_h(x)[0]
def rot_about_anchor(x, th):
    c, s = np.cos(th), np.sin(th); d = x[:2] - an; return np.r_[an + [c * d[0] - s * d[1], s * d[0] + c * d[1]], x[2] + th]
eps = 1e-4; rows = []
for k in range(0, 157):
    x = T[k]; hp = h_at(rot_about_anchor(x, eps)); hm = h_at(rot_about_anchor(x, -eps)); d_rig = (hp - hm) / (2 * eps)
    hp2 = h_at(x + [0, 0, eps]); hm2 = h_at(x - [0, 0, eps]); d_psi = (hp2 - hm2) / (2 * eps)
    rows.append((d_rig[0], d_rig[1], d_psi[1], np.sqrt(ekf["Reff"][k][1, 1]), np.sqrt(ekf["Reff"][k][0, 0]), ekf["mask"][k]))
R = np.array(rows); m = R[:, 5] > 0
info_rig = float(np.sum((R[m, 1] / R[m, 3])**2 + (R[m, 0] / R[m, 4])**2)); info_psi = float(np.sum((R[m, 2] / R[m, 3])**2))
out = dict(ds_drigid_median_abs=float(np.median(abs(R[:, 1]))), ds_dpsi_median_abs=float(np.median(abs(R[:, 2]))), dr_drigid_max_abs=float(abs(R[:, 0]).max()),
           ratio_rigid_to_heading_sensitivity=float(np.median(abs(R[:, 1])) / np.median(abs(R[:, 2]))),
           fisher_info_rigid_rotation_white=info_rig, fisher_info_heading_only_white=info_psi,
           sigma_rigid_deg_white=float(np.degrees(1 / np.sqrt(info_rig))), sigma_heading_deg_white=float(np.degrees(1 / np.sqrt(info_psi))))
print(json.dumps(out, indent=1)); json.dump(out, open(OUT + "/diag_r5_rigid_rotation.json", "w"), indent=1)
