#!/usr/bin/env python3
"""Post-hoc R5-B seed isolation: cross initial-state seeds and sensor/control seeds.
No model, Q, R, or means are changed. BASE mask is regenerated for each hybrid.
Factorial seeds [0,3,8,9] were chosen after inspecting the original failures;
this is a mechanism diagnostic, never an independent robustness claim.
"""
from __future__ import annotations
import argparse,hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;SRC=HERE.parent/'mbvar_control_correction_20261029'
SEEDS=[0,3,8,9]
def dump(p,d):Path(p).write_text(json.dumps(d,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--control-seed',type=int,choices=SEEDS);ap.add_argument('--out',required=True);ap.add_argument('--aggregate',action='store_true');a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if a.aggregate:
        ff=sorted(out.glob('SEED_GRID_CONTROL_*.csv'));d=pd.concat([pd.read_csv(f) for f in ff],ignore_index=True)
        assert len(ff)==4 and len(d)==48 and not d.duplicated(['control_seed','initial_seed','arm']).any()
        d.to_csv(out/'R5B_SEED_FACTORIAL.csv',index=False)
        tables=[]
        for arm,g in d.groupby('arm'):
            tables+=['## '+arm,g.pivot(index='control_seed',columns='initial_seed',values='head_rmse').to_markdown()]
        (out/'R5B_SEED_FACTORIAL.md').write_text('# Post-hoc R5-B seed factorial\n\nRows: sensor/control seed. Columns: initial-state seed. Heading RMSE [deg].\nNo model parameter was changed. BASE mask regenerated per cell.\n\n'+'\n\n'.join(tables))
        return
    sys.path.insert(0,str(SRC));import ctl_core as K
    case='R5_aB_m0';m=K.model();Dall={s:K.load(case,s) for s in SEEDS};dc=Dall[a.control_seed]
    old=pd.read_csv(SRC/'results/run_40820579727'/f'A_SCORES_{case}.csv');rows=[];t0=time.time()
    for initial_seed in SEEDS:
        D=dict(dc);D['x0']=Dall[initial_seed]['x0'].copy()
        D['acc']=K.PB.gated_mask(D['z'],D['mu']['BB'],D['R0'],D['ds'],D['gy'],D['dt'],D['x0'],D['P0'],D['spec'],m)&D['fin']
        for arm,bg,Rf in [('BB_ORIG','BB',K.R_orig),('MB_ORIG','MB',K.R_orig),('MB_VAR','MB',K.R_var)]:
            X,P,L=K.run(D,bg,Rf);s=K.scores(D,X,P);par=None
            if initial_seed==a.control_seed:
                ref=old[(old.seed==initial_seed)&(old.arm==arm)].iloc[0]
                par=max(abs(s['head_rmse']-ref.head_rmse),abs(s['xy_rmse_cm']-ref.xy_rmse_cm));assert par<1e-5
            rows.append(dict(case=case,control_seed=a.control_seed,initial_seed=initial_seed,arm=arm,n_base_accepted=int(D['acc'].sum()),initial_px_error_m=D['x0'][0]-D['gt'][0,0],initial_py_error_m=D['x0'][1]-D['gt'][0,1],initial_heading_error_deg=float(np.rad2deg(K.wrap(D['x0'][2]-D['gt'][0,2]))),original_diagonal_parity=par,**s))
        pd.DataFrame(rows).to_csv(out/f'SEED_GRID_CONTROL_{a.control_seed}.csv',index=False,float_format='%.12g')
        print('FACTORIAL',a.control_seed,initial_seed,round(time.time()-t0,1),flush=True)
    dump(out/f'MANIFEST_SEED_{a.control_seed}.json',dict(source_ref='422b6c0',git_sha=os.getenv('GITHUB_SHA'),run_id=os.getenv('GITHUB_RUN_ID'),utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),command=sys.argv,config=dict(case=case,control_seed=a.control_seed,initial_seeds=SEEDS,bias='B0',gate='BASE regenerated per hybrid',posthoc=True),input_lock=(Path(os.environ['REFLECT_ROOT'])/'out/INPUT_LOCK.sha256').read_text(),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.csv')}))
if __name__=='__main__':main()
