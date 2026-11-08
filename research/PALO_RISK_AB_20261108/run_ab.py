#!/usr/bin/env python3
"""Pinned PALO A/B: exhaustive fixed-prior diagnosis and causal-feature risk study.
No RF regeneration, no new closed-loop rollout, no stage C/D, no test-set tuning.
"""
import argparse,base64,hashlib,io,json,os,platform,time,urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor,RandomForestClassifier
import sklearn

BASE='16450dc14366ba4ed2cb4e151952493f0efc944f'
REPO='myoungsunk/sionna-resimulation'
ROOT='research/PALO_GAP_STUDY_20261107'
DEST='research/PALO_RISK_AB_20261108'
GATE=6.6348966010212145
ALPHAS=[0.,.05,.1,.25,.5,1.]
CUTS=[.01,.025,.05,.1,.2,.35,.5,.75,1.]
ORIGINAL=['nis','innovation_abs','Hpsi_abs','Hxy_norm','Pxy_trace','Ppsi','Pxypsi_norm','correction_abs','dr_innov_mean5','dr_innov_std5','dr_heading_diff','dr_xy_diff']
MAG=[x for x in ORIGINAL if x!='dr_innov_mean5']+['dr_innov_mean5_abs']
RF_PARAMS=dict(n_estimators=64,max_depth=4,min_samples_leaf=40,max_features=1.0,n_jobs=2,random_state=2308)
CONTRACT=dict(scope='A/B ONLY; stored-prior counterfactuals; NOT closed-loop policy performance',base_commit=BASE,
 donors='12 baseline (S4/DR/Heading oracle) plus 4 development learned; 979 each',
 fit='baseline S4/DR only, 40<=t<100',calibration='baseline S4/DR only, 100<=t<120',gap='120<=t<140',
 diagnostic_test='t>=140; every donor, grouped by same physical k; R2 already exposed, NOT independent holdout',
 alphas=ALPHAS,models=['M0 refit stump','M1 magnitude','M2 signed interactions','M3 state/motion'],forest=RF_PARAMS,
 risk_cutoffs=CUTS,large_loss=dict(heading_abs_increase_deg=.5,xy_abs_increase_m=.01),
 calibration_selection='>=20 accepted; positive heading and nonnegative XY squared-error sum; empirical large-loss fractions <=.05 each; no negative sum in any level with >=10 accepted; maximize calibration heading gain. Otherwise abstain.',
 prohibited_inputs=['truth','errors','oracle action','level','donor','group','k','t','pose_id','absolute x/y','Full-LoS difference'],
 exclusions=['no C/D','no generalization claim','no Gaussian calibration claim','no independent audit claim'],
 frozen_before_test=True)

def digest(b):return hashlib.sha256(b).hexdigest()
def dump(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def delta(x,y):
 d=np.asarray(x)-np.asarray(y);d=d.copy();d[...,2]=wrap(d[...,2]);return d

def request(url):
 for attempt in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'PALO-A-B-reproducible-analysis'}),timeout=90) as r:return r.read()
  except Exception:
   if attempt==3:raise
   time.sleep(2**attempt)

def fetch(path):return request(f'https://raw.githubusercontent.com/{REPO}/{BASE}/{ROOT}/{path}')

def validate(a):
 n=len(a['t']);assert n==979 and a['prior_X'].shape==(n,4)
 for k in ['X','P','prior_X','prior_P','candidate_X','candidate_P','nis','features','truth','t']:
  assert np.isfinite(a[k]).all(),k
 assert np.all(np.diff(a['t'])>0) and len(np.unique(a['pose_id']))==n
 for k in ['P','prior_P','candidate_P']:
  assert np.max(abs(a[k]-a[k].swapaxes(-1,-2)))<1e-10 and np.linalg.eigvalsh(a[k]).min()>0,k
 yes=a['accepted'].astype(bool)
 for k,pr,ca in [('X','prior_X','candidate_X'),('P','prior_P','candidate_P')]:
  mask=yes.reshape((n,)+(1,)*(a[k].ndim-1));assert np.array_equal(a[k],np.where(mask,a[ca],a[pr]))
 d=delta(a['candidate_X'],a['prior_X']);reduction=a['prior_P']-a['candidate_P']
 magnitude=np.sqrt(np.maximum(reduction[:,2,2],0)*np.maximum(a['nis'],0))
 assert np.allclose(magnitude,abs(d[:,2]),atol=1e-7,rtol=1e-6),'ambiguous unwrapped correction'
 # All state components, not just heading, must agree with the scalar rank-one identity.
 expected=d[:,:,None]*d[:,None,:]
 scalar=reduction*a['nis'][:,None,None]
 assert np.max(abs(expected-scalar))<1e-7,'rank-one identity'
 return dict(branch_exact=True,minimum_eigenvalue=float(min(np.linalg.eigvalsh(a[k]).min() for k in ['P','prior_P','candidate_P'])),scalar_identity_max=float(np.max(abs(expected-scalar))))

