import json,hashlib,sys,itertools,platform,time
from pathlib import Path
import numpy as np
import engine as E
from scipy.stats import rankdata,spearmanr
B=E.BASE;O=B/'results'; LEVELS=('B0','L0','L1','L2'); TAUS=(.02,.05,.10,.20)
def save(name,obj):
 (O/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def record(group,lv,name,spec,start=40,switch=None,features=False,**extra):
 path=O/'trajectories'/f'{group}_{lv}_{name}.npz'
 a=E.replay(lv,spec,path,switch=switch,feature_output=features)
 r=dict(group=group,level=lv,name=name,path=path.name,**extra,**E.metrics(a,start))
 ROWS.append(r)
 return a,r
def validate_math(a,lv):
 # Independent rank-one scalar measurement covariance and state update.
 from math import radians
 hH=[E.lut.model(x,E.case) for x in a['prior_X']]
 H=np.array([v[1][1] for v in hH]); nu=E.Z-np.array([v[0][1] for v in hH])
 ph=np.einsum('nij,nj->ni',a['prior_P'],H);S=np.einsum('ni,ni->n',ph,H)+.0081
 K=ph/S[:,None];x=a['prior_X']+K*nu[:,None];x[:,2]=E.wrap(x[:,2]);P=a['prior_P']-K[:,:,None]*ph[:,None,:]
 assert np.max(abs(x-a['candidate_X']))<1e-12
 assert np.max(abs(P-a['candidate_P']))<1e-12
 assert np.max(abs(nu**2/S-a['nis']))<1e-10
 yes=a['accepted'];assert np.array_equal(a['X'],np.where(yes[:,None],a['candidate_X'],a['prior_X']))
 assert np.array_equal(a['P'],np.where(yes[:,None,None],a['candidate_P'],a['prior_P']))
 # Previous selected state/P, not a frozen donor, must generate next prior.
 c=E.controls(lv)
 for k in range(1,E.N):
  x,P=E.advance(a['X'][k-1],a['P'][k-1],c,k)
  assert np.array_equal(x,a['prior_X'][k]) and np.array_equal(P,a['prior_P'][k])
def auc(x,y):
 n=int(y.sum());m=len(y)-n
 return None if not n or not m else float((rankdata(x)[y].sum()-n*(n+1)/2)/(n*m))
def feature_analysis():
 out=[];bins=[];examples=[]
 for lv in LEVELS:
  for policy in ('s4','dr','heading'):
   a=CACHE[lv,policy];take=E.T>=40;f=a['features'][take];b=a['benefit'][take];xy=a['xy_benefit'][take];y=b>1e-12
   for j,key in enumerate(E.FEATURES):
    z=f[:,j];corr=None if np.ptp(z)==0 else float(spearmanr(z,b).statistic)
    out.append(dict(level=lv,prior=policy,feature=key,n=len(b),beneficial=int(y.sum()),auc_benefit=auc(z,y),spearman_benefit=corr))
    cuts=np.unique(np.quantile(z,[0,.25,.5,.75,1]))
    for q,(lo,hi) in enumerate(zip(cuts[:-1],cuts[1:])):
     m=(z>=lo)&(z<=hi if q==len(cuts)-2 else z<hi)
     if m.any():bins.append(dict(level=lv,prior=policy,feature=key,lo=float(lo),hi=float(hi),n=int(m.sum()),beneficial_fraction=float(y[m].mean()),benefit_sum_deg=float(np.rad2deg(b[m].sum())),xy_benefit_sum_m=float(xy[m].sum())))
   for label,inds in [('most_harmful',np.argsort(b)[:10]),('most_beneficial',np.argsort(b)[-10:])]:
    for i in inds:examples.append(dict(level=lv,prior=policy,type=label,k=int(np.flatnonzero(take)[i]),benefit_deg=float(np.rad2deg(b[i])),**{key:float(f[i,j]) for j,key in enumerate(E.FEATURES)}))
 save('FEATURE_ASSOCIATIONS.json',out);save('FEATURE_QUARTILES.json',bins);save('FEATURE_COUNTEREXAMPLES.json',examples)
def train_stump():
 F=[];G=[];Y=[];XY=[]
 for lv in LEVELS:
  for policy in ('s4','dr'):
   a=CACHE[lv,policy];m=(E.T>=40)&(E.T<120)
   F.append(a['features'][m]);G.append(a['nis'][m]<=E.GATE);Y.append(a['benefit'][m]);XY.append(a['xy_benefit'][m])
 f=np.concatenate(F);g=np.concatenate(G);y=np.concatenate(Y);xy=np.concatenate(XY)
 best=dict(feature='never',direction='none',threshold=0.,objective=0.,xy_benefit=0.,selected=0)
 candidates=[('always','none',0.,g)]
 for j,key in enumerate(E.FEATURES):
  for cut in np.unique(np.quantile(f[:,j],np.arange(.1,1,.1))):
   candidates.extend([(key,'le',float(cut),g&(f[:,j]<=cut)),(key,'gt',float(cut),g&(f[:,j]>cut))])
 for key,direction,cut,m in candidates:
  score=float(y[m].sum());xb=float(xy[m].sum())
  if xb>=0 and score>best['objective']+1e-15:best=dict(feature=key,direction=direction,threshold=cut,objective=score,xy_benefit=xb,selected=int(m.sum()))
 best.update(training_rows=len(y),train='40<=t<120, S4+DR 4 levels',test='t>=140; common S4 history',independent_holdout=False)
 save('FROZEN_DEVELOPMENT_MODEL.json',best)
 return best
ROWS=[];CACHE={}
def main():
 O.mkdir(exist_ok=False);(O/'trajectories').mkdir()
 started=time.time()
 manifest=json.loads((E.PRIOR/'INPUT_MANIFEST.json').read_bytes())
 for r in manifest['files']:
  p=E.PRIOR/'inputs'/r['path'].split('research/POL_HEADING_RESEARCH_20261107/',1)[1]
  assert digest(p)==r['sha256']
 provenance=dict(started_unix=started,python=sys.version,numpy=np.__version__,platform=platform.platform(),input_manifest_sha=digest(E.PRIOR/'INPUT_MANIFEST.json'),files={str(p):digest(p) for p in [B/'CONTRACT.md',B/'engine.py',B/'campaign.py',E.PRIOR/'inputs/governance/COMMON_CONTRACT.md',E.PRIOR/'inputs/governance/ROLE_IMPLEMENTER.md']})
 save('EXECUTION_PROVENANCE.json',provenance)
 # Decision extreme cases, no neutral accepted, NIS override cannot bypass gate.
 f=np.zeros(len(E.FEATURES));spec=dict(mode='errors',kind='both',fn=np.ones(E.N,bool),fp=np.ones(E.N,bool))
 assert not E.action(spec,0,f,1.,True) and E.action(spec,0,f,-1.,True)
 assert not E.action(spec,0,f,0.,True) and not E.action(spec,0,f,-1.,False)
 parity=[]
 for lv in LEVELS:
  for p in ('s4','dr','heading'):
   a,r=record('baseline',lv,p,dict(mode=p),features=True);CACHE[lv,p]=a
   old=np.load(E.PRIOR/'results_v2'/f'full_{lv}_{"oracle_heading_gate" if p=="heading" else p}.npz')
   err={key:float(np.max(abs(a[key]-old[key]))) for key in ('X','P','nis')}
   assert err['X']<=1e-7 and err['P']<=1e-8 and err['nis']<=1e-7 and np.array_equal(a['accepted'],old['accepted'])
   parity.append(dict(level=lv,policy=p,**err));validate_math(a,lv)
 save('BASELINE_PARITY_PASS.json',parity)
 print('BASELINE_PARITY_PASS 12',flush=True)
 for lv in LEVELS:
  for tau in TAUS:
   for gated in (False,True):
    a,r=record('rf',lv,f'{tau:.2f}_gate{int(gated)}',dict(mode='rf',tau=tau,gated=gated),tau=tau,gated=gated)
    validate_math(a,lv)
    if not gated:
     K=int(a['accepted'].sum())
     for seed in range(5):
      schedule=np.zeros(E.N,bool);schedule[np.random.default_rng(seed).choice(E.N,K,replace=False)]=True
      ar,rr=record('random',lv,f'{tau:.2f}_s{seed}',dict(mode='random',schedule=schedule),tau=tau,seed=seed,target_count=K)
      assert ar['accepted'].sum()==K
  print('RF_DONE',lv,flush=True)
 feature_analysis();print('FEATURE_ANALYSIS_DONE',flush=True)
 for lv in LEVELS:
  for pattern in ('iid','burst'):
   for kind in ('fn','fp','both'):
    # Zero-error limit must be the gated oracle on its own trajectory.
    z=np.zeros(E.N,bool)
    a=E.replay(lv,dict(mode='errors',kind=kind,fn=z,fp=z))
    assert np.array_equal(a['X'],CACHE[lv,'heading']['X']) and np.array_equal(a['P'],CACHE[lv,'heading']['P'])
    for rate in (.01,.05,.10,.20):
     for seed in range(5):
      fn,fp=E.error_masks(rate,seed,pattern)
      a,r=record('sensitivity',lv,f'{pattern}_{kind}_{rate:.2f}_s{seed}',dict(mode='errors',kind=kind,fn=fn,fp=fp),pattern=pattern,kind=kind,rate=rate,seed=seed)
      if seed==0 and rate==.2:validate_math(a,lv)
   print('SENSITIVITY_DONE',lv,pattern,flush=True)
 model=train_stump();print('MODEL_FROZEN',model,flush=True)
 for lv in LEVELS:
  specs=[('s4',dict(mode='s4')),('dr',dict(mode='dr')),('heading',dict(mode='heading')),('learned',dict(mode='learned',model=model))]+[(f'rf_{tau:.2f}',dict(mode='rf',tau=tau)) for tau in TAUS]
  for name,spec in specs:
   a,r=record('development',lv,name,spec,start=140,switch=140,features=True)
   assert np.array_equal(a['X'][E.T<140],CACHE[lv,'s4']['X'][E.T<140])
   validate_math(a,lv)
 # Perturb truth while preserving all inputs: RF and learned X/P/masks must not change.
 changed=E.TRUTH.copy();changed[:,:2]+=100;changed[:,2]=E.wrap(changed[:,2]+1.)
 for spec in (dict(mode='rf',tau=.05),dict(mode='learned',model=model)):
  a=E.replay('B0',spec,switch=140);b=E.replay('B0',spec,truth=changed,switch=140)
  assert all(np.array_equal(a[k],b[k]) for k in ('X','P','accepted'))
 assert len(ROWS)==12+32+80+480+32
 assert len({r['path'] for r in ROWS})==len(ROWS)
 save('SUMMARY.json',dict(status='EXECUTED_SELF_CHECK_PASS',rows=ROWS,elapsed_seconds=time.time()-started,trajectories=len(ROWS),independent_generalization='NOT_ESTABLISHED'))
 save('CHECKS.json',dict(input_hashes=86,baseline_parity_cases=12,recorded_trajectories=len(ROWS),zero_error_limits=24,truth_perturbation_policies=2,math_checks='12 baseline +32 RF +24 representative sensitivity +32 development',count_matched_controls=80,independent_audit=False))
 print('COMPLETE',len(ROWS),'seconds',time.time()-started,flush=True)
if __name__=='__main__':main()
