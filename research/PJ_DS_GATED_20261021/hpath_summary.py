#!/usr/bin/env python3
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
for g, nm in [('*_HP_ATTR.csv', 'HP_ATTR.csv'), ('*_HP_PAIR.csv', 'HP_PAIR.csv'), ('*_HP_SCORES.csv', 'HP_SCORES.csv'), ('*_HP_GAIN.csv', 'HP_GAIN.csv'), ('*_HP_QA.csv', 'HP_QA.csv')]:
    cat(g).to_csv(OUT / nm, index=False)
for g, nm in [('*_HP_PACKETS.csv.gz', 'HP_PACKETS.csv.gz'), ('*_HP_SERIES.csv.gz', 'HP_SERIES.csv.gz')]:
    cat(g).to_csv(OUT / nm, index=False, compression='gzip')
PK = pd.read_csv(OUT / 'HP_PACKETS.csv.gz'); QA = pd.read_csv(OUT / 'HP_QA.csv'); S = pd.read_csv(OUT / 'HP_SCORES.csv')
dmod = (PK['sMGT_+0'] - PK['sL_+0']).abs()
qa = {'closure_max': float(QA.closure.max()), 'gt_yaw_qa_max': float(QA.gt_yaw_qa_rad.max()), 'gt_xy_qa_max': float(QA.gt_xy_qa_m.max()),
      'model_vs_los_s0_p50': float(dmod.median()), 'model_vs_los_s0_p99': float(dmod.quantile(.99)), 'fp_model_eq_los_frac': float((PK.fpM_GT == PK.fp_los).mean()), 'n_packets': len(PK)}
(OUT / 'HP_QA.json').write_text(json.dumps(qa, indent=2)); print('::notice title=HP::' + json.dumps(qa)); print('HP_SUMMARY_DONE')
