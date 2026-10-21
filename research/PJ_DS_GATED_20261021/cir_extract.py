#!/usr/bin/env python3
"""Extract CIR (both RX ports, Full and LoS) around first path for selected packets. Same processing as features.py."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(os.environ['PJ_SOURCE_ROOT']); ART = Path(os.environ['PJ_ART']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
SEL = [('R2_aA_m0', 1088, 'A_bias_large_ds_large'), ('R4_aA_m0', 737, 'B_bias_large_ds_small'), ('R5_aA_m0', 381, 'C_R5A_heading_drift'), ('R2_aA_m45', 85, 'REF_clean')]
MAN = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
obs = pd.read_csv(next(ART.rglob('OBSERVATION_FEATURES_LABELS.csv.gz')))
q = obs[(obs.fp_tap > 0)]; dt_m = float(np.median(q.range_m / q.fp_tap)); dt_ns = dt_m / 0.299792458


def cir(Hrow):
    H = np.asarray(Hrow, np.complex128)[None]; nf = H.shape[1]; nt = 4 * nf
    w = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    c = np.fft.ifft(H * w[None, :, None], n=nt, axis=1) * nf
    amp = np.abs(c[0]); branch = int(amp.max(axis=0).argmax()); strong = amp[:, branch]; peak = strong.max()
    fp = int(np.argmax(strong >= .3 * peak)); return c[0], fp, branch, peak


rows, meta = [], []
for case, pid, tag in SEL:
    c = next(x for x in MAN['cases'] if x['id'] == case)
    ids = pd.DataFrame(json.loads((ROOT / c['samples_path']).read_text())).pose_id.to_numpy(int); i = int(np.where(ids == pid)[0][0])
    res = {}
    for ch, key in [('full', 'full_path'), ('los', 'los_path')]:
        H = np.load(ROOT / c[key], mmap_mode='r', allow_pickle=False); res[ch] = cir(H[i, :, :, 0])
    fp_los = res['los'][1]
    for ch, (cc, fp, br, pk) in res.items():
        for tap in range(max(0, fp_los - 40), min(len(cc), fp_los + 160)):
            p = np.abs(cc[tap]) ** 2
            rows.append({'tag': tag, 'case': case, 'pose_id': pid, 'channel': ch, 'tap': tap, 'rel_tap_to_los_fp': tap - fp_los, 'delay_ns_rel': (tap - fp_los) * dt_ns,
                         'amp_p45': float(np.abs(cc[tap, 0])), 'amp_m45': float(np.abs(cc[tap, 1])), 's_tap': float((p[0] - p[1]) / (p[0] + p[1])) if p.sum() > 0 else np.nan})
        meta.append({'tag': tag, 'case': case, 'pose_id': pid, 'channel': ch, 'fp_tap': fp, 'fp_rel_to_los': fp - fp_los, 'strong_port': br, 'peak_amp': float(pk),
                     's_at_fp': float((np.abs(cc[fp, 0]) ** 2 - np.abs(cc[fp, 1]) ** 2) / (np.abs(cc[fp, 0]) ** 2 + np.abs(cc[fp, 1]) ** 2))})
pd.DataFrame(rows).to_csv(OUT / 'CIR_SELECTED.csv', index=False)
(OUT / 'CIR_META.json').write_text(json.dumps({'dt_ns_per_tap': dt_ns, 'dt_m_per_tap': dt_m, 'packets': meta}, indent=2))
print('CIR_DONE', dt_ns, flush=True)
