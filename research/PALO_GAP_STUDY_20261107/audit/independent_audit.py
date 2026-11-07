import csv,hashlib,itertools,json,sys
from pathlib import Path
import numpy as np
from scipy.stats import rankdata
p=Path('D:/codex/PALO_GAP_STUDY_20261107_01')
q=Path('D:/codex/PALO_EXACT_ORACLE_20261107_01')
src=q/'inputs/experiments/POL_FGO_CORR_20261106_v1/frozen/repo'
sys.path.insert(0,str(src/'research/EKF4_RANGE_S_STAGED_20261014'))
from p3_rf_adapter4 import FrozenLut
H=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
J=lambda f:json.loads(f.read_bytes())
manifest=J(p/'OUTPUT_MANIFEST.json')
assert len(manifest)==668
for path,r in manifest.items():
 f=p/path
 assert f.stat().st_size==r['bytes'] and H(f)==r['sha256'],path
m=J(q/'INPUT_MANIFEST.json')
assert len(m['files'])==86
for r in m['files']:
 f=q/'inputs'/r['path'].split('research/POL_HEADING_RESEARCH_20261107/',1)[1]
 b=f.read_bytes()
 assert hashlib.sha256(b).hexdigest()==r['sha256'] and hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==r['git_blob']
prev_hashes=J(q/'OUTPUT_SHA256.json')
for f in ['source/palo_oracle_closedloop.py', 'audit/independent_check.py']:
 if f in prev_hashes: assert H(q/f)==prev_hashes[f]
prov=J(p/'results/EXECUTION_PROVENANCE.json')
assert H(q/'INPUT_MANIFEST.json')==prov['input_manifest_sha']
for f,h in prov['files'].items():assert H(Path(f))==h,f
print('binding',H(p/'OUTPUT_MANIFEST.json'),m['commit'],H(q/'OUTPUT_SHA256.json'),flush=True)
f=q/'inputs/inputs/original_run/verified_inputs'
with np.load(f/'R2_aB_m0_full_seed0_ONE_STEP.npz') as a, np.load(f/'R2_aB_m0_los_seed0_ONE_STEP.npz') as b:
 t,pose,truth,z=a['t_s'],a['pose_id'],a['truth_for_offline_scoring_only'],a['z_s']
 rf=np.abs(z-b['z_s'])
 for k in ('t_s','pose_id','truth_for_offline_scoring_only'): assert np.array_equal(a[k],b[k])
 assert a['detected'].all() and b['detected'].all()
assert len(t)==979 and (t>=40).sum()==779 and t[t<140][-1]==139.8 and (t>=140).sum()==279
levels=('B0','L0','L1','L2'); taus=(.02,.05,.10,.20)
r=J(p/'results/SUMMARY.json')['rows']
rows={(a['group'],a['level'],a['name']):a for a in r}
expected=set()
for lv in levels:
 for name in ('s4','dr','heading'):expected.add(('baseline',lv,name))
 for ta in taus:
  for g in (0,1):expected.add(('rf',lv,f'{ta:.2f}_gate{g}'))
  for seed in range(5):expected.add(('random',lv,f'{ta:.2f}_s{seed}'))
 for pat,kind,rate,seed in itertools.product(('iid','burst'),('fn','fp','both'),(.01,.05,.10,.20),range(5)):expected.add(('sensitivity',lv,f'{pat}_{kind}_{rate:.2f}_s{seed}'))
 for name in ('s4','dr','heading','learned',*(f'rf_{ta:.2f}' for ta in taus)):expected.add(('development',lv,name))
