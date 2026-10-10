from pathlib import Path
import json,hashlib,re
import numpy as np,pandas as pd
root=Path(__file__).parent;remote=root/'retrieved';out=remote/'OUTPUT'
manifest=json.loads((remote/'OUTPUT_MANIFEST.json').read_text())
hash_bad=[p for p,v in manifest.items() if not (remote/p).is_file() or hashlib.sha256((remote/p).read_bytes()).hexdigest()!=v['sha256']]
assert not hash_bad,hash_bad
csvs=['A0_ARMS.csv','ARMS_controls.csv','ARMS_q1.csv']
df=pd.concat([pd.read_csv(out/x) for x in csvs],ignore_index=True)
keys=['case','mount_deg','arm','drift','seed']
arms=['A0_real_real','M0_Rmatched_Rmatched','W0_white_white','S1_bias','S2_ar0','S3_ar1','S4_iid','S5_iid0','S6_realdem','S7_block','S8_real']
expected={('R2A',0.,a,d,s) for a in arms for d in range(3) for s in range(50)}
actual=set(df[keys].itertuples(index=False,name=None));assert actual==expected and not df.duplicated(keys).any()
assert df.error.fillna('').eq('').all() and np.isfinite(df[['nees_mean','heading_rmse_deg','pos_rmse_m','nees_cov95','heading_cov95']]).all().all()
traces=list((out/'TRACES').glob('*.npz'));assert len(traces)==66
maxdiff={};min_eig=float('inf');max_asym=0.;logs=0
for p in traces:
 mat=re.match(r'R2A_m0_(.+)_s(\d+)_d(\d+)\.npz',p.name);arm,seed,drift=mat.group(1),int(mat.group(2)),int(mat.group(3))
 row=df[(df.arm==arm)&(df.seed==seed)&(df.drift==drift)].iloc[0]
 with np.load(p) as z:
  assert not bool(z['failed'])
  e=z['est'][:,:3]-z['truth'];e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
  P=z['cov6'];mask=z['t']>=30.;assert np.array_equal(mask,z['keep'])
  assert np.isfinite(P).all() and np.isfinite(e).all();max_asym=max(max_asym,float(np.abs(P-P.transpose(0,2,1)).max()))
  min_eig=min(min_eig,float(np.linalg.eigvalsh((P+P.transpose(0,2,1))*.5).min()))
  cov=P[mask,:3,:3];nees=np.einsum('ni,ni->n',e[mask],np.linalg.solve(cov,e[mask][...,None])[...,0])
  vals=dict(nees_mean=nees.mean(),heading_rmse_deg=np.sqrt(np.mean(np.degrees(e[mask,2])**2)),pos_rmse_m=np.sqrt(np.mean(np.sum(e[mask,:2]**2,axis=1))),nees_cov95=np.mean(nees<=7.814727903251179),heading_cov95=np.mean(np.abs(e[mask,2])<=1.96*np.sqrt(cov[:,2,2])))
  for kind in ['s','r']:
   lg=z[kind+'_log'];k=lg[:,0].astype(int);m=mask[k];acc=lg[:,2].astype(bool)
   assert np.allclose(lg[:,1],lg[:,3]**2/lg[:,4],rtol=1e-12,atol=1e-12)
   vals['nis_'+kind+'_eval_pre']=lg[m,1].mean();vals['nis_'+kind+'_eval_acc']=lg[m&acc,1].mean();vals[kind+'_reject_frac_eval']=np.mean(~acc[m]);logs+=len(lg)
  for k,v in vals.items():
   diff=abs(float(v)-float(row[k]));maxdiff[k]=max(maxdiff.get(k,0),diff)
   assert np.isclose(v,row[k],rtol=1e-9,atol=1e-9),(p.name,k,v,row[k])
assert min_eig>=0.,min_eig
result=dict(transferred_files_verified=len(manifest),rows=len(df),expected_rows=1650,duplicates=0,missing_keys=0,failed=0,trace_files=len(traces),trace_logs=logs,min_eigenvalue_cov6=min_eig,max_cov6_asymmetry=max_asym,independent_trace_metric_max_abs_diff=maxdiff,trace_scope='seeds0,1 only; no covariance-wide claim for untraced seeds')
(root/'VERIFICATION.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
