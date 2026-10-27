from pathlib import Path
import sys,os,json,hashlib,importlib.util,traceback,datetime
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent;REPO=BASE.parents[1]
SRC=Path(r'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2')
ART=SRC.parent/'p2_artifacts'
sys.dont_write_bytecode=True
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
os.environ.update(PJ_SOURCE_ROOT=str(SRC),PJ_ART=str(ART),PJ_OUT=str(ROOT/'runtime'))
sys.path.insert(0,str(SRC/'research/PJ_DS_GATED_20261021'))
import numpy as np,pandas as pd
import v_replay as V
from geometry_model import GeometryFFD
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0'];EDGES=np.array([0,.5,1,1.5,2,3,4,6,8,np.inf]);LABELS=['0-.5','.5-1','1-1.5','1.5-2','2-3','3-4','4-6','6-8','8-inf'];EPS=1e-12
CHECKS=[];LOCK=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(n,d):
 (ROOT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def event(stage,**kw):
 r=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage=stage,**kw)
 with (ROOT/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(r)+'\n')
 print(json.dumps(r),flush=True)
def stop():
 p=os.environ.get('MANAGED_PROCESS_STOP_FILE')
 if p and Path(p).exists():raise RuntimeError('MANAGED_STOP')
def check(name,a,b,tol=1e-10):
 a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape,(name,a.shape,b.shape)
 err=float(np.max(np.abs(a.astype(float)-b.astype(float)))) if a.size else 0.;ok=bool(np.isfinite(err) and err<=tol);CHECKS.append(dict(name=name,max_abs=err,tolerance=tol,pass_check=ok))
 if not ok:write('CHECKS.json',dict(status='FAIL',checks=CHECKS));raise RuntimeError(f'{name}: {err} > {tol}')
def wrap(x):return 180-(180-x)%360
def load(p):
 with np.load(p) as z:return {k:z[k] for k in z.files}
def axes(p,a):
 v=p-a;d=np.linalg.norm(v,axis=1);assert np.all(d>1e-9);ur=v/d[:,None];ut=np.c_[-ur[:,1],ur[:,0]];return d,ur,ut

