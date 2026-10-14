"""D2: read-only diagnosis of two immutable solver inputs, cloud only."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, os, traceback, platform
import math
import numpy as np
import mpmath as mp
from scipy.optimize import least_squares
from core import SyntheticRF, map_update, gaussian_update, wrap
from validate import sha, write

HERE=Path(__file__).resolve().parent


def analyze(path):
    s=json.loads(path.read_text())
    mu,P,z,R=(np.asarray(s[k]) for k in ('prior_x','prior_P','z','R'))
    n=len(mu); model=SyntheticRF(); Lp=np.linalg.cholesky(P); Lr=np.linalg.cholesky(R)
    y0=np.linalg.solve(Lp,np.asarray(s['prior_delta']))
    def residual(y):
        h,_=model(mu+Lp@y)
        return np.r_[y,np.linalg.solve(Lr,z-h)]
    def jac(y):
        _,H=model(mu+Lp@y)
        return np.vstack([np.eye(n),-np.linalg.solve(Lr,H@Lp)])
    def ev(y):
        f=residual(y); A=jac(y)
        return .5*float(f@f),A.T@f,A.T@A
    mp.mp.dps=80
    mm=mp.matrix([mp.mpf(float(t)) for t in mu])
    ll=mp.matrix([[mp.mpf(float(t)) for t in row] for row in Lp])
    rr=mp.matrix([[mp.mpf(float(t)) for t in row] for row in Lr])
    zz=mp.matrix([mp.mpf(float(t)) for t in z])
    def mcost(yy):
        yy=mp.matrix(yy); x=mm+ll*yy; dx=x[0]+2; dy=x[1]-3; q=dx*dx+dy*dy
        h=mp.matrix([mp.sqrt(q+mp.mpf(float(1.3))**2),mp.mpf(float(.8))*mp.sin(x[2])+mp.mpf(float(.15))*dy/mp.sqrt(q)])
        v=mp.lu_solve(rr,zz-h)
        return (mp.fdot(yy,yy)+mp.fdot(v,v))/2
    def mv(y): return [mp.mpf(float(v)) for v in y]
    def partial(y,i):
        def f(t):
            yy=list(y); yy[i]=t; return mcost(yy)
        return mp.diff(f,y[i])
    funcs=tuple((lambda *yy,i=i:partial(yy,i)) for i in range(n))
    root=mp.findroot(funcs,tuple(mv(y0)),tol=mp.mpf('1e-60'),maxsteps=30)
    Hess=np.array([[float(mp.diff(lambda t:partial([t if k==j else root[k] for k in range(n)],i),root[j])) for j in range(n)] for i in range(n)])
    c,g,info=ev(y0); step=np.linalg.solve(info,-g); cc,gg,_=ev(y0+step); _,gm,_=ev(y0+.5*step)
    area=float(math.fsum(float(a)*float(b) for a,b in zip((g+4*gm+gg)/6.,step)))
    trap=float(math.fsum(float(a)*float(b) for a,b in zip((g+gg)/2.,step)))
    change=info@step
    curvature_ratio=float(np.linalg.norm(gg-g-change,np.inf)/max(np.linalg.norm(change,np.inf),1e-30))
    records=[]; yy=y0.copy()
    for i in range(8):
        a,b,C=ev(yy); d=np.linalg.solve(C,-b); yn=yy+d; an,bn,_=ev(yn)
        records.append({'step':i,'cost':a,'gradient_inf':float(np.max(np.abs(b))),'next_gradient_inf':float(np.max(np.abs(bn))),
            'double_cost_change':an-a,'mp_cost_change':mp.nstr(mcost(mv(yn))-mcost(mv(yy)),45)})
        yy=yn
    r1=map_update(mu,P,z,model,R,max_iter=80,gradient_tol=1e-8)
    def rm(x):
        h,H=model(x);return h[:1],H[:1]
    xx,_,_=gaussian_update(mu,P,z[:1],rm,R[:1,:1]); d=xx-mu;d[2]=wrap(d[2]); yr=np.linalg.solve(Lp,d)
    refs=[]
    for method,jtype in [('trf','analytic'),('trf','3-point'),('dogbox','analytic'),('lm','analytic')]:
        sol=least_squares(residual,yr,jac=jac if jtype=='analytic' else jtype,method=method,
                          ftol=1e-13,xtol=1e-13,gtol=1e-13,max_nfev=500)
        sc,sg,_=ev(sol.x)
        refs.append({'method':method,'jacobian':jtype,'success':bool(sol.success),'status':int(sol.status),
                     'nfev':sol.nfev,'analytic_gradient_inf':float(np.max(np.abs(sg))),'meets_original_gradient':bool(np.max(np.abs(sg))<=1e-8),
                     'cost':sc,'state_distance_from_mp':float(np.max(np.abs(Lp@(sol.x-np.array([float(t) for t in root]))))),
                     'mp_cost_gap':mp.nstr(mcost(mv(sol.x))-mcost(list(root)),45),'message':sol.message})
    return {'snapshot':path.name,'sha256':sha(path),'cell':s['cell'],'recorded_status':s['recorded_status'],
      'replay_R1':{'status':r1.status,'gradient_inf':r1.gradient_inf,'iterations':r1.iterations,'history':r1.history},
      'saved_GN_step':{'before_gradient_inf':float(np.max(np.abs(g))),'next_gradient_inf':float(np.max(np.abs(gg))),
          'double_cost_delta':cc-c,'mp_cost_delta':mp.nstr(mcost(mv(y0+step))-mcost(mv(y0)),45),
          'gradient_integral_delta':area,'trapezoid_delta':trap,'curvature_ratio':curvature_ratio,'R1_curvature_guard':.05,
          'step_norm_inf':float(np.max(np.abs(step)))},
      'mp_hessian_eigenvalues':np.linalg.eigvalsh(Hess).tolist(),
      'mp_stationary_y':[mp.nstr(t,45) for t in root],'plain_GN_diagnostic_only':records,'independent_scipy':refs}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);a=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('cloud diagnosis only')
    from pre_run_audit import require_audit_receipt
    require_audit_receipt(a.audit)
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'stage':'D2','started_utc':datetime.now(timezone.utc).isoformat(),'git_sha':os.environ['GITHUB_SHA'],
            'run_id':os.environ['GITHUB_RUN_ID'],'python':platform.python_version(),'status':'STARTED',
            'P2':'NOT_RUN','P3_P6':'NOT_RUN','scientific_PASS':False,'source_sha256':{p.name:sha(p) for p in HERE.glob('*.py')}}
    write(out/'START.json',result);rc=1
    try:
        result['cases']=[analyze(HERE/f) for f in ('FAILURE_SNAPSHOT.json','RESUME_FAILURE_SNAPSHOT.json')]
        result['status']='DIAGNOSIS_EXECUTED';rc=0
    except Exception:
        result['status']='FAIL_CLOSED';result['traceback']=traceback.format_exc()
    result['exit_code']=rc;result['ended_utc']=datetime.now(timezone.utc).isoformat()
    write(out/'D2_RESULT.json',result)
    print('D2_RESULT '+json.dumps(result,allow_nan=False),flush=True)
    return rc

if __name__=='__main__':raise SystemExit(main())
