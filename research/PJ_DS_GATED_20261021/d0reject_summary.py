#!/usr/bin/env python3
import json, os
from pathlib import Path
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
pd.concat([pd.read_csv(p) for p in sorted(IN.rglob('*_REJ.csv.gz'))], ignore_index=True).to_csv(OUT / 'REJ.csv.gz', index=False, compression='gzip')
json.dump([json.loads(p.read_text()) for p in sorted(IN.rglob('*_REJ_META.json'))], open(OUT / 'REJ_META.json', 'w'), indent=2); print('REJ_SUMMARY_DONE')
