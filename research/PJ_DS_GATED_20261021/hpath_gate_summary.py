#!/usr/bin/env python3
import os
from pathlib import Path
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
cat('*_HG_SCORES.csv').to_csv(OUT / 'HG_SCORES.csv', index=False); cat('*_HG_CF.csv').to_csv(OUT / 'HG_CF.csv', index=False)
cat('*_HG_SERIES.csv.gz').to_csv(OUT / 'HG_SERIES.csv.gz', index=False, compression='gzip'); print('HG_SUMMARY_DONE')
