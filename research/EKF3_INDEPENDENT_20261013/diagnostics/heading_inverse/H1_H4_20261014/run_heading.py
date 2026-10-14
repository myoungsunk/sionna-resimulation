import os,sys,json,math,csv,gzip,argparse,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from inverse_core import curve,inverse,wrap,propagated_cov
ROOT=Path(__file__).resolve().parent
REPO=Path('D:/SLAM_bot/artifacts/EKF3_P0_VERIFY_20261013_01a132b7/checkout')
CODE=REPO/'research/EKF3_INDEPENDENT_20261013/diagnostics/robust_fusion'
INPUT=Path('D:/SLAM_bot/artifacts/EKF3_ROBUST_FUSION_20261013/M0')
TRACE=Path('D:/SLAM_bot/artifacts/EKF3_LOSS_FAMILY_20261013')
for p in [CODE/'followup',CODE,CODE.parent]:sys.path.insert(0,str(p))
from rf_components import check_inputs,original_lut,case_motion,initial_state,DiagnosticFilter,RS,RR
from ekf3 import EKF3
from qclean_uwb.drivesim.hs_lut import s_model
STAGES=[('NOISE','noise_pair',1),('L0','gyro_bias',0),('L1','gyro_bias',1),('L2','gyro_bias',2)]
MODELS=['M0','RF_HUBER_ONLY','RF_CAUCHY']
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False),encoding='utf-8')
def native(lut,c,x):return s_model(lut,c['anchor'],c['robot_z_m'],x[...,0],x[...,1],x[...,2],c['mount_deg'],with_jac=True)
def packP(g):
 p=np.zeros((len(g),3,3));p[:,0,0]=g.Pxx;p[:,1,1]=g.Pyy;p[:,2,2]=g.Ppsi
 for i,j,n in [(0,1,'Pxy'),(0,2,'Pxpsi'),(1,2,'Pypsi')]:p[:,i,j]=p[:,j,i]=g[n]
 return p
class Writer:
 def __init__(self,p):self.f=gzip.open(p,'wt',newline='',encoding='utf-8');self.w=None;self.n=0
 def row(self,v):
  if self.w is None:self.w=csv.DictWriter(self.f,fieldnames=v);self.w.writeheader()
  self.w.writerow({k:json.dumps(x) if isinstance(x,list) else x for k,x in v.items()});self.n+=1
 def close(self):self.f.close()
def input_gate():
 m=json.loads((INPUT/'MANIFEST.json').read_text())
 for n,h in m['sha256'].items():assert sha(INPUT/n)==h,n
 return check_inputs()
def sources():
 paths=[ROOT/'run_heading.py',ROOT/'inverse_core.py']+[ROOT/'PLAN.md',REPO/'research/EKF3_INDEPENDENT_20261013/ekf3.py',CODE.parent/'d6_d9_common.py',CODE/'followup/rf_components.py',CODE/'ablation/robust_pose_ekf.py',CODE/'followup/loss_family.py']
 return {str(p):sha(p) for p in paths}
def test():
 # Triangular periodic forward model with roots, extrema, no roots and flat intervals.
 x=np.array([-np.pi,-np.pi/2,0,np.pi/2,np.pi]);y=np.array([0,1,0,-1,0.])
 a=inverse(x,y,.5,.1,prior=0,truth=0);assert a['root_count']==2
 assert inverse(x,y,1,.1)['root_count']==1
 assert inverse(x,y,2,.1)['no_exact_solution']
 assert inverse(x,y,0,.1)['root_count']==2
 assert inverse(x,np.zeros(5),0,.1)['flat_solution']
 assert abs(inverse(x,np.zeros(5),0,.1)['band_width_deg']-360)<1e-9
 assert inverse(x,np.zeros(5),2,.1)['band_components']==0
 a=inverse(x,y,.5,.1,prior=0,truth=0);b=inverse(x,y,.5,.1,prior=0,truth=2)
 assert a['selected_heading_deg']==b['selected_heading_deg']
 rng=np.random.default_rng(71)
 for _ in range(100):
  yy=np.r_[rng.uniform(-1,1,4),0.];yy[-1]=yy[0];z=rng.uniform(-1,1)
  xx=np.sort(np.r_[x,(x[:-1]+x[1:])/2]);yv=np.interp(xx,x,yy)
  a=inverse(x,yy,z,.1);b=inverse(xx,yv,z,.1)
  assert a['root_count']==b['root_count'] and np.allclose(a['roots_deg'],b['roots_deg'],atol=1e-8,rtol=0)
  assert abs(a['band_width_deg']-b['band_width_deg'])<1e-8 and a['band_components']==b['band_components']
 for _ in range(30):
  X=rng.normal(size=3);A=rng.normal(size=(3,3));P=A@A.T*.01+np.eye(3)*.001;ds,da=rng.normal(size=2)*.01;dt=.2
  f=EKF3(X,P);f.predict(ds,da,dt)
  b=propagated_cov(P[None],X[2:3],np.array([ds]),np.array([da]),np.array([dt]))[0]
  assert np.max(abs(b-f.P))<1e-12
 p0=input_gate();lut=original_lut(p0);mx=0.
 for c in p0['cases']:
  f=np.load(INPUT/(c['id']+'_los.npz'))
  for q in np.linspace(0,len(f['truth'])-1,10,dtype=int):
   truth=f['truth'][q];xx,yy,_,_=curve(lut,c,truth[:2]);angles=np.r_[xx,(xx[:-1]+xx[1:])/2,xx[:-1]+.371*np.diff(xx)]
   states=np.column_stack([np.full(len(angles),truth[0]),np.full(len(angles),truth[1]),angles]);a=native(lut,c,states)[0]
   mx=max(mx,float(np.max(abs(a-np.interp(angles,xx,yy)))))
   assert mx<1e-10
 dump(ROOT/'TEST_RECEIPT.json',dict(status='PASS',synthetic_cases=138,native_case_positions=70,native_max_abs_s=mx,source_sha256=sources(),scientific_PASS=False))
 print('TEST PASS native max',mx,flush=True)
