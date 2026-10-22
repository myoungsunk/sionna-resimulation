#!/usr/bin/env python3
import os
from pathlib import Path
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
pd.concat([pd.read_csv(p) for p in sorted(IN.rglob('*_D0V_SCORES.csv'))], ignore_index=True).to_csv(OUT / 'D0V_SCORES.csv', index=False); print('D0V_SUMMARY_DONE')
