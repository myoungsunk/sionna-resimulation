#!/usr/bin/env python3
"""Collect R2 failure decomposition for R2 and controls R4, R5."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();src=Path(a.input);dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
def cat(tag):
    fs=sorted(src.rglob(f'*_R2DIAG_{tag}.csv'));assert len(fs)==3,(tag,fs);return pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
S=cat('STRATA');R=cat('RECURSIVE')
h1=[json.loads(f.read_text()) for f in sorted(src.rglob('*_R2DIAG_H1.json'))];assert len(h1)==3
S.to_csv(dst/'R2DIAG_STRATA.csv',index=False);R.to_csv(dst/'R2DIAG_RECURSIVE.csv',index=False)
(dst/'R2DIAG_H1.json').write_text(json.dumps(h1,indent=2))
for f in sorted(src.rglob('*_R2DIAG_PACKETS.csv.gz')):(dst/f.name).write_bytes(f.read_bytes())
pd.set_option('display.width',260);pd.set_option('display.max_columns',30);pd.set_option('display.max_rows',300)
print('H1 / overall\n'+pd.DataFrame(h1).T.to_string())
cols=['held','stratum','frac','mean_delta_true','mean_dhat_pwide','mean_r_pwide','rms_r_base','rms_r_pwide','wb_contrib_base_deg','wb_contrib_pwide_deg']
for t in ['all','case','fp_shift','delta_true','domain_score','anchor_distance','abs_g']:
    print(f'\n== {t}\n'+S[S.stratum_type==t][cols].round(4).to_string(index=False))
rr=R.groupby(['held','arm','stratum_type','stratum'])[['n','mean_eps','wb_contrib_deg']].agg({'n':'sum','mean_eps':'median','wb_contrib_deg':'median'}).reset_index()
print('\n== recursive (t>=30, accepted; median over case x bias)\n'+rr.round(4).to_string(index=False))
print('R2DIAG_ALL_PASS',flush=True)
