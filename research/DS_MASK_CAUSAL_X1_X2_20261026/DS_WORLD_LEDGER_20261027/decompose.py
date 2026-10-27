from common import *

def arrays(z,case):
 mask=z['t_s']>=30;x=z['x'][mask];truth=z['truth_scoring_only'][mask];a=np.asarray(case['anchor']);eraw=x[:,:,:2]-truth[:,None,:2]
 radial=truth[:,:2]-a[:2];d=np.linalg.norm(radial,axis=1);ur=radial/d[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]])
 er=np.einsum('nji,ni->nj',eraw,ur);et=np.einsum('nji,ni->nj',eraw,ut)
 b,e,r=geometry(truth,case);bh,eh,rh=geometry(x,case)
 ps=wrap(np.degrees(x[:,:,2]-truth[:,None,2]));be=wrap(np.degrees(bh-b[:,None]));ph=wrap(ps-be)
 check('beta_sign_exact',be,wrap(np.degrees(np.arctan2(et,d[:,None]+er))),1e-10)
 xy=np.sum(eraw**2,axis=2);gap=np.mean(xy,axis=0)-np.mean(er**2+et**2,axis=0);check('XY_identity_m2',gap,np.zeros_like(gap),1e-12)
 return dict(psi=ps,beta=be,phi=ph,er=er*100,et=et*100,epsilon=np.degrees(eh-e[:,None]),range=(rh-r[:,None])*100,xy2=xy*10000,beta_small_approx=np.degrees(et/d[:,None]),wrap_residual=ps-be-ph),x,truth,(b,e,r,bh,eh,rh)

def stats(v):
 v=v[np.isfinite(v)]
 return dict(bias=float(v.mean()),std=float(v.std()),rmse=float(np.sqrt(np.mean(v*v)))) if len(v) else dict(bias=np.nan,std=np.nan,rmse=np.nan)

def metric_rows(a,case,bias,names,alphas):
 rows=[]
 for j,name in enumerate(names):
  row=dict(case=case['id'],route=case['route'],bias=bias,arm=str(name),alpha=float(alphas[j]),n=len(a['psi']))
  for k in ['psi','beta','phi','er','et','epsilon','range']:
   row.update({k+'_'+key:value for key,value in stats(a[k][:,j]).items()})
  row['xy_rmse_cm']=float(np.sqrt(a['xy2'][:,j].mean()));row['wrap_count']=int((abs(a['wrap_residual'][:,j])>1e-10).sum());row['bias_identity_residual']=float(a['psi'][:,j].mean()-a['beta'][:,j].mean()-a['phi'][:,j].mean())
  if row['wrap_count']==0:assert abs(row['bias_identity_residual'])<=1e-12
  if 'psi_eq' in a:
   row.update({'eq_'+key:value for key,value in stats(a['psi_eq'][:,j]).items()});row['undefined_fraction']=float(np.isnan(a['psi_eq'][:,j]).mean());row['eq_interpretable']=row['undefined_fraction']<=.1
  rows.append(row)
 return rows