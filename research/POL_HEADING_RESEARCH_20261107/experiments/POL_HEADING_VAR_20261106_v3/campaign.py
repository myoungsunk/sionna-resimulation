import run_heading as m
import numpy as np,json,time,sys
from datetime import datetime,timezone

def main():
 out=m.BASE/'outputs';out.mkdir(exist_ok=False);rows=[];parity=[]
 for lv in ['B0','L0','L1','L2']:
  for ch in ['full','los']:
   d=m.e.data(ch);ctrl,x0=m.e.build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],lv);saved=np.load(m.e.OLD/f'results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED'
   X,P,status=m.e.run_ekf(ctrl,d['z_s'],x0,True);dx=X-saved['estimate'][:,j];dx[:,2]=m.e.wrap(dx[:,2]);err=float(max(abs(dx).max(),abs(P-saved['covariance'][:,j]).max()));assert err<1e-7 and np.array_equal(status,saved['status'][:,j]);parity.append(dict(channel=ch,level=lv,max_error=err));m.dump('PARITY.json',parity)
   for arm,step,offset in [('S4',None,0),('v3',.25,0),('refined',.125,0),('shifted',.25,.125)]+([('fine',.0625,0)] if ch=='full' and lv=='B0' else []):
    start=time.perf_counter();extra={}
    if arm!='S4':X,P,extra=m.run(ctrl,d['z_s'],x0,True,mask,np.deg2rad(np.arange(-180+offset,180,step)))
    assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
    np.savez_compressed(out/f'{ch}_{lv}_{arm}.npz',estimate=X,covariance=P,t_s=d['t_s'],mask=mask,**extra)
    r=dict(channel=ch,level=lv,method=arm,grid_deg=step,offset_deg=offset,seconds=time.perf_counter()-start,**m.e.metrics(X,P,d['truth_for_offline_scoring_only'],d['t_s']));rows.append(r);m.dump('PROGRESS.json',rows);print(json.dumps(r),flush=True)
 assert len(rows)==33
 for filename in ['INPUT_HASHES.json','EXTRA_HASHES.json']:
  assert all(m.sha(p)==h for p,h in json.loads((m.BASE/filename).read_text(encoding='utf-8')).items())
 m.dump('RESULT.json',dict(status='EXECUTION_COMPLETED',rows=len(rows),time_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,inputs_unchanged=True,output_hashes={p.name:m.sha(p) for p in out.glob('*.npz')}))
if __name__=='__main__':main()
