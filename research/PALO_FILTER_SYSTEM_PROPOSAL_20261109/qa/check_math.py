"""Algebra-only checks for proposal formulas; NOT a PALO performance experiment."""
from pathlib import Path
import json
import numpy as np
rng=np.random.default_rng(20261109)
checks={'schmidt_Pbb_max_diff':0.,'schmidt_cross_max_diff':0.,'schmidt_min_eigenvalue':float('inf'),
        'projection_nuisance_max':0.,'projection_noise_I_max':0.,'projection_information_gain_max_eigen':0.,
        'mixture_extra_cov_min_eigen':float('inf')}
for _ in range(500):
    A=rng.normal(size=(4,4));P=A@A.T+.1*np.eye(4)
    H=rng.normal(size=(1,4));H[0,3]=0
    R=.0081
    K=P@H.T/float((H@P@H.T)[0,0]+R);K[3,0]=0
    J=np.eye(4)-K@H
    C=J@P@J.T+R*K@K.T
    checks['schmidt_Pbb_max_diff']=max(checks['schmidt_Pbb_max_diff'],abs(C[3,3]-P[3,3]))
    cross=P[:3,3]-(K[:3]@(H@P[:,3,None])).ravel()
    checks['schmidt_cross_max_diff']=max(checks['schmidt_cross_max_diff'],np.max(np.abs(cross-C[:3,3])))
    checks['schmidt_min_eigenvalue']=min(checks['schmidt_min_eigenvalue'],np.linalg.eigvalsh(C).min())
    n=10;A=rng.normal(size=(n,n));Rwin=A@A.T+.2*np.eye(n);L=np.linalg.cholesky(Rwin)
    B=np.ones((n,1));W=np.linalg.solve(L,np.eye(n));Bw=W@B
    Q,_=np.linalg.qr(Bw,mode='complete');U=Q[:,1:];T=U.T@W
    checks['projection_nuisance_max']=max(checks['projection_nuisance_max'],np.max(np.abs(T@B)))
    checks['projection_noise_I_max']=max(checks['projection_noise_I_max'],np.max(np.abs(T@Rwin@T.T-np.eye(n-1))))
    Hwin=rng.normal(size=(n,4))
    Jfull=(W@Hwin).T@(W@Hwin);Jnew=(T@Hwin).T@(T@Hwin)
    checks['projection_information_gain_max_eigen']=max(checks['projection_information_gain_max_eigen'],np.linalg.eigvalsh(Jnew-Jfull).max())
    w=rng.dirichlet(np.ones(2));mu=rng.normal(size=(2,4));bar=w@mu
    between=sum(w[i]*np.outer(mu[i]-bar,mu[i]-bar) for i in range(2))
    checks['mixture_extra_cov_min_eigen']=min(checks['mixture_extra_cov_min_eigen'],np.linalg.eigvalsh(between).min())
assert checks['schmidt_Pbb_max_diff']<1e-12
assert checks['schmidt_cross_max_diff']<1e-12
assert checks['schmidt_min_eigenvalue']>0
assert checks['projection_nuisance_max']<1e-12
assert checks['projection_noise_I_max']<1e-12
assert checks['projection_information_gain_max_eigen']<1e-10
assert checks['mixture_extra_cov_min_eigen']>-1e-12
result={'status':'ALGEBRA_PASS_NOT_SCIENCE_VALIDATION','random_seed':20261109,'trials_per_formula_family':500,
        'families':3,'new_PALO_runs':0,'checks':{k:float(v) for k,v in checks.items()}}
p=Path(__file__).with_name('MATH_QA.json');p.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