assert set(rows)==expected and len(r)==len(rows)==636
out=p/'results/trajectories'
assert set(out.glob('*.npz'))=={out/a['path'] for a in r}
controls={lv:dict(np.load(q/'inputs/experiments/POL_FGO_CORR_20261106_v1/outputs'/f'controls_full_{lv}.npz')) for lv in levels}
lut=FrozenLut(src)
case=next(x for x in J(src/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json')['cases'] if x['id']=='R2_aB_m0')
angle=lambda a:np.arctan2(np.sin(a),np.cos(a))
maxdiff={}
def close(key,x,y,tol):
 err=float(np.max(abs(np.asarray(x)-np.asarray(y))))
 assert np.isfinite(err) and err<=tol,(key,err,tol)
 maxdiff[key]=max(maxdiff.get(key,0),err)
def motion(x,P,c):
 dt=c['dt_s'][1:]; ds=c['ds_odom'][1:]; yaw=c['dtheta_gyro'][1:]-x[:,3]*dt
 sinc=np.sinc(yaw/(2*np.pi)); a=yaw/2
 deriv=-yaw/12+yaw**3/480-yaw**5/53760
 ii=np.abs(a)>.0005
 deriv[ii]=(a[ii]*np.cos(a[ii])-np.sin(a[ii]))/(2*a[ii]**2)
 psi=x[:,2]+a
 uv=np.column_stack((np.cos(psi),np.sin(psi)))
 perpendicular=uv[:,::-1]*[-1,1]
 dx=ds[:,None]*sinc[:,None]*uv
 dpsi=ds[:,None]*(deriv[:,None]*uv+.5*sinc[:,None]*perpendicular)
 A=np.tile(np.eye(4),(len(ds),1,1))
 A[:,:2,2]=dx[:,::-1]*[-1,1]; A[:,:2,3]=-dt[:,None]*dpsi; A[:,2,3]=-dt
 B=np.zeros((len(ds),4,2))
 B[:,:2,0]=sinc[:,None]*uv; B[:,:2,1]=dpsi; B[:,2,1]=1
 v=np.column_stack((2e-5*abs(ds),np.deg2rad(.015)**2*dt))
 predicted=x.copy()
 predicted[:,:2]+=dx;predicted[:,2]=angle(x[:,2]+yaw)
 return predicted,A@P@A.transpose(0,2,1)+(B*v[:,None,:])@B.transpose(0,2,1)
def measurement(xx):
 u,v=(xx[:,:2]-case['anchor'][:2]).T
 rho2=np.maximum(u*u+v*v,1e-12); rho=np.sqrt(rho2)
 h=case['anchor'][2]-case['robot_z_m']
 psi=np.degrees(xx[:,2])+case['mount_deg']
 idx=np.array([np.degrees(np.arctan2(rho,h))/lut.dt,(np.degrees(np.arctan2(-v,u))+180)/lut.dp,(np.degrees(np.arctan2(-v,-u))-psi+180)%360/lut.dp])
 idx[0]=np.clip(idx[0],0,lut.nt-1-1e-9)
 lo=np.floor(idx).astype(int); f=idx-lo
 pred=np.zeros(len(xx));grad=np.zeros((3,len(xx)))
 for bits in itertools.product((0,1),repeat=3):
  w=np.where(np.asarray(bits)[:,None],f,1-f)
  ijk=lo+np.asarray(bits)[:,None];ijk[1:]%=lut.np
  val=lut.s[tuple(ijk)].astype(float)
  pred+=val*np.prod(w,axis=0)
  for j in range(3):grad[j]+=(2*bits[j]-1)*val*np.prod(w[np.arange(3)!=j],axis=0)
 grad/=np.array([lut.dt,lut.dp,lut.dp])[:,None]
 theta=grad[0]*h/(rho2+h*h)/rho
 azi=(grad[1]-grad[2])/rho2
 H=np.column_stack((theta*u+azi*v,theta*v-azi*u,-grad[2],np.zeros(len(xx))))*180/np.pi
 return pred,H
dr={}
for lv in levels:
 with np.load(out/rows['baseline',lv,'dr']['path']) as a:
  prior=a['prior_X']
 pred,_=measurement(prior)
 v=z-pred
 hist=np.array([[np.mean(v[max(0,i-5):i]),np.std(v[max(0,i-5):i])] if i else [0,0] for i in range(len(t))])
 dr[lv]=(prior,hist)
def errors(X):
 dx=X[:,:3]-truth
 dx[:,2]=angle(dx[:,2])
 return dx,np.linalg.norm(dx[:,:2],axis=1)
def nees(e,P):
 return e[:,2]**2/P[:,2,2],(e[:,0]**2*P[:,1,1]-2*e[:,0]*e[:,1]*P[:,0,1]+e[:,1]**2*P[:,0,0])/(P[:,0,0]*P[:,1,1]-P[:,0,1]**2)
def stats(x,P):
 e,d=errors(x)
 hn,xn=nees(e,P)
 return e,d,hn,xn
def save_data(key):
 with np.load(out/rows[key]['path']) as a:return dict(a)
base={lv:save_data(('baseline',lv,'s4')) for lv in levels}
model=J(p/'results/FROZEN_DEVELOPMENT_MODEL.json')
assert model['feature']=='dr_innov_mean5' and model['direction']=='le'
train=[];features={}
report_events={}
nmin=1e6
rf_wins=0
metrics={}
for key,row in rows.items():
 g,lv,name=key
 a=save_data(key); c=controls[lv]
 assert all(np.array_equal(a[k],v) for k,v in [('t',t),('truth',truth),('pose_id',pose)])
 x,P,xm,Pm,xu,Pu,yes=[a[k] for k in ('X','P','prior_X','prior_P','candidate_X','candidate_P','accepted')]
 assert yes.dtype==np.bool_ and yes.shape==(979,)
 for cov in (P,Pm,Pu):
  assert cov.shape==(979,4,4) and np.isfinite(cov).all()
  close('symmetry',cov,cov.transpose(0,2,1),1e-13)
  eig=np.linalg.eigvalsh(cov).min()
  assert eig>0
  nmin=min(nmin,float(eig))
 assert np.array_equal(xm[0],np.r_[c['initial_pose'],0.])
 close('initial_P',Pm[0],np.diag(np.array([.1,.1,np.deg2rad(5),np.deg2rad(.1)])**2),1e-15)
 xp,Pp=motion(x[:-1],P[:-1],c)
 close('transition_X',xp,xm[1:],1e-12);close('transition_P',Pp,Pm[1:],1e-12)
 h,H=measurement(xm)
 ph=np.einsum('nij,nj->ni',Pm,H)
 var=np.einsum('ni,ni->n',H,ph)+.0081
 v=z-h
 nis=v**2/var
 pred=xm+ph*(v/var)[:,None];pred[:,2]=angle(pred[:,2])
 cov=Pm-np.einsum('ni,nj,n->nij',ph,ph,1/var)
 close('candidate_X',pred,xu,1e-11);close('candidate_P',cov,Pu,1e-11);close('NIS',nis,a['nis'],1e-10)
 assert np.array_equal(x[yes],xu[yes]) and np.array_equal(x[~yes],xm[~yes])
 assert np.array_equal(P[yes],Pu[yes]) and np.array_equal(P[~yes],Pm[~yes])
 ep,dp,hp,np_=stats(xm,Pm); ec,dc=errors(xu); e,d,hn,xn=stats(x,P)
 b=np.abs(ep[:,2])-np.abs(ec[:,2]); bxy=dp-dc
 close('benefit',b,a['benefit'],1e-12);close('xy_benefit',bxy,a['xy_benefit'],1e-12)
 gate=a['nis']<=6.6348966010212145
 good=a['benefit']>1e-12;bad=a['benefit']< -1e-12
 if g in ('baseline','development'):
  if name=='s4': expect=gate
  elif name=='dr':expect=np.zeros_like(yes)
  elif name=='heading':expect=gate&good
  elif name=='learned':expect=gate&(dr[lv][1][:,0]<=model['threshold'])
  else:expect=gate&(rf<=float(name.split('_')[1]))
  if g=='baseline':
   oldname='oracle_heading_gate' if name=='heading' else name
   with np.load(q/'results_v2'/f'full_{lv}_{oldname}.npz') as old:
    assert np.array_equal(yes,old['accepted'])
    close('baseline_X',x,old['X'],1e-7);close('baseline_P',P,old['P'],1e-8);close('baseline_NIS',a['nis'],old['nis'],1e-7)
  else:
   pre=t<140
   for field in ('X','P','prior_X','prior_P','accepted'):assert np.array_equal(a[field][pre],base[lv][field][pre])
   first=np.flatnonzero(~pre)[0]
   for field in ('prior_X','prior_P'):assert np.array_equal(a[field][first],base[lv][field][first])
   expect=np.where(pre,base[lv]['accepted'],expect)
 elif g=='rf':
  expect=(rf<=row['tau'])
  if row['gated']:expect &=gate
 elif g=='random':
  k=int((rf<=row['tau']).sum())
  assert k==row['target_count']
  expect=np.isin(np.arange(len(t)),np.random.default_rng(row['seed']).choice(len(t),k,replace=False))
 elif g=='sensitivity':
  u=np.random.default_rng(row['seed']).random((2,len(t)));p0=row['rate']
  if row['pattern']=='iid': masks=u<p0
  else:
   masks=u<p0
   for i in range(1,len(t)):
    masks[:,i]=np.where(masks[:,i-1],u[:,i]>=.2,u[:,i]<p0/(5*(1-p0)))
  ng=good if row['kind']=='fp' else good&~masks[0]
  nb=np.zeros_like(bad) if row['kind']=='fn' else bad&masks[1]
  expect=gate&(ng|nb)
 assert np.array_equal(yes,expect),key
 if 'features' in a:
  drx,hist=dr[lv]
  f2=np.column_stack((nis,abs(v),abs(H[:,2]),np.linalg.norm(H[:,:2],axis=1),Pm[:,0,0]+Pm[:,1,1],Pm[:,2,2],np.linalg.norm(Pm[:,:2,2],axis=1),abs(angle(xu[:,2]-xm[:,2])),hist,abs(angle(xm[:,2]-drx[:,2])),np.linalg.norm(xm[:,:2]-drx[:,:2],axis=1)))
  close('features',f2,a['features'],1e-10)
  if g=='baseline':
   features[lv,name]=(a['features'],a['benefit'])
   if name in ('s4','dr'):
    m=(t>=40)&(t<120)
    train.append((lv,name,a['features'][m],gate[m],a['benefit'][m],a['xy_benefit'][m]))
 m=t>=(140 if g=='development' else 40)
 m2=dict(n=m.sum(),heading_rmse_deg=np.linalg.norm(np.rad2deg(e[m,2]))/np.sqrt(m.sum()),xy_rmse_m=np.linalg.norm(d[m])/np.sqrt(m.sum()),heading_nees=hn[m].mean(),xy_nees=xn[m].mean(),heading_95_coverage=(hn[m]<=3.841458820694124).mean(),xy_95_coverage=(xn[m]<=5.991464547107979).mean(),applied=(yes&m).sum(),applied_all=yes.sum(),beneficial_opportunities=(gate&good&m).sum(),harmful_opportunities=(gate&bad&m).sum(),false_reject=(gate&good&~yes&m).sum(),false_accept=(gate&bad&yes&m).sum(),min_cov_eigenvalue=np.linalg.eigvalsh(P).min())
 for col,val in m2.items():close('metrics',val,row[col],1e-9)
 metrics[key]=m2
 last=np.maximum.accumulate(np.where(yes,np.arange(len(t)),-1))
 re=last-np.r_[-1,last[:-1]]>=6
 ix=np.flatnonzero(re&yes&m)
 report_events[key]=(len(ix),int(((P[:,2,2]<Pm[:,2,2])&(abs(e[:,2])>abs(ep[:,2])))[ix].sum()),int(((hp<=3.841458820694124)&(hn>3.841458820694124))[ix].sum()))
print('max',maxdiff,'min_eigenvalue',nmin,flush=True)
order={l:i for i,l in enumerate(levels)}
train.sort(key=lambda x:(order[x[0]],x[1]=='dr'))
fs,gate,bs,xy=[np.concatenate([r[i] for r in train]) for i in range(2,6)]
assert len(bs)==3200
best=(0.,'never','none',0.,0.,0)
for fi in [-1,*range(12)]:
 cuts=[0] if fi==-1 else np.unique(np.quantile(fs[:,fi],np.arange(.1,1,.1)))
 for cut in cuts:
  for direction in (('always',) if fi==-1 else ('le','gt')):
   ok=gate & (True if fi==-1 else (fs[:,fi]<=cut if direction=='le' else fs[:,fi]>cut))
   benefit,xb=bs[ok].sum(),xy[ok].sum()
   if xb>=0 and benefit>best[0]+1e-15:best=(benefit,fi,direction,cut,xb,ok.sum())
assert best[1]==8 and best[2]==model['direction'] and best[3]==model['threshold'] and best[5]==model['selected']
close('training_objective',best[0],model['objective'],1e-12); close('training_XY',best[4],model['xy_benefit'],1e-12)
featkeys=['nis','innovation_abs','Hpsi_abs','Hxy_norm','Pxy_trace','Ppsi','Pxypsi_norm','correction_abs','dr_innov_mean5','dr_innov_std5','dr_heading_diff','dr_xy_diff']
for a in J(p/'results/FEATURE_ASSOCIATIONS.json'):
 f,b=features[a['level'],a['prior']]
 m=t>=40
 fg=f[m,featkeys.index(a['feature'])]
 good=b[m]>1e-12
 wins=(fg[good,None]>fg[~good]).sum()+.5*(fg[good,None]==fg[~good]).sum()
 if good.any() and (~good).any():close('AUC',wins/(good.sum()*(~good).sum()),a['auc_benefit'],1e-12)
 else:assert a['auc_benefit'] is None
for group in ('baseline','rf','random','sensitivity','development'):
 print('event_totals',group,np.sum([v for k,v in report_events.items() if k[0]==group],axis=0).tolist())
print('RF.02g_events',np.sum([v for k,v in report_events.items() if k[0]=='rf' and k[2]=='0.02_gate1'],axis=0).tolist())
for lv in levels:
 for tau in taus:
  rfrow=metrics['rf',lv,f'{tau:.2f}_gate0']
  rw=[metrics['random',lv,f'{tau:.2f}_s{seed}']['heading_rmse_deg'] for seed in range(5)]
  assert rfrow['heading_rmse_deg']<np.median(rw)
  rf_wins+=sum(rfrow['heading_rmse_deg']<a for a in rw)
print('RF random wins',rf_wins)
print('stump',best)
for k in levels:
 print(k,*[round(metrics[x]['heading_rmse_deg'],8) for x in [('baseline',k,'s4'),('rf',k,'0.02_gate1'),('baseline',k,'heading'),('development',k,'s4'),('development',k,'learned'),('development',k,'heading')]])
print('PASS 636 trajectories 622644 frames',flush=True)

prior_manifest={k.replace(chr(92),'/'):v for k,v in prev_hashes.items()}
prior_metrics={(r['channel'],r['level'],r['policy']):r for r in J(q/'results_v2/SUMMARY.json')['metrics']}
for lv in levels:
 ref=f'results_v2/full_{lv}_oracle_heading.npz'
 gated=f'results_v2/full_{lv}_oracle_heading_gate.npz'
 assert hashlib.sha256((q/ref).read_bytes()).hexdigest()==hashlib.sha256((q/gated).read_bytes()).hexdigest()==prior_manifest[ref]==prior_manifest[gated]
 with np.load(q/ref,allow_pickle=False) as a:
  assert all(np.array_equal(a[k],v) for k,v in [('t',t),('truth',truth),('pose_id',pose)])
  keep=t>=40
  er,xy=errors(a['X']); h=np.sqrt(np.mean(np.degrees(er[keep,2])**2)); x=np.sqrt(np.mean(xy[keep]**2))
  prev=prior_metrics['full',lv,'oracle_heading']
  assert abs(h-prev['heading_rmse_deg'])<1e-10 and abs(x-prev['xy_rmse_m'])<1e-10
  assert all(metrics['rf',lv,f'{tau:.2f}_gate0']['heading_rmse_deg']>h for tau in taus)
  print('ungated_reference',lv,h,x,int(a['accepted'][keep].sum()),int(a['accepted'].sum()),prior_manifest[ref])
