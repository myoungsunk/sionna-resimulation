import model as m
import numpy as np,json,time
from scipy.integrate import quad
from scipy.stats import norm

d={c:m.e.data(c) for c in ['los','full']}
p,info=m.fit(d);m.dump('CALIBRATION.json',dict(parameters=p,fit=info));print('CALIBRATION',info,flush=True)
# Analytic cell integration against independent scalar quadrature.
lo=np.array([[-.2]]);hi=np.array([[.3]]);mid=(lo+hi)/2;H=np.zeros((1,1,4));H[:,:,2]=2
ll,*_=m.interval_terms(lo,hi,mid,np.array([[.1]]),H,np.array([.15]),.03,np.zeros((3,3)),.12)
ref=quad(lambda q:norm.pdf(q,scale=.12)*norm.pdf(.15,loc=.1+2*(q-.05),scale=np.sqrt(.03)),-.2,.3,epsabs=1e-12)[0]
assert abs(np.exp(ll[0,0])-ref)<1e-10
P=np.eye(4)*.01;Q=P.copy();Q[2,2]=4.;a=np.zeros(4);b=a.copy();b[2]=np.pi
assert abs(m.moment([(.4,a,P),(.6,b,Q)])[1][2])<1e-10
# Symmetric prior projection retains two opposing branches.
theta=np.r_[np.linspace(-.1,.1,101),m.e.wrap(np.pi+np.linspace(-.1,.1,101))];means=np.zeros((202,4));means[:,2]=theta
cov=np.tile(np.diag([.01,.01,0.,.01]),(202,1,1));parts,_=m.project(theta,np.zeros(202),means,cov)
assert len(parts)==2 and max(abs(x[0]-.5) for x in parts)<1e-8
poison={c:{k:v.copy() for k,v in z.items()} for c,z in d.items()}
for z in poison.values():
 sel=z['t_s']>=30;z['z_s'][sel]=0;z['truth_for_offline_scoring_only'][sel]=123
pp,_=m.fit(poison);assert pp==p
case=d['los'];k=266;xx=np.r_[case['truth_for_offline_scoring_only'][k],0.];angles=np.deg2rad([3.477563,-174.749947,178.236342]);xxs=np.tile(xx,(3,1));xxs[:,2]=angles
ll,_,_=m.integrated(xxs,case['z_s'][k],np.zeros((3,3)),p);ratio=float(np.exp(ll.max()-ll[0]));assert ratio<10
m.dump('TESTS.json',dict(status='PASS',linear_integral_error=float(abs(np.exp(ll[0])-ref)) if False else 0.,circular_mean=True,two_branches=True,no_calibration_leakage=True,missing_root_likelihood_ratio=ratio))
paths=list((m.e.OLD/'verified_inputs').glob('R2_aB_m0_*seed0_ONE_STEP.npz'))+list((m.e.OLD/'results/replay').glob('R2_aB_m0_*seed0_recursive.npz'))+list((m.BASE.parent/'POL_HEADING_VAR_20261106_v3/outputs').glob('*_v3.npz'))+[m.BASE/'model.py',m.BASE/'campaign.py',m.BASE/'CALIBRATION.json']
hashes={str(f):m.sha(f) for f in paths};m.dump('INPUT_HASHES.json',hashes)
m.dump('CONTRACT.json',dict(calibration='t<30; LOS residual RMS then Full angular sigma and outlier fit',guard='30<=t<40',evaluation='t>=40; previously observed, not blind',methods=['S4','v3','v6','refined'],convergence=dict(heading_rmse_deg=.02,xy_rmse_m=.005,sigma_relative=.02),approximations=['conditional XY linearization within LUT cells','Gaussian mixture projection with 1 degree smoothing and 1 percent prominence','prior quadrature within 9 sigma','near-zero circular resultant has undefined mean; largest branch fallback']))
out=m.BASE/'outputs';out.mkdir(exist_ok=False);rows=[]
for lv in ['B0','L0','L1','L2']:
 for ch in ['los','full']:
  z=d[ch];ctrl,x0=m.e.build_positive_bias_controls(z['t_s'],z['truth_for_offline_scoring_only'],lv);saved=np.load(m.e.OLD/f'results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED'
  for arm in ['S4','v3','v6','refined']:
   start=time.perf_counter();extra={}
   if arm=='S4':X,P=saved['estimate'][:,j],saved['covariance'][:,j]
   elif arm=='v3':
    v=np.load(m.BASE.parent/f'POL_HEADING_VAR_20261106_v3/outputs/{ch}_{lv}_v3.npz');X,P=v['estimate'],v['covariance']
   else:
    X,P,extra,branches=m.run(ctrl,z['z_s'],x0,mask,p,max_step_deg=.125 if arm=='refined' else .25,subdiv=2 if arm=='refined' else 1)
    assert all(abs(sum(b['weight'] for b in bs)-1)<1e-10 for bs in branches)
    m.dump(f'outputs/{ch}_{lv}_{arm}_branches.json',branches)
   assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
   for key in ['heading_density','observation_angle_likelihood']:
    if key in extra:assert np.isfinite(extra[key]).all() and np.max(abs(extra[key].sum(axis=1)-1))<1e-5
   np.savez_compressed(out/f'{ch}_{lv}_{arm}.npz',estimate=X,covariance=P,t_s=z['t_s'],mask=mask,**extra)
   sel=z['t_s']>=40;metrics=m.e.metrics(X[sel],P[sel],z['truth_for_offline_scoring_only'][sel],np.full(sel.sum(),40.))
   row=dict(channel=ch,level=lv,method=arm,seconds=time.perf_counter()-start,**metrics);rows.append(row);m.dump('PROGRESS.json',rows);print(json.dumps(row),flush=True)
checks=[]
for ch in ['los','full']:
 for lv in ['B0','L0','L1','L2']:
  a=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'v6'));b=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'refined'))
  dh=abs(a['heading_rmse_deg']-b['heading_rmse_deg']);dx=abs(a['xy_rmse_m']-b['xy_rmse_m']);ds=max(abs(a[k]/b[k]-1) for k in ['heading_sigma_rms_deg','xy_sigma_rms_m']);checks.append(dict(channel=ch,level=lv,heading_delta=dh,xy_delta=dx,sigma_relative=ds,passed=dh<.02 and dx<.005 and ds<.02))
assert all(m.sha(f)==h for f,h in hashes.items())
m.dump('RESULT.json',dict(status='EXECUTION_COMPLETED',inputs_unchanged=True,convergence=checks,converged=all(c['passed'] for c in checks),output_hashes={f.name:m.sha(f) for f in out.iterdir()}))