def lag(x,n=5):
 return np.array([np.mean(x[max(0,k-n):k]) if k else 0. for k in range(len(x))])

def features(a,dr):
 # No truth, benefit, accepted, policy identity or bias-level input is read here.
 x,p=a['prior_X'],a['prior_P'];u,v=a['candidate_X'],a['candidate_P']
 d=delta(u,x);off=delta(x,dr['X']);f=pd.DataFrame(a['features'],columns=ORIGINAL)
 f['dr_innov_mean5_abs']=abs(f.dr_innov_mean5)
 signed=[]
 for j,name in enumerate(['x','y','psi','bg']):
  for prefix,vec in [('delta',d),('dr_offset',off)]:
   key=prefix+'_'+name;f[key]=vec[:,j];signed.append(key)
 c,s=np.cos(x[:,2]),np.sin(x[:,2])
 for prefix,vec in [('delta',d),('dr_offset',off)]:
  f[prefix+'_forward']=c*vec[:,0]+s*vec[:,1];f[prefix+'_lateral']=-s*vec[:,0]+c*vec[:,1]
  signed += [prefix+'_forward',prefix+'_lateral']
 f['dr_heading_alignment']=off[:,2]*d[:,2]
 f['dr_xy_alignment']=np.sum(off[:,:2]*d[:,:2],axis=1)
 f['dr_heading_distance_gain']=off[:,2]**2-wrap(off[:,2]+d[:,2])**2
 f['dr_xy_distance_gain']=np.sum(off[:,:2]**2-(off[:,:2]+d[:,:2])**2,axis=1)
 signed+=['dr_heading_alignment','dr_xy_alignment','dr_heading_distance_gain','dr_xy_distance_gain']
 state=[]
 vals={'P_xpsi':p[:,0,2],'P_ypsi':p[:,1,2],'bg_est':x[:,3],'bg_sigma':np.sqrt(p[:,3,3]),
  'P_psibg':p[:,2,3],'normalized_step':d[:,2]/np.sqrt(p[:,2,2]),
  'heading_fraction':1-v[:,2,2]/p[:,2,2],
  'xy_fraction':1-np.trace(v[:,:2,:2],axis1=1,axis2=2)/np.trace(p[:,:2,:2],axis1=1,axis2=2),
  'lag5_delta_psi':lag(d[:,2]),'lag5_delta_bg':lag(d[:,3]),'lag5_innovation_abs':lag(f.innovation_abs.to_numpy())}
 drstep=np.diff(dr['X'],axis=0,prepend=dr['X'][:1]);drstep[:,2]=wrap(drstep[:,2])
 vals.update(dr_motion_distance=np.linalg.norm(drstep[:,:2],axis=1),dr_turn=drstep[:,2],lag5_dr_turn=lag(drstep[:,2]))
 for k,z in vals.items():f[k]=z;state.append(k)
 state.append('dr_innov_mean5')
 assert np.isfinite(f.to_numpy()).all()
 return f,{'M1':MAG,'M2':MAG+signed,'M3':MAG+signed+state}

