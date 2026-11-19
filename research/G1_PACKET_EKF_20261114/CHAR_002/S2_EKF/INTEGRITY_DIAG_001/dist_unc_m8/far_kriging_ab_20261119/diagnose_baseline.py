"""Baseline-only diagnostic. Never runs the candidate or changes frozen assets."""
import argparse
import importlib.util
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

P=argparse.ArgumentParser()
P.add_argument('--runner',required=True)
P.add_argument('--out',required=True)
P.add_argument('--seed',type=int,default=30)
P.add_argument('--condition',default='B0')
P.add_argument('--input-root')
P.add_argument('--stable-kriging',action='store_true')
args=P.parse_args()
out=Path(args.out); out.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('far_runner',args.runner)
A=importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
if args.stable_kriging:
    from kriging_stable import make_predictor
    A.KO.krige_s=make_predictor(A.KO)
if args.input_root:
    def packet(cond,seed,route):
        with np.load(Path(args.input_root)/cond/f'seed{seed}'/f'{route}_online.npz') as z:
            return {k:z[k] for k in A.C.KEYS}
    A.C.packet=packet
B,table,published=A.load_frozen()
env=A.C.env(); ft,_,_=A.C.scorers()
from metrics_s2 import _summarize
rows={}; checks=[]; start=time.time()
for route in A.ROUTES:
    p=A.C.packet(args.condition,args.seed,route)
    pk=A.baseline_packet(p,*(B[f'{route}/{k}'] for k in ('mu_r','mu_s','Rrr','Rss')))
    truth=A.C.TRUTH[route]['truth']
    traces={
        'H2':A.C.R7.replay(p,env,'H2',**A.C.m7_kwargs('H2',route,args.condition,'own')),
        'H2S':A.C.R7.replay(pk,env,'H2',condition=args.condition,rref_policy='own',sigma_b=A.ZERO,sigma_rad=0.),
        A.BASE:A.M.replay_m8(pk,env,A.BASE,mu_s_fn=A.KO.make_fn(B[f'{route}/mu_s'],near_limit=6.),
                          table=table,sigma_b=A.ZERO,condition=args.condition,**A.M.ARM_MODES['F2'])}
    rows[route]={}
    for arm,tr in traces.items():
        rows[route][arm]=np.asarray(ft(tr,truth))
        np.savez_compressed(out/f'{route}_{arm}.npz',**tr)
    print('REPLAYED',route,flush=True)
groups={r:rows[r] for r in rows}
groups['pooled']={a:np.concatenate([rows[r][a] for r in rows]) for a in rows[A.ROUTES[0]]}
for route,arms in groups.items():
    for arm,data in arms.items():
        score=_summarize(data)
        for field in A.PAIR_PARAMS:
            old=published[args.condition,args.seed,arm,route][field]
            gap=abs(float(score[field])-old)
            checks.append(dict(route=route,arm=arm,metric=field,expected=old,actual=float(score[field]),abs_gap=gap,passed=bool(np.isfinite(gap) and gap<=1e-8)))
result=dict(status='PASS' if all(r['passed'] for r in checks) else 'FAIL',numpy=np.__version__,python=sys.version,platform=platform.platform(),
            condition=args.condition,seed=args.seed,stable_kriging=args.stable_kriging,elapsed_s=time.time()-start,checks=checks)
(out/'BASELINE.json').write_text(json.dumps(result,indent=2))
print(result['status'],'max_abs',max(r['abs_gap'] for r in checks),flush=True)
for row in checks:
    if not row['passed']: print(row,flush=True)
sys.exit(0 if result['status']=='PASS' else 1)