def c0():
 # Freeze every canonical local input already used in the previous validated campaign.
 old=json.loads(Path(r'D:\SLAM_bot\DS_COMPONENT_AZIMUTH_20261027\INPUT_LOCK.json').read_text())['files']
 for x in old:assert sha(x['path'])==x['sha256'],x['path']
 paths=[Path(x['path']) for x in old]+list((BASE/'e1_e4/E1').glob('*.npz'))+[BASE/'e1_e4/SCORES.csv',SRC/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json',BASE/'geometry_physical/geometry_model.py']+list((SRC/'research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_r2diag').glob('*_R2DIAG_PACKETS.csv.gz'))+list(ROOT.glob('*.py'))+[ROOT/'PROTOCOL.md']
 LOCK.extend(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(set(paths)))
 write('INPUT_LOCK.json',dict(baseline_commit='d2fe43a',execution_parent='9ff1810',files=LOCK))
 inventory=[];parity=[];cache=[];scores=pd.read_csv(BASE/'e1_e4/SCORES.csv');required='t_s pose_id names prior x Pprior P h H K nu acc R mu truth_scoring_only'.split()
 for case in V.MANIFEST['cases']:
  for bias in ['B0','L2']:
   path=BASE/'e1_e4/E1'/f'{case["id"]}_{bias}.npz';z=load(path);missing=sorted(set(required)-z.keys());inventory.append(dict(case=case['id'],bias=bias,path=str(path),fields={k:list(v.shape) for k,v in z.items()},missing=missing));write('C0_TRACE_INVENTORY.json',inventory)
   if missing:raise RuntimeError('C0 missing fields '+str(missing))
   idx=[list(z['names']).index(n) for n in ['A0','A1']];m=z['t_s']>=30;truth=z['truth_scoring_only'];a=np.asarray(case['anchor']);height=a[2]-case['robot_z_m'];dgt=np.sqrt(np.sum((truth[:,:2]-a[:2])**2,axis=1)+height**2)
   for j,arm in zip(idx,['BB','MB']):
    e=wrap(np.degrees(z['x'][:,j,2]-truth[:,2]));dist=np.sqrt(np.sum((z['x'][:,j,:2]-a[:2])**2,axis=1)+height**2);got=[float(np.sqrt(np.mean(e[m]**2))),float(e[m].mean()),float(np.sqrt(np.mean((100*(dist[m]-dgt[m]))**2)))];q=scores[(scores.stage=='E1')&(scores.case==case['id'])&(scores.bias==bias)&(scores.arm==('A0' if arm=='BB' else 'A1'))].iloc[0];expected=q[['heading_rmse_deg','heading_bias_deg','range_rmse_cm']].to_numpy(float);check('C0_'+case['id']+bias+arm,np.array(got),expected);parity.append(dict(case=case['id'],bias=bias,arm=arm,got=got,expected=expected.tolist()))
    for key in ['P','Pprior']:
     cov=z[key][:,j];check('symmetric_'+key,cov,cov.swapaxes(-1,-2),1e-12);mineig=float(np.linalg.eigvalsh(cov).min());assert mineig>=-1e-12
    check('K2_hb',z['H'][:,j,1,3],np.zeros(len(m)),0);check('K2_range_psi',z['H'][:,j,0,2],np.zeros(len(m)),0)
    dx=z['x'][:,j,:3]-z['prior'][:,j,:3];dx[:,2]=np.radians(wrap(np.degrees(dx[:,2])));kv=np.einsum('nij,nj->ni',z['K'][:,j,:3],z['nu'][:,j])*z['acc'][:,j,None];kv[:,2]=np.radians(wrap(np.degrees(kv[:,2])));check('K4_update',dx,kv)
   cache.append((case,bias,z,idx))
 write('C0_PARITY.json',dict(status='PASS',conditions=len(cache),comparisons=parity));event('C0_PASS',conditions=len(cache));return cache

def eval_model(model,source,x,case):
 values=[];diags=[]
 for start in range(0,len(x),48):
  stop();xx=x[start:start+48];h,_,diag=model.batch(xx,case,gradient=False,return_diagnostics=True);hh,_=source.batch(xx,case,gradient=False);check('K5_'+case['id'],h[:,1],hh[:,1],1e-12);values.append(h);diags.append(diag)
 return np.concatenate(values),{k:np.concatenate([v[k] for v in diags]) for k in diags[0]}

def run():
 cache=c0();rng=np.random.default_rng(20261027);theta=rng.uniform(-np.pi,np.pi,100);d=rng.uniform(.2,12,100);p=np.c_[np.cos(theta)*d,np.sin(theta)*d];_,_,ut=axes(p,np.zeros(2));h=1e-4
 def beta(v):return np.arctan2(-v[:,1],-v[:,0])
 b0=beta(p);der=[]
 for j in range(2):
  q=np.eye(2)[j]*h
  def delta(v):return np.angle(np.exp(1j*(beta(v)-b0)))
  der.append((-delta(p+2*q)+8*delta(p+q)-8*delta(p-q)+delta(p-2*q))/(12*h))
 check('K1_gradient_beta',ut/d[:,None],np.array(der).T,1e-9)
 source=V.SourceFFD();model=GeometryFFD(banks=source.banks);model.modes=None;model.explicit=None
 residual=pd.concat([pd.read_csv(SRC/f'research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_r2diag/{r}_R2DIAG_PACKETS.csv.gz') for r in ['R2','R4','R5']],ignore_index=True);assert not residual.duplicated(['case','pose_id']).any();residual=residual.set_index(['case','pose_id'])
 outputs={k:[] for k in ['C1','C1B','C2','C3']}
 for case,bias,z,idx in cache:
  truth=z['truth_scoring_only'];anchor=np.array(case['anchor'])[:2];dg,urg,utg=axes(truth[:,:2],anchor);n=len(dg);lookup=residual.loc[[(case['id'],int(pid)) for pid in z['pose_id']]].reset_index();check('residual_ids',lookup.pose_id.to_numpy(),z['pose_id'],0)
  for j,arm in zip(idx,['BB','MB']):
   xp=z['prior'][:,j];de,ure,ute=axes(xp[:,:2],anchor);bins=np.searchsorted(EDGES,dg,side='right')-1
   common=dict(case=case['id'],route=case['route'],bias=bias,arm=arm,k=np.arange(n),pose_id=z['pose_id'],t_s=z['t_s'],scoring=z['t_s']>=30,accepted=z['acc'][:,j],d_gt_m=dg,d_est_m=de,bin=np.array(LABELS)[bins])
   hs=z['H'][:,j,1];hr=np.einsum('ni,ni->n',hs[:,:2],ure);ht=np.einsum('ni,ni->n',hs[:,:2],ute);db=ht*de;dp=hs[:,2];kap=np.divide(abs(db),abs(dp),out=np.full(n,np.nan),where=abs(dp)>EPS)
   posgt=xp.copy();posgt[:,:2]=truth[:,:2];allgt=truth.copy();xx=np.concatenate([xp,posgt,allgt]);hv,diag=eval_model(model,source,xx,case);he,hp,hg=np.split(hv[:,1],3);check('K5_stored_h',he,z['h'][:,j,1],1e-12)
   c1=pd.DataFrame(dict(**common,h_x=hs[:,0],h_y=hs[:,1],h_psi=dp,h_b=hs[:,3],h_rad_per_m=hr,h_tan_per_m=ht,ds_dbeta_per_deg=np.radians(db),ds_dpsi_per_deg=np.radians(dp),kappa=kap,fp_margin=diag['fp_margin'][:n],tap=diag['tap'][:n],strong_port=diag['strong_port'][:n],cells=[json.dumps(v.tolist()) for v in diag['cells'][:n]]));outputs['C1'].append(c1)
   c1b=pd.DataFrame(dict(**common,s_pred_est=he,s_pred_posGT=hp,s_pred_allGT=hg,ds_pos=he-hp,ds_psi=hp-hg,r_base=lookup.r_base.to_numpy(),e_true=lookup.e_true.to_numpy(),V=lookup.V.to_numpy(),g=lookup.g.to_numpy(),dist_r2diag=lookup.dist.to_numpy()));outputs['C1B'].append(c1b)
   ks=z['K'][:,j,:,1];kr=z['K'][:,j,:,0];ksr=np.einsum('ni,ni->n',ks[:,:2],ure);kst=np.einsum('ni,ni->n',ks[:,:2],ute);ar=hr*ksr;at=ht*kst;ap=dp*ks[:,2];ab=hs[:,3]*ks[:,3];total=np.einsum('ni,ni->n',hs,ks);check('K3_allocation',ar+at+ap+ab,total,1e-12);Sss=np.einsum('ni,nij,nj->n',hs,z['Pprior'][:,j],hs)+z['R'][:,j,1,1]
   shares={f'share_{name}':np.divide(val,total,out=np.full(n,np.nan),where=abs(total)>EPS) for name,val in [('rad',ar),('tan',at),('psi',ap),('b',ab)]}
   inc={}
   for name,kcol,nu in [('pol',ks,z['nu'][:,j,1]),('rng',kr,z['nu'][:,j,0])]:
    dx=kcol*nu[:,None]*z['acc'][:,j,None];dt=np.einsum('ni,ni->n',dx[:,:2],ute);dr=np.einsum('ni,ni->n',dx[:,:2],ure);inc.update({f'dpsi_{name}_deg':np.degrees(dx[:,2]),f'dt_{name}_cm':dt*100,f'dr_{name}_cm':dr*100,f'dbeta_{name}_deg':np.degrees(dt/de)})
   outputs['C2'].append(pd.DataFrame(dict(**common,nu_s=z['nu'][:,j,1],nu_r=z['nu'][:,j,0],S_ss=Sss,R_ss=z['R'][:,j,1,1],HsKs=total,a_rad=ar,a_tan=at,a_psi=ap,a_b=ab,**shares,**inc)))
   cal={}
   for state,covkey,suffix in [('x','P',''),('prior','Pprior','_prior')]:
    x=z[state][:,j];cov=z[covkey][:,j];e=x[:,:2]-truth[:,:2];er=np.einsum('ni,ni->n',e,urg);et=np.einsum('ni,ni->n',e,utg);_,_,_=axes(x[:,:2],anchor)
    vb=anchor-x[:,:2];vg=anchor-truth[:,:2];be=wrap(np.degrees(np.arctan2(vb[:,1],vb[:,0])-np.arctan2(vg[:,1],vg[:,0])));pe=wrap(np.degrees(x[:,2]-truth[:,2]));st=np.sqrt(np.einsum('ni,nij,nj->n',utg,cov[:,:2,:2],utg));sr=np.sqrt(np.einsum('ni,nij,nj->n',urg,cov[:,:2,:2],urg));sp=np.sqrt(cov[:,2,2]);assert np.all(st>0) and np.all(sr>0) and np.all(sp>0)
    vals=dict(e_r_cm=er*100,e_t_cm=et*100,beta_err_deg=be,psi_err_deg=pe,sigma_r_cm=sr*100,sigma_t_cm=st*100,sigma_beta_deg=np.degrees(st/dg),sigma_psi_deg=np.degrees(sp),rho_t_psi=np.einsum('ni,ni->n',utg,cov[:,:2,2])/(st*sp),z_r=er/sr,z_t=et/st,z_psi=pe/np.degrees(sp));cal.update({k+suffix:v for k,v in vals.items()})
   outputs['C3'].append(pd.DataFrame(dict(**common,**cal)))
   event('ARM_PASS',case=case['id'],bias=bias,arm=arm,n=n)
  for key,frames in outputs.items():pd.concat(frames,ignore_index=True).to_csv(ROOT/f'{key}_PACKETS.csv.gz',index=False,compression='gzip')
 for x in LOCK:assert sha(x['path'])==x['sha256'],x['path']
 write('CHECKS.json',dict(status='PASS',checks=CHECKS));write('CALC_GATE.json',dict(status='PASS',conditions=len(cache),arms=2,no_replay=True));event('CALC_COMPLETE')
if __name__=='__main__':
 try:run()
 except BaseException as e:write('FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));event('STOP_FAILURE',error=str(e));raise
