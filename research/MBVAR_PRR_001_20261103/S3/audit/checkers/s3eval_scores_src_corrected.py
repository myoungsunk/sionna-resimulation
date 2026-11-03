import json,hashlib,subprocess,itertools
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import chi2
root=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');pkg=root/'research/MBVAR_PRR_001_20261103';s=pkg/'S3';run=s/'runs/EVAL_001';cache=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/S1_INPUTS')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
 with np.load(p) as f:return dict(f)
def blob(c,p):return subprocess.check_output(['git','--git-dir='+str(root/'.git'),'show',c+':'+str(p.relative_to(root))])
count=0;maxdiff=0.
def same(a,b,label):
 global count,maxdiff
 a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape,(label,a.shape,b.shape)
 if a.dtype.kind in 'USOb' or b.dtype.kind in 'USOb':assert np.array_equal(a,b),label
 else:
  assert np.allclose(a,b,atol=2e-10,rtol=2e-10,equal_nan=True),(label,np.nanmax(abs(a-b)))
  valid=np.isfinite(a)&np.isfinite(b)
  if valid.any():maxdiff=max(maxdiff,float(np.max(abs(a[valid]-b[valid]))))
 count+=1
m=json.loads((run/'RUN_MANIFEST.json').read_text());gr=m['grant'];authraw=blob(gr['approval_commit'],s/'audit/GO_S3_LOCKED_EVAL.json');auth=json.loads(authraw)
assert hashlib.sha256(authraw).hexdigest()==gr['audit_sha256'];assert auth['token']==gr['token']=='GO_S3_LOCKED_EVAL'
assert auth['code_commit']==gr['code_commit']=='e68482d262665fff7d0c43749758a523fbf0f4e4'
assert auth['dev_manifest_sha256']==sha(s/'runs/DEV_001/RUN_MANIFEST.json')
assert auth['rules_sha256']==m['config_hash']==sha(s/'RULES.json');assert auth['contract_sha256']==sha(pkg/'A0_R3_REFIT/CONTRACT_LOCK.json')
assert m['status']=='COMPLETE' and m['expected_main']==640 and m['expected_auxiliary']==0 and m['n']==640
assert (run/'FAILURES.jsonl').read_bytes()==b''
for st in ('S1','S2','S3'):
 for p in (pkg/st).glob('*.py'):assert p.read_bytes()==blob(gr['code_commit'],p),str(p)
ah=json.loads((run/'ARTIFACT_HASHES.json').read_text())
for name,digest in ah.items():assert sha(run/name)==digest,name
assert set(ah)=={p.name for p in run.iterdir() if p.is_file() and p.name!='ARTIFACT_HASHES.json'}
ixs=json.loads((run/'TRACE_INDEX.json').read_text());events=json.loads((run/'EVENTS.json').read_text())
keys=['route','bias','channel','seed','arm','kind','variant']
def ident(ix):return tuple(ix.get(k,'main') for k in keys)
ixmap={ident(ix):ix for ix in ixs};assert len(ixmap)==640
cells=list(itertools.product(('R4','R5'),('B0','L2'),('Full','Native_LoS')))
assert {ident(ix) for ix in ixs if ix['kind']=='P'}=={(*c,seed,arm,'P','main') for c in cells for seed in range(10,30) for arm in ('A','B','C_CP','D_CP')}
assert not any(ix['kind']!='P' for ix in ixs)
scores=pd.read_csv(run/'SCORES_PER_SEED.csv');scores['variant']=scores.get('variant',pd.Series('main',index=scores.index)).fillna('main');assert len(scores)==3200;scores=scores.set_index(keys+['window'],verify_integrity=True)
timing=pd.read_csv(run/'TIMING.csv');timing['variant']=timing.get('variant',pd.Series('main',index=timing.index)).fillna('main');timing=timing.set_index(keys,verify_integrity=True)
snap=pd.DataFrame();ends=pd.read_csv(run/'EVENT_ENDPOINTS.csv');ends['variant']=ends.get('variant',pd.Series('main',index=ends.index)).fillna('main');ends=ends.set_index(keys+['event_index'],verify_integrity=True)
cts=pd.read_csv(run/'RECOVERY_COUNTS.csv');cts['variant']=cts.get('variant',pd.Series('main',index=cts.index)).fillna('main');cts=cts[cts.arm.notna()].set_index(keys,verify_integrity=True)
packets={};truths={};epsilon={};baselines={};sourceparity=0;identityparity=0;timed=0;packetcount=0;endpointcount=0;min_eig=1e9
def endpoint(t,x,gt,before,target):
 h=abs(np.rad2deg(np.arctan2(np.sin(x[:,2]-gt[:,2]),np.cos(x[:,2]-gt[:,2]))));xy=np.linalg.norm(x[:,:2]-gt[:,:2],axis=1);h0=abs(np.rad2deg(np.arctan2(np.sin(before[2]-target[2]),np.cos(before[2]-target[2]))));q0=np.linalg.norm(before[:2]-target[:2]);first=None;rt=np.nan
 for ti,ok in zip(t,(h<=1)&(xy<=.1)):
  if not ok:first=None
  elif first is None:first=ti
  if first is not None and ti-first>=2-1e-9:rt=ti-t[0];break
 d=dict(start_heading_deg=h0,start_xy_m=q0,first_emitted_heading_deg=h[0],first_emitted_xy_m=xy[0],recovery_time_s=rt,censored=np.isnan(rt),available_s=t[-1]-t[0],already_accurate=h0<=1 and q0<=.1)
 for sec in (10,20):
  sel=t<=t[0]+sec+1e-9;d['heading_integral_'+str(sec)+'s']=np.trapezoid(h[sel],t[sel]);d['xy_integral_'+str(sec)+'s']=np.trapezoid(xy[sel],t[sel]);d['window_'+str(sec)+'s_censored']=t[-1]<t[0]+sec-1e-9
 return d
