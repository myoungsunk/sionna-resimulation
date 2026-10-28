"""Rebuild E1 packet inputs (z, mu_B, mu_M, R) from Full RF H with the original feature / OOF code.

Original sources (unchanged, imported):
  PHYSICS_RS_STAGED_20261015/code/features.py      extract()            -> z = [range_m, s_fp], features
  R5_N4B_20261015/n4b_rf_errors.py                 fit_model('POWER_BIN_JOINT'), site_weights()
                                                   -> POWER_DIAG mu_B = (mu_r, mu_s), R = diag(Vr, Vs)   (power_oof_experiment.fit_models)
  PJ_DS_GATED_20261021/series_dump.py              taps() -> ds_+-k
  mu_recursive.hgb(EXIST + DS, 'e_r')              -> mu_M_r = EXDS prediction                            (mu_recursive.main)
Training sets are the ORIGINAL folds: Full rows of the 7 original cases, target route held out, XY duplicates of the
target removed (POWER only).  New mount-45 cases are prediction-only (never in training).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
SRC = HERE / "src" / "research"
for p in ("PHYSICS_RS_STAGED_20261015/code", "R5_N4B_20261015", "PJ_DS_GATED_20261021"):
    sys.path.insert(0, str(SRC / p))
sys.path.insert(0, str(HERE.parent / "pbtest" / "reflect_model"))
import common as C  # noqa: E402
from features import extract, FEATURES, GROUPS  # noqa: E402
import n4b_rf_errors as B  # noqa: E402

OFFS = [-8, -4, -2, -1, 1, 2, 4, 8]
DS = [f"ds_{o:+d}" for o in OFFS]
EXIST = ['log_fp_power', 'abs_s_fp', 'early4', 'early8', 'early16', 'delay_rms_ns', 'peak_diff_ns', 'eta_fp_win80', 's_diff4', 's_diff8', 's_diff16',
         'tap_pol_var80', 'jones_diversity', 'freq_s_var', 'detector_s_span', 'detector_delay_span_ns']
ROUTE = lambda cid: cid[:2]
NEW_CASES = {f"{r}_m45": dict(anchor=C.CASES[f"{r}_m0"]["anchor"], robot_z_m=0.45, mount_deg=45.0) for r in ("R2_aB", "R4_aA", "R4_aB", "R5_aA", "R5_aB")}
M45_DIR = HERE.parent / "m45"


def taps(H):
    """series_dump.taps (copied verbatim minus the module-level imports it would pull in)."""
    H = np.asarray(H, np.complex128); n, nf, _ = H.shape; nt = 4 * nf; ii = np.arange(n)
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[None, :, None], n=nt, axis=1) * nf; amp = np.abs(cir); power = amp ** 2
    branch = amp.max(axis=1).argmax(axis=1); strong = amp[ii, :, branch]; peaks = strong.max(axis=1)
    tap = (strong >= .3 * peaks[:, None]).argmax(axis=1); s = {}
    for o in [0] + OFFS:
        idx = tap + o; ok = (idx >= 0) & (idx < nt); idc = np.clip(idx, 0, nt - 1); P = power[ii, idc, :]; den = P.sum(axis=1)
        s[o] = np.where(ok & (den > 0), (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1), np.nan)
    out = {f'ds_{o:+d}': s[o] - s[0] for o in OFFS}; out['s_fp_chk'] = s[0]; out['fp_rel_power'] = peaks
    return out


def case_spec(cid):
    return C.CASES[cid] if cid in C.CASES else NEW_CASES[cid]


def load_H(cid):
    p = (M45_DIR / f"H_{cid}.npy") if cid in NEW_CASES else (C.ROOT / "rf" / f"H_{cid}.npy")
    return np.load(p, mmap_mode="r")


def features_for(cid, model):
    """build_dataset() for one case, Full channel: features + labels e_r/e_s against SourceFFD at the true pose."""
    route_m0 = cid.replace("m45", "m0") if cid in NEW_CASES else cid
    smp = pd.DataFrame(json.loads((C.ROOT / "rf" / f"SAMPLES_{route_m0}.json").read_text()))
    pose = smp[['x', 'y', 'yaw_body_deg']].to_numpy(float).copy(); pose[:, 2] = np.radians(pose[:, 2]); ids = smp.pose_id.to_numpy(int)
    spec = case_spec(cid)
    pred = np.vstack([model.batch(pose[k:k + 64], spec, gradient=False)[0] for k in range(0, len(pose), 64)])
    H = load_H(cid); assert len(H) == len(pose), (cid, H.shape, len(pose))
    blocks = [extract(np.asarray(H[k:k + 64, :, :, 0]), model.freqs) for k in range(0, len(H), 64)]
    q = {name: np.concatenate([b[name] for b in blocks]) for name in blocks[0]}; assert np.all(q['valid'])
    d = pd.DataFrame({'case': cid, 'route': ROUTE(cid), 'channel': 'full', 'pose_id': ids, 'x_eval': pose[:, 0], 'y_eval': pose[:, 1], 'yaw_eval_rad': pose[:, 2],
                      'e_r': q['range_m'] - pred[:, 0], 'e_s': q['s_fp'] - pred[:, 1], 's_fp': q['s_fp'], 'range_m': q['range_m']})
    for f in FEATURES:
        d[f] = q[f]
    d['fp_tap'] = q['tap']
    tb = [taps(np.asarray(H[k:k + 128, :, :, 0])) for k in range(0, len(H), 128)]
    for k in tb[0]:
        d[k] = np.concatenate([x[k] for x in tb])
    return d


def power_diag(train_full, test):
    """power_oof_experiment.fit_models: POWER_BIN_JOINT -> POWER_DIAG (cross-covariance set to 0)."""
    held = test.route.iloc[0]
    dist = cKDTree(test[['x_eval', 'y_eval']].to_numpy()).query(train_full[['x_eval', 'y_eval']].to_numpy())[0]
    tr = train_full[(train_full.route != held) & (dist > 1e-4)].copy(); w = B.site_weights(np, pd, tr)
    mp, cp, ip = B.fit_model(np, tr, test, w, 'POWER_BIN_JOINT', GROUPS)
    return mp, cp[:, 0, 0], cp[:, 1, 1], len(tr)


def exds(train_ft, test):
    """mu_recursive.hgb(EXIST + DS, 'e_r') on Full rows of the other routes."""
    held = test.route.iloc[0]
    tr = train_ft[(train_ft.channel == 'full') & (train_ft.route != held)]
    m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(tr[EXIST + DS], tr['e_r'])
    return m.predict(test[EXIST + DS]), len(tr)
