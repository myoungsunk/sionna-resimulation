"""Locate the first divergence; inspect same-prior Kriging neighbor selection."""
import argparse,importlib.util,json,sys
from pathlib import Path
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('runner')
parser.add_argument('--left',default='base246')
parser.add_argument('--right',default='base253_oldinput')
parser.add_argument('--output',default='RUNTIME_TRACE_COMPARISON.json')
args=parser.parse_args()
out=Path('/runout'); spec=importlib.util.spec_from_file_location('A',args.runner); A=importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
result={}
for route in A.ROUTES:
    for arm in ('H2','H2S',A.BASE):
        with np.load(out/args.left/f'{route}_{arm}.npz') as old,np.load(out/args.right/f'{route}_{arm}.npz') as new:
            detail={}
            for k in ('t','pose_id','x','P','prior','Pprior','nu','Reff','mask','distance','c1','c0','a'):
                if k not in old.files or k not in new.files: continue
                a,b=old[k],new[k]
                if a.dtype.kind=='b': detail[k]=dict(different=int(np.count_nonzero(a!=b)));continue
                delta=np.abs(a-b).reshape(len(a),-1).max(axis=1)
                ix=np.flatnonzero(delta>1e-12)
                detail[k]=dict(max_abs=float(delta.max()),first_over_1e_minus12=int(ix[0]) if len(ix) else None)
            result[f'{route}/{arm}']=detail
(out/args.output).write_text(json.dumps(result,indent=2))
for k,d in result.items():print(k,d['x'],d['nu'],flush=True)
