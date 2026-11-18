"""O1 parity: (1) frozen FFD synthetic LoS (hs_lut.los_h, corridor convention) vs Office RT Direct-LoS H;
(2) frozen extractor range/s_fp vs RT first-path table. Office anchor O0=(5,2.2,2.65), robot z 0.45, mount 0."""
import sys, json, numpy as np, pandas as pd
SRC = "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_model003_src"
sys.path.insert(0, SRC); sys.path.insert(0, "/home/claude/m8cal")
from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
from feats import features, B_OLD
banks = [pat.Bank(dict(np.load(f"/home/claude/rel/{n}", allow_pickle=False))) for n in ("LP_plus45_bank.npz", "LP_minus45_bank.npz")]
A = np.array([5., 2.2, 2.65]); ZR = .45
def o30(c):
    m = np.abs(c); b = m.max(axis=1).argmax(axis=1); s = np.take_along_axis(m, b[:, None, None], axis=2)[:, :, 0]; pk = s.max(axis=1)
    return (s >= .3 * pk[:, None]).argmax(axis=1)
def s_at(c, i):
    p = np.abs(c[np.arange(len(c)), i, :])**2; return (p[:, 0] - p[:, 1]) / p.sum(axis=1)
out = {}
for o in ("O01", "O02", "O03"):
    d = f"/home/claude/office/rel/{o}_M0/CASES/{o}_O0_M0_FULL"
    P = pd.read_csv(f"{d}/RADIO_POSE.csv"); Hl = np.load(f"{d}/H_DIRECT_LOS.npy"); Hf = np.load(f"{d}/H_FULL.npy")
    los = np.load(f"{d}/LOS_EXISTS.npy")
    delta = np.c_[P.x_m, P.y_m, np.full(len(P), ZR)] - A; dist = np.linalg.norm(delta, axis=1); dirn = delta / dist[:, None]
    Hs = np.stack([model.los_h(banks, dirn[i], float(P.yaw_antenna_deg[i]), float(dist[i])) for i in range(len(P))])
    m = los.astype(bool)
    rel = np.linalg.norm((Hs - Hl)[m].reshape(m.sum(), -1), axis=1) / np.linalg.norm(Hl[m].reshape(m.sum(), -1), axis=1)
    cl, cs = obs.cir_batch(Hl[..., 0]), obs.cir_batch(Hs[..., 0]); il = o30(cl)
    ds = np.abs(s_at(cs, il) - s_at(cl, il))[m]
    F = features(Hf); er = F.range_m.to_numpy() - (dist + B_OLD)
    FP = pd.read_csv(f"{d}/FIRST_PATH.csv")
    out[o] = dict(n=len(P), los_frac=float(m.mean()), H_rel_err_median=float(np.median(rel)), H_rel_err_p90=float(np.quantile(rel, .9)),
                  s_abs_err_p90=float(np.quantile(ds, .9)), s_abs_err_max=float(ds.max()),
                  e_r_cm_LoS_median=float(100 * np.median(er[m])), e_r_cm_NLoS_median=float(100 * np.median(er[~m])) if (~m).any() else None,
                  valid_frac=float(F.valid.mean()), first_path_cols=list(FP.columns)[:12])
    print(o, json.dumps(out[o]))
# mirror-convention probe: same check with anchor frame flipped (yaw -> -yaw, and +180)
o = "O02"; d = f"/home/claude/office/rel/{o}_M0/CASES/{o}_O0_M0_FULL"
P = pd.read_csv(f"{d}/RADIO_POSE.csv"); Hl = np.load(f"{d}/H_DIRECT_LOS.npy")
delta = np.c_[P.x_m, P.y_m, np.full(len(P), ZR)] - A; dist = np.linalg.norm(delta, axis=1); dirn = delta / dist[:, None]
for lab, f in (("yaw+180", lambda y: y + 180), ("-yaw", lambda y: -y)):
    Hs = np.stack([model.los_h(banks, dirn[i], float(f(P.yaw_antenna_deg[i])), float(dist[i])) for i in range(0, len(P), 10)])
    r = np.linalg.norm((Hs - Hl[::10]).reshape(len(Hs), -1), axis=1) / np.linalg.norm(Hl[::10].reshape(len(Hs), -1), axis=1)
    print("probe", lab, "median rel", float(np.median(r)))
json.dump(out, open("/home/claude/office/O1_PARITY.json", "w"), indent=1)
