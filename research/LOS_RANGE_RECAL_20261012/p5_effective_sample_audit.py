"""R2-1: quantify how much of the P5 run-to-run variation is explained by the 12 fixed RF series (case) vs the 128 seeds.
Variance decomposition (one-way ANOVA on case x drift cells) for the paired E_COND-B_OLD and BEST_PLUS_R_IAT-B_OLD position-RMSE differences,
design effect and effective n for the pooled mean. Reads the R1 P5 runs table only. usage: p5_effective_sample_audit.py R1_DIR OUT_JSON"""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
R1=Path(sys.argv[1]);d=pd.read_csv(R1/'P5/P5_EKF_PAIRED_RUNS.csv')
d=d.rename(columns={'case':'cs'});d['cell']=d.cs+'|d'+d.drift.astype(str)
def icc(x,cell):
    g=pd.DataFrame(dict(x=x.to_numpy(),c=cell.to_numpy()));k=g.c.nunique();n=len(g)/k;gm=g.groupby('c').x.mean();msb=n*((gm-g.x.mean())**2).sum()/(k-1);msw=((g.x-g.c.map(gm))**2).sum()/(len(g)-k)
    r=(msb-msw)/(msb+(n-1)*msw);deff=1+(n-1)*max(r,0);return float(r),float(deff),float(len(g)/deff),float(msb),float(msw)
out={'n_cells':int(d.cell.nunique()),'seeds_per_cell':int(d.groupby('cell').seed.nunique().iloc[0]),'rf_series_independent':12,'measurement_noise_draws_per_seed':0}
piv=d.pivot_table(index=['cell','seed'],columns='arm',values='pos_rmse_m').reset_index()
armcol={a:a for a in piv.columns}
for name,a,b in (('E_COND-B_OLD','E_COND','B_OLD'),('BEST_PLUS_R_IAT-B_OLD','BEST_PLUS_R_IAT','B_OLD'),('B_OLD-A','B_OLD','A'),('E_COND-A','E_COND','A')):
    if a in piv and b in piv:
        x=piv[a]-piv[b];r,de,ne,msb,msw=icc(x,piv.cell);out[name]=dict(mean=float(x.mean()),icc_by_cell=r,design_effect=de,n_effective_runs=ne,n_runs=int(len(x)),between_cell_ms=msb,within_cell_ms=msw)
for a in ('A','B_OLD','E_COND'):
    if a in piv:r,de,ne,_,_=icc(piv[a],piv.cell);out['level_'+a]=dict(icc_by_cell=r,design_effect=de,n_effective_runs=ne)
# cell-level paired differences = what the 12 RF series (x3 drifts) actually support
cell=piv.groupby('cell')[[c for c in ('A','B_OLD','E_COND','BEST_PLUS_R_IAT') if c in piv]].mean()
out['cells_E_better_than_B']=int(((cell.E_COND-cell.B_OLD)<0).sum()) if 'E_COND' in cell else None;out['cells_total']=int(len(cell))
out['cells_IAT_better_than_B']=int(((cell.BEST_PLUS_R_IAT-cell.B_OLD)<0).sum()) if 'BEST_PLUS_R_IAT' in cell else None
out['cells_B_worse_than_A']=int(((cell.B_OLD-cell.A)>0).sum()) if 'A' in cell else None
Path(sys.argv[2]).write_text(json.dumps(out,indent=1));print(json.dumps(out,indent=1))
