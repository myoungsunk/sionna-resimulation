import model as m
import numpy as np,json,time
p=json.loads((m.BASE/'CALIBRATION.json').read_text(encoding='utf-8'))['parameters'];out=m.BASE/'outputs';out.mkdir(exist_ok=False);rows=[];parity=[]
for lv in ['B0','L0','L1','L2']:
 for ch in ['los','full']:
  d=m.e.data(ch);ctrl,x0=m.e.build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],lv);saved=np.load(m.e.OLD/f'results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED'
  X,P,status=m.e.run_ekf(ctrl,d['z_s'],x0,True);dx=X-saved['estimate'][:,j];dx[:,2]=m.e.wrap(dx[:,2]);err=float(max(abs(dx).max(),abs(P-saved['covariance'][:,j]).max()));assert err<1e-7 and np.array_equal(status,saved['status'][:,j]);parity.append(dict(channel=ch,level=lv,error=err));m.dump('PARITY.json',parity)
  for arm in ['S4','v3','v5','precise']:
   extra={};start=time.perf_counter()
   if arm=='v3':
    old=np.load(m.BASE.parent/f'POL_HEADING_VAR_20261106_v3/outputs/{ch}_{lv}_v3.npz');X,P=old['estimate'],old['covariance']
   elif arm in ['v5','precise']:X,P,extra=m.run(ctrl,d['z_s'],x0,mask,p,tol=1e-10 if arm=='precise' else 1e-8,maxiter=400 if arm=='precise' else 200)
   assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
   np.savez_compressed(out/f'{ch}_{lv}_{arm}.npz',estimate=X,covariance=P,t_s=d['t_s'],mask=mask,**extra)
   row=dict(channel=ch,level=lv,method=arm,seconds=time.perf_counter()-start,**m.metrics(X,P,d['truth_for_offline_scoring_only'],d['t_s']));rows.append(row);m.dump('PROGRESS.json',rows);print(json.dumps(row),flush=True)
assert len(rows)==32 and all(m.sha(p)==h for p,h in json.loads((m.BASE/'INPUT_HASHES.json').read_text(encoding='utf-8')).items())
m.dump('RESULT.json',dict(status='EXECUTION_COMPLETED',rows=len(rows),inputs_unchanged=True,output_hashes={f.name:m.sha(f) for f in out.glob('*.npz')}))