def run(smoke):
 begin=time.time();out=ROOT/('SMOKE' if smoke else 'FULL');out.mkdir(exist_ok=False)
 testr=json.loads((ROOT/'TEST_RECEIPT.json').read_text());assert testr['status']=='PASS'
 for p,h in testr['source_sha256'].items():assert sha(p)==h,p
 source=sources();p0=input_gate();lut=original_lut(p0);cases=p0['cases'][:1] if smoke else p0['cases'];seeds=[0] if smoke else [0,1,2];stages=STAGES[:1] if smoke else STAGES
 caches={};curves={};motions={};drs={};writer=Writer(out/'H12_RF.csv.gz')
 sigma=math.sqrt(RS)
 for c in cases:
  fs={ch:np.load(INPUT/(c['id']+'_'+ch+'.npz')) for ch in ['los','full']};truth=fs['los']['truth'];ids=np.flatnonzero(fs['los']['t']>=30)
  for ch in fs:
   assert np.array_equal(fs[ch]['truth'],truth) and np.array_equal(fs[ch]['t'],fs['los']['t'])
   caches[c['id'],ch]={k:fs[ch][k] for k in fs[ch].files}
  for k in ids:
   xx,yy,clip,th=curve(lut,c,truth[k,:2]);curves[c['id'],int(k)]=(xx,yy,clip,th)
   for ch in ['los','full']:
    inv=inverse(xx,yy,float(fs[ch]['s'][k]),sigma,truth=truth[k,2]);pred,jac=native(lut,c,truth[k]);unique=inv['root_count']==1 and not inv['flat_solution']
    writer.row(dict(case=c['id'],sample_index=k,t_s=fs[ch]['t'][k],channel=ch,experiment='H1' if ch=='los' else 'H2',theta_clipped=clip,theta_geo_deg=th,
      s=fs[ch]['s'][k],s_residual=fs[ch]['s'][k]-pred,hpsi=jac[2],sigma_heading_known_xy_deg=np.degrees(sigma/abs(jac[2])) if abs(jac[2])>1e-14 else np.nan,
      unique_error_deg=float(np.degrees(wrap(np.radians(inv['roots_deg'][0])-truth[k,2]))) if unique else np.nan,**inv))
  print('H12',c['id'],len(ids)*2,flush=True)
 writer.close()
 wh3=Writer(out/'H3_DR.csv.gz')
 for stage,condition,level in stages:
  for c in cases:
   for seed in seeds:
    t,truth,pids,motion,oracle=case_motion(p0,c,seed,level,condition);motions[stage,c['id'],seed]=motion
    f=DiagnosticFilter(initial_state(truth[0],seed));dr=[]
    for k in range(len(t)):
     if k:f.predict(float(motion['ds_odom'][k]),float(motion['dtheta_gyro'][k]),float(motion['dt_s'][k]))
     dr.append(f.pose.copy())
    dr=np.array(dr);drs[stage,c['id'],seed]=dr
    for k in np.flatnonzero(t>=30):
     cache=caches[c['id'],'full'];assert np.array_equal(cache['truth'][k],truth[k]);xx,yy,clip,th=curve(lut,c,dr[k,:2]);z=float(cache['s'][k]);iv=inverse(xx,yy,z,sigma,prior=dr[k,2],truth=truth[k,2]);cx,cy,_,_=curves[c['id'],int(k)]
     ref=inverse(cx,cy,z,sigma,prior=dr[k,2],truth=truth[k,2]);los=inverse(cx,cy,float(caches[c['id'],'los']['s'][k]),sigma,prior=dr[k,2],truth=truth[k,2])
     pred,jac=native(lut,c,truth[k]);_,jd=native(lut,c,dr[k]);dp=dr[k,:2]-truth[k,:2];ds=z-pred;good=abs(jac[2])>1e-14
     a=ds/jac[2] if good else np.nan;b=-float(jac[:2]@dp)/jac[2] if good else np.nan
     wh3.row(dict(stage=stage,condition=condition,level=level,case=c['id'],seed=seed,sample_index=k,t_s=t[k],theta_clipped=clip,dr_heading_error_deg=float(np.degrees(wrap(dr[k,2]-truth[k,2]))),position_error_m=float(np.linalg.norm(dp)),
      H1_prior_error_deg=los['selected_error_deg'],H2_prior_error_deg=ref['selected_error_deg'],H2_root_count=ref['root_count'],H2_band_width_deg=ref['band_width_deg'],H2_band_truth=ref['band_truth'],
      hpsi_truth=jac[2],hpsi_dr=jd[2],hx_truth=jac[0],hy_truth=jac[1],hx_dr=jd[0],hy_dr=jd[1],delta_x=dp[0],delta_y=dp[1],delta_s=ds,
      rf_term_deg=np.degrees(a),position_term_deg=np.degrees(b),cross_deg2=2*np.degrees(a)*np.degrees(b),linear_error_deg=np.degrees(a+b),linear_remainder_deg=iv['selected_error_deg']-np.degrees(a+b),derivative_oracle_only=True,**iv))
    print('H3',stage,c['id'],seed,flush=True)
 wh3.close()
 # Read preserved traces; reconstruct priors using only previous posterior + frozen motion.
 wh4=Writer(out/'H4_EKF.csv.gz');checks=[];trace_hashes={}
 for stage,condition,level in stages:
  path=TRACE/stage/'RF_COMPONENT_TRACE.csv.gz';mh=json.loads((TRACE/stage/'MANIFEST.json').read_text())['sha256'][path.name];assert sha(path)==mh;trace_hashes[str(path)]=mh
  frames=[]
  for chunk in pd.read_csv(path,chunksize=50000,float_precision='round_trip'):
   mask=chunk.case.isin([c['id'] for c in cases])&chunk.seed.isin(seeds)&chunk.model.isin(MODELS)&chunk.arm.isin(['A','C'])
   frames.append(chunk[mask])
  allg=pd.concat(frames,ignore_index=True)
  for key,g in allg.groupby(['case','channel','range_model','seed','arm','model'],sort=False):
   cid,ch,rm,seed,arm,name=key;c=next(c for c in cases if c['id']==cid);g=g.sort_values('sample_index').reset_index(drop=True);old=g.iloc[:-1];g=g.iloc[1:].reset_index(drop=True)
   k=g.sample_index.to_numpy(int);assert np.all(k-old.sample_index.to_numpy(int)==1)
   truth=caches[cid,ch]['truth'][k];motion=motions[stage,cid,seed];pp=propagated_cov(packP(old),old.psi.to_numpy(),motion['ds_odom'][k],motion['dtheta_gyro'][k],motion['dt_s'][k])
   prior=np.column_stack([truth[:,0]+g.prior_error_x,truth[:,1]+g.prior_error_y,wrap(truth[:,2]+np.radians(g.prior_heading_error_deg))]);hs,jac=native(lut,c,prior)
   ds=motion['ds_odom'][k];da=motion['dtheta_gyro'][k];distance=ds*np.sinc(da/(2*np.pi));px=old.x.to_numpy()+distance*np.cos(old.psi.to_numpy()+da/2);py=old.y.to_numpy()+distance*np.sin(old.psi.to_numpy()+da/2)
   stateerr=max(float(np.max(abs(px-prior[:,0]))),float(np.max(abs(py-prior[:,1]))),float(np.max(abs(wrap(old.psi.to_numpy()+da-prior[:,2])))))
   diagerr=float(np.max(abs(np.diagonal(pp,axis1=1,axis2=2)-g[['prior_Pxx','prior_Pyy','prior_Ppsi']].to_numpy())))
   assert stateerr<=1e-8 and diagerr<=1e-8,(key,stateerr,diagerr)
   H=jac[:,None,:];rv=np.full((len(g),1),RS);z=caches[cid,ch]['s'][k,None];pred=hs[:,None]
   if arm=='C':
    delta=prior[:,:2]-np.asarray(c['anchor'][:2]);dist=np.sqrt(np.sum(delta**2,axis=1)+(c['robot_z_m']-c['anchor'][2])**2)
    jr=np.column_stack([delta/dist[:,None],np.zeros(len(g))]);H=np.stack([jac,jr],axis=1);rv=np.tile([RS,RR],(len(g),1));z=np.column_stack([z[:,0],caches[cid,ch][rm][k]]);pred=np.column_stack([hs,dist])
   assert np.isfinite(z).all(),'Missing observation requires explicit subblock analysis'
   R=np.array([np.diag(a) for a in rv]);S=H@pp@H.transpose(0,2,1)+R;innov=z-pred;nis=np.einsum('ni,ni->n',innov,np.linalg.solve(S,innov[...,None])[...,0]);niserr=float(np.max(abs(nis-g.NIS.to_numpy())))
   assert niserr<=1e-8,(key,niserr)
   applied=g.status.to_numpy()=='applied';gate=6.6348966010212145 if arm=='A' else 9.21034037197618;assert np.array_equal(applied,nis<=gate)
   w=np.ones(len(g)) if name=='M0' else g.huber_weight.fillna(1).to_numpy();eff=R/w[:,None,None]
   gain=np.linalg.solve(H@pp@H.transpose(0,2,1)+eff,H@pp).transpose(0,2,1);ident=np.eye(3)-gain@H;post=ident@pp@ident.transpose(0,2,1)+gain@eff@gain.transpose(0,2,1);post[~applied]=pp[~applied]
   perr=float(np.max(abs(post-packP(g))));assert perr<=1e-8,(key,perr)
   check=dict(stage=stage,case=cid,channel=ch,range_model=rm,seed=int(seed),arm=arm,model=name,n=len(g),state_max=stateerr,prior_cov_max=diagerr,NIS_max=niserr,posterior_cov_max=perr)
   checks.append(check)
   for i in range(len(g)):
    row=g.iloc[i];xx,yy,cl,th=curve(lut,c,prior[i,:2]);iv=inverse(xx,yy,float(z[i,0]),sigma,truth=truth[i,2]);known=np.degrees(sigma/abs(jac[i,2])) if abs(jac[i,2])>1e-14 else np.nan
    # Marginal scalar-s gain includes position/heading prior cross covariance.
    ps=pp[i]@jac[i];scalar_reduction=float(ps[2]**2/(jac[i]@ps+RS));conditional=np.maximum(0.,pp[i,2,2]-scalar_reduction)
    wh4.row(dict(stage=stage,case=cid,channel=ch,range_model=rm,seed=seed,arm=arm,model=name,sample_index=int(k[i]),t_s=row.t_s,theta_clipped=cl,
     root_count=iv['root_count'],flat_solution=iv['flat_solution'],no_exact_solution=iv['no_exact_solution'],band_width_deg=iv['band_width_deg'],band_components=iv['band_components'],band_truth=iv['band_truth'],
     hpsi=jac[i,2],sigma_known_xy_deg=known,prior_heading_std_deg=np.degrees(np.sqrt(pp[i,2,2])),post_heading_std_deg=np.degrees(np.sqrt(row.Ppsi)),
     scalar_s_nominal_post_std_deg=np.degrees(np.sqrt(conditional)),heading_cov_ratio=row.Ppsi/pp[i,2,2],xy_cov_ratio=(row.Pxx+row.Pyy)/(pp[i,0,0]+pp[i,1,1]),
     NIS=row.NIS,applied=bool(applied[i]),weight=float(w[i]) if applied[i] else np.nan,R_multiplier=float(1/w[i]) if applied[i] else np.nan,
     heading_error_deg=row.heading_error_deg,prior_heading_error_deg=row.prior_heading_error_deg,heading_squared_error_change=row.heading_squared_error_change,
     heading_NEES=row.heading_NEES,heading95=row.heading95,H=H[i].tolist(),S=S[i].tolist(),K=gain[i].tolist(),R_effective=eff[i].tolist(),P_prior=pp[i].tolist(),P_post=packP(g.iloc[i:i+1])[0].tolist()))
   print('H4',stage,*key,len(g),flush=True)
 wh4.close();pd.DataFrame(checks).to_csv(out/'H4_PARITY.csv',index=False)
 for p,h in source.items():assert sha(p)==h,p
 dump(out/'RECEIPT.json',dict(status='PASS',mode='SMOKE' if smoke else 'FULL',elapsed_s=time.time()-begin,utc=datetime.now(timezone.utc).isoformat(),H12_rows=writer.n,H3_rows=wh3.n,H4_rows=wh4.n,
  covariance_and_NIS_parity_tolerance=1e-8,source_sha256=source,trace_sha256=trace_hashes,input_manifest_sha256=sha(INPUT/'MANIFEST.json'),output_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()},scientific_PASS=False))
 print('COMPLETE',writer.n,wh3.n,wh4.n,flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['test','smoke','full']);a=ap.parse_args()
 if a.mode=='test':test()
 else:run(a.mode=='smoke')
