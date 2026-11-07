import json,hashlib
from pathlib import Path
import numpy as np
B=Path(__file__).resolve().parent; O=B/'results_v2'
s=json.loads((O/'SUMMARY.json').read_text(encoding='utf-8'))
checked=0
for row in s['metrics']:
 p=row['policy']; a=np.load(O/f"{row['channel']}_{row['level']}_{p}.npz")
 accept=a['accepted']; truth=a['truth']; prior=a['prior_X']; cand=a['candidate_X']
 h=lambda x:abs((x[:,2]-truth[:,2]+np.pi)%(2*np.pi)-np.pi)
 hg=h(cand)+1e-12<h(prior)
 xg=np.linalg.norm(cand[:,:2]-truth[:,:2],axis=1)+1e-12<np.linalg.norm(prior[:,:2]-truth[:,:2],axis=1)
 gate=a['nis']<=6.6348966010212145
 expected={'dr':np.zeros(len(accept),bool),'s4':gate,'oracle_heading':hg,'oracle_xy':xg,'oracle_both':hg&xg,'oracle_heading_gate':hg&gate,'oracle_both_gate':hg&xg&gate}[p]
 assert np.array_equal(accept,expected)
 assert np.array_equal(a['X'],np.where(accept[:,None],cand,prior))
 assert np.array_equal(a['P'],np.where(accept[:,None,None],a['candidate_P'],a['prior_P']))
 mask=a['t']>=40
 rmse=np.sqrt(np.mean(h(a['X'])[mask]**2))*180/np.pi
 assert abs(rmse-row['heading_rmse_deg'])<1e-12
 checked+=1
assert checked==56
receipt={'status':'SELF_CHECK_PASS_NOT_INDEPENDENT_AUDIT','arms':checked,'checks':['decision truth table','chosen full state and covariance','heading RMSE independent aggregation','all 779 evaluation samples per arm'],'claim':'greedy hindsight diagnostic, not global optimum'}
(O/'SELF_CHECK.json').write_text(json.dumps(receipt,indent=2)+'\n')
s['status']='EXECUTION_COMPLETE_SELF_CHECK_PASS'
(O/'SUMMARY.json').write_text(json.dumps(s,indent=2)+'\n')
print(json.dumps(receipt))
for r in s['metrics']:
 if r['channel']=='full':print(r['level'],r['policy'],round(r['heading_rmse_deg'],4),round(r['xy_rmse_m'],4),round(r['heading_nees'],3),round(r['xy_nees'],3))
