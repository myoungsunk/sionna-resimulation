"""Bounded nonlinear mean profiles with a fixed tangent covariance.

These are diagnostics on noiseless design observations, not sampled posterior
intervals or an exact nonlinear generative likelihood. Cost minima are upper
bounds from local multistart optimization; no global optimality claim.
"""
from pathlib import Path
import json,sys,datetime,hashlib
import numpy as np
from scipy.optimize import least_squares
from i1_model import forward,build_whitener,whiten
from i1_structural_observability import HERE,datasets,write

def run(out):
    spec=json.loads((out/'FROZEN_SPEC.json').read_text());data=datasets(spec)
    target=out/'PROFILE_LIKELIHOOD.json'
    if target.exists():raise FileExistsError(target)
    scale=np.array(spec['scales']);low,high=np.array(spec['profile_bounds_scaled']);all_results=[]
    for case in spec['profile_cases']:
        name,arm,aid=case.split(':');inp=data[name];anchor=np.array(spec['anchors'][aid]);use=arm!='A_DR'
        theta=inp['theta'];ops,values,J=build_whitener(theta,inp,anchor,spec,use)
        n,m=values.shape;W=whiten(np.eye(n*m).reshape(n,m,n*m),ops)
        for pose in spec['pose_cases']:
            def residual(u):
                v,_=forward(theta+scale*u,inp,anchor,use)
                r=W@(v-values).ravel()
                if pose=='S1':r=np.r_[r,u[:3]*scale[:3]/np.array(spec['pose_prior_std'])]
                return r
            def jacobian(u):
                _,_,J=forward(theta+scale*u,inp,anchor,use,True)
                mat=(W@J.reshape(n*m,6))*scale
                if pose=='S1':mat=np.vstack([mat,np.diag(scale/np.r_[spec['pose_prior_std'],[1,1,1]])[:3]])
                return mat
            results=[]
            for fixed in [None,3,5]:
                for grid in ([0.] if fixed is None else spec['profile_scaled_grid']):
                    free=[j for j in range(6) if j!=fixed]
                    def expand(z):
                        u=np.zeros(6);u[free]=z
                        if fixed is not None:u[fixed]=grid
                        return u
                    candidates=[]
                    for start in range(spec['profile_starts']):
                        z=np.zeros(6) if start==0 else np.array([.1,-.15,.2,.7,-.4,.6])*(1 if start==1 else -1)
                        solution=least_squares(lambda v:residual(expand(v)),z[free],jac=lambda v:jacobian(expand(v))[:,free],bounds=(low[free],high[free]),max_nfev=spec['profile_max_nfev'],ftol=1e-10,xtol=1e-10,gtol=1e-10)
                        candidates.append(dict(start=start,success=bool(solution.success),status=int(solution.status),evaluations=solution.nfev,twice_nll=float(2*solution.cost),scaled_parameters=expand(solution.x).tolist(),optimality=float(solution.optimality)))
                    successful=[c for c in candidates if c['success']]
                    best=min(successful or candidates,key=lambda c:c['twice_nll'])
                    results.append(dict(fixed_parameter='none' if fixed is None else ['x','y','psi','bg','SFg','eps'][fixed],fixed_scaled_value=grid,best=best,all_starts=candidates,status='CONVERGED_LOCAL' if successful else 'INCONCLUSIVE_OPTIMIZATION'))
            all_results.append(dict(case=case,pose_case=pose,profiles=results))
            print(case,pose,'profiles complete',flush=True)
    write(target,dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope=spec['profile_likelihood'],confidence_intervals='NOT_COMPUTED',global_optimality='NOT_ESTABLISHED',parameter_bounds=spec['profile_bounds_scaled'],results=all_results,I2='NOT_RUN',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),command=sys.argv))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
