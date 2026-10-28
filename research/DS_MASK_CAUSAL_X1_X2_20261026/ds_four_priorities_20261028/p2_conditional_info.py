#!/usr/bin/env python3
"""P2 mathematical 5-state/3-channel information diagnostic using real held-route P3 residuals.
This NEVER claims to be a recursive 5-state performance test.
"""
import argparse,json
from pathlib import Path
import numpy as np,pandas as pd
p=argparse.ArgumentParser();p.add_argument('--p3-scores',required=True);p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
df=pd.read_csv(a.p3_scores);piv=df.pivot(index="case",columns="model",values="residual_rms")
assert set(['BASE','BASE_PLUS_DELTA'])<=set(piv.columns)
res=pd.DataFrame({'case':piv.index,'rms_base':piv.BASE,'rms_plus_delta':piv.BASE_PLUS_DELTA}).reset_index(drop=True)
res['mse_ratio']=(res.rms_plus_delta/res.rms_base)**2
res['gain_proxy_nats_per_packet']=np.log(res.rms_base/res.rms_plus_delta)
res['incremental_gain']=1-res.mse_ratio
if {'NO_D0','NO_D0_PLUS_DELTA'} <= set(piv.columns):
 res['rms_no_d0']=piv.NO_D0.to_numpy()
 res['rms_plus_delta_no_d0']=piv.NO_D0_PLUS_DELTA.to_numpy()
 res['incremental_gain_no_d0']=1-(res.rms_plus_delta_no_d0/res.rms_no_d0)**2
# Demonstrate exact linear-algebra identity: nuisance-state Schur information.
# For whitened linear model and an independent q observation with precision p>0,
# conditional information for psi increases relative to nuisance unmeasured q.
def schur(A):
 return A[0,0]-A[0,1]**2/A[1,1]
R=np.array([[.04,.012],[.012,.02]]) # purely illustrative covariance, not RF-estimated
H=np.array([[1.,2.],[.08,1.]])       # psi and latent delta
I=H.T@np.linalg.solve(R,H);J=H[0:1].T@H[0:1]/R[0,0]
assert np.all(np.linalg.eigvalsh(R)>0)
assert abs(schur(I)-schur(I.T))<1e-10
# Comparing to s-only with a weak prior for q; avoid singular Schur if no q measurement.
prior=np.diag([0.,1/.5])
gain=schur(I+prior)-schur(J+prior)
assert gain>=-1e-10
res.to_csv(out/'P2_CONDITIONAL_PREDICTION_INFO.csv',index=False,float_format='%.16g')
status={'status':'REAL_HELD_ROUTE_PREDICTIVE_INFORMATION_AND_SYNTHETIC_SCHUR_QA_ONLY',
 'n_cases':len(res),'n_predictive_information_gain_positive':int((res.incremental_gain>0).sum()),
 'median_mse_improvement_fraction':float(res.incremental_gain.median()),
 'median_log_error_gain_nats':float(res.gain_proxy_nats_per_packet.median()),
 'n_gain_positive_no_d0':int((res.incremental_gain_no_d0>0).sum()) if 'incremental_gain_no_d0' in res else None,
 'median_gain_fraction_no_d0':float(res.incremental_gain_no_d0.median()) if 'incremental_gain_no_d0' in res else None,
 'synthetic_schur_information_gain':float(gain),
 'state':'[x,y,psi,b_g,q_delta]',
 'measurement':'[range,s_fp,delta_s]',
 'warning':'Synthetic Fisher uses artificial H/R; real data quantity measures held-route conditional prediction, not state observability. 5-state EKF NOT executed.'}
(out/'P2_INFORMATION_STATUS.json').write_text(json.dumps(status,indent=2),encoding='utf8')
print(json.dumps(status,indent=2))
