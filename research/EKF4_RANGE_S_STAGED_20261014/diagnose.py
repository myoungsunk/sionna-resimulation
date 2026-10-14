"""Read-only D1 fixed failure experiment; run in GitHub Actions only."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
from datetime import datetime,timezone
import numpy as np
import mpmath as mp
from scipy.optimize import least_squares
from core import SyntheticRF,map_update
from validate import sha,write

HERE=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    s=json.loads((HERE/'FAILURE_SNAPSHOT.json').read_text())
    mu=np.asarray(s['prior_x']);P=np.asarray(s['prior_P']);z=np.asarray(s['z']);R=np.asarray(s['R'])
    model=SyntheticRF();Lp=np.linalg.cholesky(P);Lr=np.linalg.cholesky(R)
    y0=np.linalg.solve(Lp,np.asarray(s['prior_delta']))
    def ev(y):
        h,H=model(mu+Lp@y);v=np.linalg.solve(Lr,z-h);B=np.linalg.solve(Lr,H@Lp)
        return .5*float(y@y+v@v),y-B.T@v,np.eye(3)+B.T@B
    def fun(y):return np.r_[y,np.linalg.solve(Lr,z-model(mu+Lp@y)[0])]
    def jac(y):return np.vstack([np.eye(3),-np.linalg.solve(Lr,model(mu+Lp@y)[1]@Lp)])
    mp.mp.dps=80
    mm=mp.matrix([mp.mpf(float(v)) for v in mu]);ml=mp.matrix([[mp.mpf(float(v)) for v in row] for row in Lp])
    mz=mp.matrix([mp.mpf(float(v)) for v in z]);mr=mp.matrix([[mp.mpf(float(v)) for v in row] for row in Lr])
    def mc(y):
        y=mp.matrix(y);x=mm+ml*y
        dx=x[0]+2;dy=x[1]-3;q=dx*dx+dy*dy
        # Independent algebra: sin(atan2(dy,dx)) = dy/sqrt(q).
        h=mp.matrix([mp.sqrt(q+mp.mpf('1.3')**2),mp.mpf('.8')*mp.sin(x[2])+mp.mpf('.15')*dy/mp.sqrt(q)])
        v=mp.lu_solve(mr,mz-h)
        return (mp.fdot(y,y)+mp.fdot(v,v))/2
    def mv(y):return [mp.mpf(float(v)) for v in y]
    def partial(y,j):
        base=list(y)
        def f(t):
            changed=base.copy();changed[j]=t;return mc(changed)
        return mp.diff(f,base[j])
    gradient_functions=tuple((lambda *yy,j=j:partial(yy,j)) for j in range(3))
    root=mp.findroot(gradient_functions,tuple(mv(y0)),tol=mp.mpf('1e-65'),maxsteps=30)
    Hmp=np.array([[float(mp.diff(lambda t:partial([t if k==j else root[k] for k in range(3)],i),root[j])) for j in range(3)] for i in range(3)])
    y=y0.copy();records=[]
    for i in range(9):
        c,g,A=ev(y);step=np.linalg.solve(A,-g);yn=y+step;cn,gn,_=ev(yn)
        high_delta=mc(mv(yn))-mc(mv(y))
        records.append({'iteration_from_saved':i,'y':y.tolist(),'cost_double':c,'gradient_inf':float(np.max(np.abs(g))),
                        'step_norm':float(np.linalg.norm(step)),'double_cost_change':cn-c,
                        'high_precision_cost_change':mp.nstr(high_delta,50),
                        'next_gradient_inf':float(np.max(np.abs(gn))),
                        'cost_gap_to_mp_stationary':mp.nstr(mc(mv(y))-mc(list(root)),50)})
        y=yn
    replay=map_update(mu,P,z,model,R,max_iter=80,gradient_tol=1e-8)
    references=[]
    for method in ['analytic','3-point']:
        sol=least_squares(fun,np.zeros(3),jac=jac if method=='analytic' else method,
                          ftol=1e-13,xtol=1e-13,gtol=1e-13,max_nfev=500)
        c,g,_=ev(sol.x)
        references.append({'jacobian':method,'success':bool(sol.success),'cost':c,
                           'analytic_gradient_inf':float(np.max(np.abs(g))),
                           'y':sol.x.tolist(),'message':sol.message,
                           'mp_cost_gap':mp.nstr(mc(mv(sol.x))-mc(list(root)),50)})
    first=records[0]
    support=(mp.mpf(first['high_precision_cost_change'])<0 and first['next_gradient_inf']<1e-8
             and np.linalg.eigvalsh(Hmp)[0]>0)
    result={'stage':'D1','git_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
            'snapshot_sha256':sha(HERE/'FAILURE_SNAPSHOT.json'),'source_sha256':{p.name:sha(p) for p in HERE.glob('*.py')},
            'mpmath_dps':80,'original_failure':s['recorded_status'],
            'replay':{'status':replay.status,'gradient_inf':replay.gradient_inf,'cost':replay.cost,'history':replay.history},
            'plain_GN_fixed_input_records':records,'scipy_references':references,
            'mp_stationary_y':[mp.nstr(t,50) for t in root],
            'mp_hessian_eigenvalues':np.linalg.eigvalsh(Hmp).tolist(),
            'hypothesis_D1_N':'SUPPORTED_AT_FIXED_INPUT' if support else 'INCONCLUSIVE',
            'qualification':'Post-failure numerical diagnosis only. No solver patch, no P2 rerun, no physical/RF claim.',
            'P2':'BLOCKED','P3_P6':'NOT_RUN','scientific_PASS':False,'ended_utc':datetime.now(timezone.utc).isoformat()}
    write(out/'D1_RESULT.json',result)
    print('D1_RESULT '+json.dumps(result,allow_nan=False),flush=True)
    return 0 if support else 2


if __name__=='__main__':raise SystemExit(main())