def labels(a):
 e=delta(a['prior_X'][:,:3],a['truth']);u=delta(a['candidate_X'][:,:3],a['truth']);d=delta(a['candidate_X'],a['prior_X'])
 h0=np.rad2deg(e[:,2]);h1=np.rad2deg(u[:,2]);p0=np.linalg.norm(e[:,:2],axis=1);p1=np.linalg.norm(u[:,:2],axis=1)
 gh=h0*h0-h1*h1;gx=p0*p0-p1*p1;no_wrap=abs(e[:,2]+d[:,2]-u[:,2])<1e-9
 mechanism=np.full(len(e),'neutral',dtype=object)
 mechanism[gh>1e-10]='beneficial';mechanism[(gh< -1e-10)&(e[:,2]*d[:,2]>=0)&no_wrap]='wrong_direction_or_unneeded'
 mechanism[(gh< -1e-10)&(e[:,2]*d[:,2]<0)&no_wrap]='overshoot';mechanism[~no_wrap]='circular_wrap'
 y=pd.DataFrame(dict(gh=gh,gx=gx,bh=abs(h0)-abs(h1),bx=p0-p1,prior_h_deg=h0,post_h_deg=h1,prior_xy=p0,post_xy=p1,
  risk_h=(abs(h1)-abs(h0)>.5),risk_xy=(p1-p0>.01),mechanism=mechanism))
 assert np.max(abs(a['benefit']-np.deg2rad(y.bh.to_numpy())))<1e-10
 assert np.max(abs(a['xy_benefit']-y.bx.to_numpy()))<1e-10
 acts=[]
 for alpha in ALPHAS:
  xx=a['prior_X']+alpha*d;xx[:,2]=wrap(xx[:,2]);pp=a['prior_P']-alpha*(a['prior_P']-a['candidate_P'])
  assert np.linalg.eigvalsh(pp).min()>0
  ee=delta(xx[:,:3],a['truth']);hh=np.rad2deg(ee[:,2]);xy=np.linalg.norm(ee[:,:2],axis=1)
  acts.append(pd.DataFrame(dict(alpha=alpha,gh=h0*h0-hh*hh,gx=p0*p0-xy*xy,bh=abs(h0)-abs(hh),bx=p0-xy)))
 return y,acts

def measure(meta,y,accept):
 take=np.asarray(accept,bool);n=len(take);z=y.loc[take];m=int(take.sum())
 return dict(n=n,accepted=m,coverage=float(m/n),heading_gain_deg2=float(z.gh.sum()),xy_gain_m2=float(z.gx.sum()),
  heading_loss_deg2=float(np.maximum(-z.gh,0).sum()),xy_loss_m2=float(np.maximum(-z.gx,0).sum()),
  beneficial_fraction=float((z.gh>1e-10).mean()) if m else None,
  large_h_fraction=float(z.risk_h.mean()) if m else None,large_xy_fraction=float(z.risk_xy.mean()) if m else None,
  largest_h_increase_deg=float(np.maximum(-z.bh,0).max()) if m else 0.,
  largest_xy_increase_m=float(np.maximum(-z.bx,0).max()) if m else 0.,
  fixed_prior_heading_rmse_deg=float(np.sqrt(np.mean(y.prior_h_deg**2-np.where(take,y.gh,0)))),
  fixed_prior_xy_rmse_m=float(np.sqrt(np.mean(y.prior_xy**2-np.where(take,y.gx,0)))))

def probability(model,x):
 proba=model.predict_proba(x);classes=model.classes_
 return proba[:,list(classes).index(True)] if True in classes else np.zeros(len(x))

def train_models(f,y):
 scale=np.maximum(np.quantile(np.abs(y[['gh','gx']].to_numpy()),.9,axis=0),[1e-8,1e-10])
 reg=RandomForestRegressor(**RF_PARAMS).fit(f,y[['gh','gx']].to_numpy()/scale)
 hc=RandomForestClassifier(**RF_PARAMS).fit(f,y.risk_h)
 xc=RandomForestClassifier(**RF_PARAMS).fit(f,y.risk_xy)
 return dict(gain=reg,hazard_h=hc,hazard_xy=xc,scale=scale)

def predict(m,f):
 g=m['gain'].predict(f)*m['scale']
 return g[:,0],g[:,1],np.maximum(probability(m['hazard_h'],f),probability(m['hazard_xy'],f))