for no,ix in enumerate(ixs):
 sk=ident(ix);route,bias,ch,seed,arm,kind,variant=sk;key=f'{route}_aB_m0_{bias}_{ch}';base=f'{route}_aB_m0_{bias}';tr=load(run/ix['file']);assert sha(run/ix['file'])==ix['sha256'];idx=tr['sample_index'];n=len(idx);packetcount+=n;x=tr['x'];P=tr['P'];assert n==ix['n'] and np.isfinite(x).all() and np.isfinite(P).all()
 if key not in packets:
  packets[key]=load(cache/'algorithm_input'/(key+'.npz'));truths[key]=load(cache/'evaluator_truth'/(base+'.npz'));epsilon[key]=load(cache/'evaluator_epsilon_r1'/(key+'.npz'))['epsilon_s']
 pk=packets[key];ttfull=truths[key];tt={k:(v[idx] if v.ndim and len(v)==len(ttfull['t']) else v) for k,v in ttfull.items()};t=tt['t'];gt=tt['truth'];same(tr['pose_id'],pk['pose_id'][idx],'source IDs');same(tr['t'],t,'time');assert np.array_equal(idx,np.arange(idx[0],idx[-1]+1))
 scale=np.array([.1,.1,np.deg2rad(1),np.deg2rad(.05)]);eig=np.linalg.eigvalsh(P/scale[None,:,None]/scale[None,None,:]);min_eig=min(min_eig,float(eig.min()));assert eig.min()>-1e-9;same(P,P.swapaxes(1,2),'P sym')
 if kind=='P' and arm in ('A','B'):
  src=pkg/'S1/runs/EVAL_001'/(f'{key}_{seed}_'+('W0' if arm=='A' else 'W-d0-DS')+'.npz');prior=load(src)
  for field in ('x','P','prior','Pprior','h','H','mu','Reff','mask'):same(tr[field],prior[field],'S1 '+field)
  sourceparity+=1
 if kind=='P' and arm=='A':baselines[sk[:4]]=tr
 same(tr['mask'],baselines[sk[:4]]['mask'][idx],'fixed shadow mask')
 if kind=='identity':
  ref=load(run/ixmap[(*sk[:4],'A' if arm=='C_CP' else 'B','P','main')]['file'])
  for field in ('x','P','shadow_x','shadow_P','mask','candidate','episode_first'):same(tr[field],ref[field],'identity '+field)
  identityparity+=1
 evfile=run/(Path(ix['file']).stem+'_EVENTS.json');local_ev=json.loads(evfile.read_text());global_ev=[{k:v for k,v in e.items() if k not in keys} for e in events if ident(e)==sk];assert local_ev==global_ev
 assert cts.loc[sk,'attempts']==len(local_ev) and cts.loc[sk,'adoptions']==sum(e['disposition']=='ACCEPT' for e in local_ev)
 adopted={e['index'] for e in local_ev if e['disposition']=='ACCEPT'};adoptmask=np.isin(idx,list(adopted))
 d0=pk['z'][idx,1]-tr['h'][:,1];wd=np.maximum(.25,np.minimum(1,.2/(abs(d0)+1e-12))**2);ws=np.maximum(.25,np.minimum(1,.07138038868537433/(abs(pk['D'][idx])+1e-12))**2);w=np.maximum(.25,wd*ws) if arm in ('B','D_CP') else np.ones(n)
 if kind!='identity':w[adoptmask]=.25
 same(tr['weight'],w,'weight');same(tr['d0'],d0,'d0')
 sig=np.interp(tr['rho_before'],[0,1.5,3,6,10],[.011,.020,.050,.120,.240]);rv=pk['R'][idx].copy();rv[:,1,1]+=sig**2;re=rv.copy();re[:,1,1]/=w;same(tr['Rvar'],rv,'Rvar');same(tr['Reff'],re,'Reff');same(tr['mu'],pk['muMB'][idx],'mu')
 nu=pk['z'][idx]-tr['h']-tr['mu'];same(tr['nu'],nu,'nu');H=tr['H'];pp=tr['Pprior'];S=H@pp@H.swapaxes(1,2)+re;S=(S+S.swapaxes(1,2))/2;K=np.linalg.solve(S,H@pp).swapaxes(1,2);K[~tr['mask']]=0
 y=tr['prior']+np.einsum('nij,nj->ni',K,nu);y[:,2]=(y[:,2]+np.pi)%(2*np.pi)-np.pi;J=np.eye(4)[None]-K@H;C=J@pp@J.swapaxes(1,2)+K@re@K.swapaxes(1,2);C=(C+C.swapaxes(1,2))/2
 same(tr['S'],S,'S');same(tr['K'],K,'K');same(x,y,'posterior');same(P,C,'Joseph')
 tm=timing.loc[sk];shouldtime=kind=='P' and seed==0;assert bool(tm.real_clock_5Hz)==shouldtime and tm.dropped_packets==0 and tm.packets==n
 if shouldtime:
  timed+=1;assert np.all(tr['arrival_to_emitted_ns']>=0) and np.all(tr['queue_wait_ns']>=0)
  same(tr['arrival_to_emitted_ns'],tr['latency_ns']+tr['queue_wait_ns'],'actual arrival latency')
  same(tm.timed_p99_ms,np.quantile(tr['arrival_to_emitted_ns'],.99)/1e6,'p99');same(tm.timed_max_ms,tr['arrival_to_emitted_ns'].max()/1e6,'max latency')
  emitted=(t-t[0])*1e9+tr['arrival_to_emitted_ns'];assert np.all(np.diff(emitted)>0)
  assert tm.wall_clock_s>=(emitted[-1]/1e9)-1e-6
 else:assert np.all(tr['arrival_to_emitted_ns']==-1) and np.all(tr['queue_wait_ns']==0)
 if kind=='M':
  start=idx[0];row=snap.loc[sk];assert start==row.start_index;ep=endpoint(t,x,gt,baselines[sk[:4]]['prior'][start],gt[0]);assert row.cohort_source=='PRETREATMENT_PREDICTED_PRIOR'
  for fld,val in ep.items():same(row[fld],val,'M endpoint '+fld)
  initial=json.loads((run/f'{key}_{variant}_INITIAL.json').read_text());same(tr['initial_x'],initial['chain']['x'],'M initialx');same(tr['initial_P'],initial['chain']['P'],'M initialP')
  assert initial['history_last_index']==start-1 and initial['chain']['last_pose_id']==(int(pk['pose_id'][start-1]) if start else None)
  end=int(np.searchsorted(pk['t'],pk['t'][start]+20+1e-9,side='right'));same(idx,np.arange(start,end),'20s inclusive M')
 else:
  for event in local_ev:
   k=event['index'];row=ends.loc[sk+(k,)];ep=endpoint(pk['t'][k:],x[k:],ttfull['truth'][k:],tr['pre_replay_prior'][k],ttfull['truth'][k]);assert row.cohort_source=='PRETREATMENT_PREDICTED_PRIOR'
   for fld,val in ep.items():same(row[fld],val,'event endpoint '+fld)
   endpointcount+=1
 if kind!='M':
  e=np.column_stack((x[:,:3]-gt,x[:,3]-tt['bg']));e[:,2]=np.arctan2(np.sin(e[:,2]),np.cos(e[:,2]));hd=np.rad2deg(e[:,2]);xy=np.linalg.norm(e[:,:2],axis=1);off=gt[:,:2]-[10,0];rho=np.linalg.norm(off,axis=1);rad=off/rho[:,None];tan=np.column_stack((-rad[:,1],rad[:,0]));ne={j:np.einsum('ni,ni->n',e[:,:j],np.linalg.solve(P[:,:j,:j],e[:,:j,None])[:,:,0]) for j in (2,3,4)};pre=tr['mask'];flag=w<1;large=abs(tt['e_mp'])>.3 if ch=='Full' else np.zeros(n,bool);clean=abs(tt['e_mp'])<=.05 if ch=='Full' else np.ones(n,bool)
  for window,sel in [('all',np.ones(n,bool)),('initial',t<30),('primary',t>=30),('near',rho<=1.5),('late',t>=2*t[-1]/3)]:
   r=scores.loc[sk+(window,)];d={'n':int(sel.sum())}
   if not sel.any():continue
   def rms(a):return np.sqrt(np.mean(a[sel]**2))
   d.update(heading_rmse_deg=rms(hd),xy_rmse_m=rms(xy),radial_rmse_m=rms(np.sum(e[:,:2]*rad,axis=1)),tangent_rmse_m=rms(np.sum(e[:,:2]*tan,axis=1)),signed_heading_deg=hd[sel].mean(),signed_x_m=e[sel,0].mean(),signed_y_m=e[sel,1].mean(),heading_p95_deg=np.quantile(abs(hd[sel]),.95),heading_max_deg=abs(hd[sel]).max(),xy_p95_m=np.quantile(xy[sel],.95),xy_max_m=xy[sel].max(),sigma_heading_deg=np.rad2deg(np.sqrt(P[sel,2,2])).mean(),ellipse95_area=np.mean(np.pi*chi2.ppf(.95,2)*np.sqrt(np.linalg.det(P[sel,:2,:2]))),xy_coverage95=np.mean(ne[2][sel]<=chi2.ppf(.95,2)),pregate_nis_mean=tr['nis'][sel].mean())
   for j in (2,3,4):d['nees'+str(j)]=ne[j][sel].mean()
   for prob in (.68,.95,.99):d['heading_coverage'+str(round(prob*100))]=np.mean(e[sel,2]**2/P[sel,2,2]<=chi2.ppf(prob,1))
   for k,v in dict(accepted=pre,discounted=pre&flag,large=pre&large,clean=pre&clean,true_positive=pre&large&flag,clean_flagged=pre&clean&flag,intermediate=pre&~large&~clean).items():d[k]=int(np.sum(sel&v))
   d['precision']=d['true_positive']/d['discounted'] if d['discounted'] else np.nan;d['recall']=d['true_positive']/d['large'] if d['large'] else np.nan;d['clean_loss']=d['clean_flagged']/d['clean'] if d['clean'] else np.nan
   elig=pre&sel
   if elig.any():
    v=re[elig,1,1]
    for lab,ser in [('innovation',nu[:,1]),('measurement_epsilon',epsilon[key])]:
     sq=ser[elig]**2;d['mean_'+lab+'2_over_Reff_joint_accepted']=np.mean(sq/v);d['ratio_mean_'+lab+'2_to_mean_Reff_joint_accepted']=np.mean(sq)/np.mean(v)
    used=elig&(w>0);sq=epsilon[key][used]**2;v=re[used,1,1];d['mean_epsilon2_over_Reff_s_used']=np.mean(sq/v);d['ratio_mean_epsilon2_to_mean_Reff_s_used']=np.mean(sq)/np.mean(v)
   for q in (.5,.95,.99):d['packet_p'+str(round(q*100))+'_ms']=np.quantile(tr['latency_ns'][sel],q)/1e6
   for fld,val in d.items():same(r[fld],val,'score '+fld)

 if (no+1)%80==0:print('VERIFIED_TRACE',no+1,flush=True)
assert len(snap)==0 and endpointcount==len(ends) and sourceparity==320 and identityparity==0 and timed==0
print(json.dumps(dict(status='PASS',traces=len(ixs),packet_count=packetcount,score_rows=3200,event_endpoint_rows=endpointcount,M_endpoint_rows=len(snap),S1_baseline_parity=sourceparity,identity_parity=identityparity,timed_5Hz_traces=timed,all_artifact_files=len(ah),checks=count,max_abs_difference=maxdiff,minimum_scaled_P_eigenvalue=min_eig,manifest_sha256=sha(run/'RUN_MANIFEST.json'),scientific_replays=0)),flush=True)