def main(out):
 out.mkdir(exist_ok=False,parents=True);dump(out/'CONTRACT.json',CONTRACT)
 delivery=json.loads(fetch('DELIVERY_MANIFEST.json'))['files'];receipts=[]
 def checked(path):
  b=fetch(path);spec=delivery[path];assert len(b)==spec['bytes'] and digest(b)==spec['sha256'],path
  blob=hashlib.sha1(('blob '+str(len(b))+'\0').encode()+b).hexdigest();assert blob==spec['git_blob']
  receipts.append(dict(path=path,sha256=digest(b),bytes=len(b),git_blob=blob));return b
 summary=json.loads(checked('results/SUMMARY.json'))
 chosen=[r for r in summary['rows'] if (r['group']=='baseline' and r['name'] in ('s4','dr','heading')) or (r['group']=='development' and r['name']=='learned')]
 assert len(chosen)==16
 def load(r):
  b=checked('results/trajectories/'+r['path'])
  with np.load(io.BytesIO(b),allow_pickle=False) as z:a={k:z[k].copy() for k in z.files}
  return (r['group'],r['level'],r['name']),a,validate(a)
 loaded=list(ThreadPoolExecutor(4).map(load,chosen));data={key:a for key,a,q in loaded}
 frames=[];labs=[];actions=[];qa=[];fs=None
 for key,a,q in loaded:
  group,level,donor=key;dr=data['baseline',level,'dr']
  for k in ['t','pose_id','truth']:assert np.array_equal(a[k],dr[k]),'frame alignment'
  f,fs=features(a,dr);changed=dict(a,truth=a['truth']+1000,benefit=a['benefit']+1000,xy_benefit=a['xy_benefit']-1000,accepted=~a['accepted'])
  assert np.array_equal(f.to_numpy(),features(changed,dr)[0].to_numpy()),'label/mask leakage'
  y,act=labels(a)
  meta=pd.DataFrame(dict(group=group,level=level,donor=donor,k=np.arange(979),t=a['t'],pose_id=a['pose_id'],gate=a['nis']<=GATE))
  meta['split']=np.select([a['t']<40,a['t']<100,a['t']<120,a['t']<140],['warmup','fit','calibration','gap'],default='test')
  meta['block']=np.floor(a['t']/10).astype(int)
  frames.append(pd.concat([meta,f],axis=1));labs.append(pd.concat([meta,y],axis=1))
  actions.extend(pd.concat([meta,x],axis=1) for x in act)
  q.update(group=group,level=level,donor=donor,truth_mask_perturbation_pass=True)
  ev=a['t']>=(140 if group=='development' else 40);e=delta(a['X'][:,:3],a['truth'])
  record=next(r for r in chosen if (r['group'],r['level'],r['name'])==key)
  q['heading_rmse_recheck_delta']=abs(np.rad2deg(np.sqrt(np.mean(e[ev,2]**2)))-record['heading_rmse_deg'])
  q['xy_rmse_recheck_delta']=abs(np.sqrt(np.mean(np.sum(e[ev,:2]**2,axis=1)))-record['xy_rmse_m'])
  assert q['heading_rmse_recheck_delta']<1e-10 and q['xy_rmse_recheck_delta']<1e-10
  qa.append(q)
 F=pd.concat(frames,ignore_index=True);Y=pd.concat(labs,ignore_index=True);ACT=pd.concat(actions,ignore_index=True)
 assert len(F)==15664 and len(ACT)==93984
 assert F.groupby('k').split.nunique().max()==1
 F.to_csv(out/'online_features.csv.gz',index=False);Y.to_csv(out/'offline_labels.csv.gz',index=False);ACT.to_csv(out/'fixed_prior_actions.csv.gz',index=False)
 # Stage A results and same-physical-frame prior contrasts.
 ar=[];pair=[]
 for (gr,lv,dn),a in Y.groupby(['group','level','donor'],sort=False):
  a=a[a.t>=(140 if gr=='development' else 40)];eg=a[a.gate]
  rec=dict(group=gr,level=lv,donor=dn,all_n=len(a),eligible_n=len(eg))
  for c in ['beneficial','wrong_direction_or_unneeded','overshoot','neutral','circular_wrap']:rec[c]=int((eg.mechanism==c).sum())
  soft=ACT[(ACT.group==gr)&(ACT.level==lv)&(ACT.donor==dn)&(ACT.t>=(140 if gr=='development' else 40))]
  best=soft.groupby('k').gh.max();full=eg.set_index('k')
  rec['full_harmful_soft_head_rescuable']=int(((full.gh< -1e-10)&(best.reindex(full.index)>1e-10)).sum())
  rec.update(measure(a,a,a.gate.to_numpy()));ar.append(rec)
 for lv in ['B0','L0','L1','L2']:
  s=Y[(Y.group=='baseline')&(Y.level==lv)&(Y.donor=='s4')&(Y.t>=40)].set_index('k')
  d=Y[(Y.group=='baseline')&(Y.level==lv)&(Y.donor=='dr')&(Y.t>=40)].set_index('k')
  h=Y[(Y.group=='baseline')&(Y.level==lv)&(Y.donor=='heading')&(Y.t>=40)].set_index('k')
  for k in s.index:
   pair.append(dict(level=lv,k=int(k),t=float(s.loc[k,'t']),s4_good=bool(s.loc[k,'gh']>1e-10),dr_good=bool(d.loc[k,'gh']>1e-10),oracle_good=bool(h.loc[k,'gh']>1e-10),s4_gate=bool(s.loc[k,'gate']),dr_gate=bool(d.loc[k,'gate']),s4_gh=float(s.loc[k,'gh']),dr_gh=float(d.loc[k,'gh'])))
 pd.DataFrame(ar).to_csv(out/'A_summary.csv',index=False);pd.DataFrame(pair).to_csv(out/'same_frame_prior_comparison.csv',index=False)
 # Stage B: fixed fit and calibration before reading test labels for scoring.
 donorfit=(F.group=='baseline')&F.donor.isin(['s4','dr']);fit=donorfit&(F.split=='fit');cal=donorfit&(F.split=='calibration');test=F.split=='test'
 assert fit.sum()==2400 and cal.sum()==800 and test.sum()==4464
 assert not set(F.loc[fit,'k'])&set(F.loc[test,'k'])
 forbidden=set(CONTRACT['prohibited_inputs'])|{'accepted','benefit','xy_benefit'}
 assert not forbidden.intersection(set(sum(fs.values(),[])))
 frozen={};calrows=[];preds={};yt=Y.loc[test].reset_index(drop=True);mt=F.loc[test].reset_index(drop=True)
 # M0 refit reproduces the earlier one-threshold design on fit data ONLY.
 best=dict(feature='never',direction='le',threshold=0.,objective=0.)
 yf=Y.loc[fit];gf=F.loc[fit,'gate'].to_numpy()
 for col in ORIGINAL:
  for cut in np.unique(np.quantile(F.loc[fit,col],[.1,.2,.3,.4,.5,.6,.7,.8,.9])):
   for direction in ['le','gt']:
    take=gf&((F.loc[fit,col].to_numpy()<=cut) if direction=='le' else (F.loc[fit,col].to_numpy()>cut))
    if yf.loc[take,'gx'].sum()>=0 and yf.loc[take,'bh'].sum()>best['objective']:
     best=dict(feature=col,direction=direction,threshold=float(cut),objective=float(yf.loc[take,'bh'].sum()))
 frozen['M0']=best
 for name,cols in fs.items():
  model=train_models(F.loc[fit,cols],Y.loc[fit]);ph,px,pr=predict(model,F.loc[cal,cols]);yc=Y.loc[cal].reset_index(drop=True);mc=F.loc[cal].reset_index(drop=True)
  locked=None;bestgain=0.
  for cut in CUTS:
   yes=mc.gate.to_numpy()&(ph>0)&(px>=0)&(pr<=cut);m=measure(mc,yc,yes)
   good=m['accepted']>=20 and m['heading_gain_deg2']>0 and m['xy_gain_m2']>=0 and m['large_h_fraction']<=.05 and m['large_xy_fraction']<=.05
   for lv in ['B0','L0','L1','L2']:
    ss=yes&(mc.level.to_numpy()==lv)
    if ss.sum()>=10:good=good and yc.loc[ss,'gh'].sum()>=0 and yc.loc[ss,'gx'].sum()>=0
   calrows.append(dict(model=name,threshold=cut,qualifies=bool(good),**m))
   if good and m['heading_gain_deg2']>bestgain:locked=cut;bestgain=m['heading_gain_deg2']
  frozen[name]=dict(features=cols,threshold=locked,abstain=locked is None,calibration_best_gain=bestgain)
  joblib.dump(model,out/(name+'_models.joblib'),compress=3)
  preds[name]=predict(model,F.loc[test,cols])
 dump(out/'FROZEN_MODELS.json',frozen);freeze_hash=digest((out/'FROZEN_MODELS.json').read_bytes())
 pd.DataFrame(calrows).to_csv(out/'B_calibration.csv',index=False)
 # Thresholds/models are frozen; no policy selection below.
 policies={'never':np.zeros(len(mt),bool),'always_gate':mt.gate.to_numpy()}
 if best['feature']=='never':policies['M0']=np.zeros(len(mt),bool)
 else:policies['M0']=mt.gate.to_numpy()&((mt[best['feature']].to_numpy()<=best['threshold']) if best['direction']=='le' else (mt[best['feature']].to_numpy()>best['threshold']))
 sweep=[];prediction_frames=[]
 for name,(ph,px,pr) in preds.items():
  lock=frozen[name]['threshold'];base=mt.gate.to_numpy()&(ph>0)&(px>=0)
  policies[name]=np.zeros(len(mt),bool) if lock is None else base&(pr<=lock)
  pf=mt[['group','level','donor','k','t']].copy();pf['model']=name;pf['pred_gh']=ph;pf['pred_gx']=px;pf['risk_score']=pr;pf['selected']=policies[name];prediction_frames.append(pf)
  for cut in CUTS:
   yes=base&(pr<=cut)
   for dn in ['s4','dr','heading','learned']:
    mask=mt.donor.to_numpy()==dn;sweep.append(dict(model=name,threshold=cut,donor=dn,**measure(mt.loc[mask],yt.loc[mask],yes[mask])))
 metrics=[]
 for name,yes in policies.items():
  for (gr,lv,dn),idx in mt.groupby(['group','level','donor']).groups.items():
   idx=np.asarray(list(idx));metrics.append(dict(model=name,group=gr,level=lv,donor=dn,**measure(mt.loc[idx],yt.loc[idx],yes[idx])))
 pd.DataFrame(metrics).to_csv(out/'B_test_metrics.csv',index=False);pd.DataFrame(sweep).to_csv(out/'B_test_risk_sweep.csv',index=False)
 pd.concat(prediction_frames,ignore_index=True).to_csv(out/'B_test_predictions.csv.gz',index=False)
 # Semantic equivalence test: retaining or removing the SAME current factor.
 rng=np.random.default_rng(2308);x=rng.normal(size=(200,4));d=rng.normal(size=(200,4))*.1
 semantic=max(float(np.max(abs((x+a*d)-((x+d)-(1-a)*d)))) for a in ALPHAS)
 assert semantic<1e-12
 pairdf=pd.DataFrame(pair);comparison=[]
 for lv,z in pairdf.groupby('level'):
  both=z.s4_gate&z.dr_gate
  comparison.append(dict(level=lv,n=len(z),s4_beneficial=int(z.s4_good.sum()),dr_beneficial=int(z.dr_good.sum()),disagree_all=int((z.s4_good!=z.dr_good).sum()),both_gate_n=int(both.sum()),disagree_both_gate=int((both&(z.s4_good!=z.dr_good)).sum())))
 dump(out/'QA.json',dict(trajectories=qa,hash_verified_files=len(receipts),feature_rows=len(F),action_rows=len(ACT),split_counts=dict(fit=int(fit.sum()),calibration=int(cal.sum()),test=int(test.sum())),same_frame_split_consistent=True,semantic_add_remove_max_difference=semantic,frozen_model_sha256=freeze_hash,stages_C_D_executed=False))
 dump(out/'SOURCE_MANIFEST.json',dict(commit=BASE,inputs=sorted(receipts,key=lambda x:x['path']),script_sha256=digest(Path(__file__).read_bytes()),python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__))
 main_summary=dict(status='A_B_EXECUTED_SELF_CHECK_PASS',scope=CONTRACT['scope'],source_commit=BASE,rows=len(F),action_rows=len(ACT),same_frame_comparison=comparison,A=ar,frozen_models=frozen,B=metrics,stages_C_D='NOT_RUN',independent_audit='NOT_RUN',independent_holdout=False)
 dump(out/'SUMMARY.json',main_summary)
 report=['# PALO A/B results','',CONTRACT['scope'],'','Raw sources: '+BASE,'',f'Validated 16 trajectories, {len(F)} priors, {len(ACT)} action rows.','',
  'Fit 40–100 s; calibration 100–120 s; gap 120–140 s; diagnostic test >=140 s. Same physical frames grouped. No oracle donor used for training/calibration. R2 is already exposed.','',
  '## Add vs remove','Same prior, candidate and decision imply identical X/P. Prior histories, not the verbal default, change the problem. Omitting a new factor does not undo old RF updates.','',
  '## Same-frame benefit disagreements','|level|n|S4 beneficial|DR beneficial|disagreements|both gate|disagreements both gate|','|---|---:|---:|---:|---:|---:|---:|']
 for z in comparison:report.append('|'+ '|'.join(str(z[k]) for k in ['level','n','s4_beneficial','dr_beneficial','disagree_all','both_gate_n','disagree_both_gate'])+'|')
 report+=['','## Locked thresholds','```json',json.dumps(frozen,indent=2),'```','','## Limitations','B evaluates same-prior counterfactual risk, NOT recursively executed policy RMSE. Oracle-prior tests are privileged-state diagnostics. Classifier scores are not certified probabilities. Scaling is modeled information weakening, not calibrated uncertainty. No C/D or new RF simulations were run.','', 'See A_summary.csv, B_test_metrics.csv, B_test_risk_sweep.csv, online_features.csv.gz and offline_labels.csv.gz.']
 (out/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
 dump(out/'OUTPUT_SHA256.json',{p.name:dict(sha256=digest(p.read_bytes()),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()})
 print(json.dumps(dict(status=main_summary['status'],rows=len(F),same_frame=comparison,thresholds={k:v.get('threshold') for k,v in frozen.items()})),flush=True)

def publish(out):
 token=os.environ['GITHUB_TOKEN'];repo=os.environ.get('REPO',REPO);branch=os.environ['BRANCH'];source=os.environ['SOURCE_SHA']
 def api(method,path,obj=None):
  req=urllib.request.Request('https://api.github.com/repos/'+repo+path,data=None if obj is None else json.dumps(obj).encode(),method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'PALO-AB-publish'})
  with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
 head=api('GET','/git/ref/heads/'+branch)['object']['sha'];assert head==source,'branch changed; refuse publication'
 tree=api('GET','/git/commits/'+head)['tree']['sha'];entries=[]
 for p in sorted(out.iterdir()):
  if not p.is_file():continue
  b=p.read_bytes();blob=api('POST','/git/blobs',dict(content=base64.b64encode(b).decode(),encoding='base64'))['sha']
  entries.append(dict(path=DEST+'/results/'+p.name,mode='100644',type='blob',sha=blob))
 tr=api('POST','/git/trees',dict(base_tree=tree,tree=entries))['sha']
 commit=api('POST','/git/commits',dict(message='PALO A/B executed: fixed-prior risk diagnostics, locked models, QA; no C/D',tree=tr,parents=[head]))['sha']
 assert api('GET','/git/ref/heads/'+branch)['object']['sha']==head
 api('PATCH','/git/refs/heads/'+branch,dict(sha=commit,force=False))
 dump(out/'PUBLICATION.json',dict(branch=branch,source_sha=source,result_sha=commit,run_id=os.environ.get('RUN_ID'),files=len(entries)))
 print('PUBLISHED_RESULT_COMMIT',commit,flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--publish',action='store_true');args=ap.parse_args()
 main(args.output)
 if args.publish:publish(args.output)
