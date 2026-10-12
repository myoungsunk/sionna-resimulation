"""Stage B V05 (exploratory): Range-only competitor models on the frozen harness, leave-one-route-out tables.
Arms: A RF-off | B fixed offset (baseline) | MU distance-conditional mean | MUVAR conditional mean + variance | IAT fixed offset, R inflated by training integrated-autocorrelation time.
NOT RUN: Gauss-Markov bias state / Schmidt-consider (requires a state-augmented filter core)."""
import json,shutil
from pathlib import Path
import numpy as np,pandas as pd
S=Path(__file__).resolve().parent;G=S/'g7';JV=G/'job_v05'
if not JV.exists():shutil.copytree(G/'job',JV)
for f in (JV/'OUTPUT').glob('09_V2*'):f.unlink()
f=pd.read_csv(G/'out/01_FEATURES_12.csv');l=pd.read_csv(G/'out/02_LABELS_EVAL_ONLY_12.csv');d=f.merge(l,on=['case','route','pose_id'])
RT=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/S1/routes')
drive_ids={r:set(pd.read_csv(RT/f'timeline_{r}_Tnone.csv').query("phase=='drive'").pose_id) for r in ('R2','R4','R5')}
d=d[[p in drive_ids[r] for r,p in zip(d.route,d.pose_id)]].reset_index(drop=True)      # drive-phase poses only
TC=json.load(open('/home/user/sionna-resimulation/research/STAGE_B_EXPLORATORY_20261012/out/v05_timecorr.json'))
def iat(x,maxlag=80):
    x=np.asarray(x,float);x=x[np.isfinite(x)];x=x-x.mean();v=np.dot(x,x)/len(x);ac=np.array([np.dot(x[:-k],x[k:])/(len(x)-k)/v for k in range(1,maxlag)]);cut=np.argmax(ac<0.05) if (ac<0.05).any() else len(ac);return float(1+2*ac[:cut].sum())
tables={}
for held in ('R2','R4','R5'):
    tr=d[d.route!=held];edges=np.quantile(tr.true_distance_m,np.linspace(0,1,9));edges[0]-=1e-9;edges[-1]+=1e-9;cen=[];mu=[];sd=[]
    for a,b in zip(edges[:-1],edges[1:]):
        g=tr[(tr.true_distance_m>=a)&(tr.true_distance_m<b)];cen.append(float(g.true_distance_m.mean()));mu.append(float(g.e_range.mean()));sd.append(float(g.e_range.std()))
    longs=[c for c in tr.case.unique() if c[:2] in ('R2','R5')]        # IAT only from routes with long straight legs (R4 legs are 38 samples: unobservable)
    ia_g=float(np.median([TC['cases'][c]['e_full_global']['iat_samples'] for c in longs]));ia_c=float(np.median([TC['cases'][c]['e_full_conditional']['iat_samples'] for c in longs]))
    tables[held]=dict(centers=cen,mu=mu,sd=sd,iat=ia_g,iat_cond=ia_c,train_cases=sorted(tr.case.unique()),iat_from=longs)
(JV/'LORO_TABLES.json').write_text(json.dumps(tables,indent=1))
src=(G/'job/simulate_g7.py').read_text().replace(str(G/'job'),str(JV))
a="class Recorder(F.SensorV2Filter):"
b='''TABLES=json.loads((J/'LORO_TABLES.json').read_text())
def RM(arm,route):
 t=TABLES[route];c=np.array(t['centers']);mu=np.array(t['mu']);sd=np.array(t['sd']);base=0.08**2
 f_mu=lambda h:(float(np.interp(h,c,mu)),float((np.interp(h+0.01,c,mu)-np.interp(h-0.01,c,mu))/0.02))
 if arm=='MU':return dict(mu=f_mu,R=lambda h:base)
 if arm=='MUVAR':return dict(mu=f_mu,R=lambda h:max(float(np.interp(h,c,sd))**2,base))
 if arm=='IAT':return dict(mu=lambda h:(META_OFF,0.),R=lambda h:base*t['iat'])
 if arm=='MUVAR_IAT':return dict(mu=f_mu,R=lambda h:max(float(np.interp(h,c,sd))**2,base)*t['iat_cond'])
 return None
class Recorder(F.SensorV2Filter):
 def range_record(self,z):
  rm=getattr(self,'rm',None)
  if rm is None:return super().range_record(z)
  x=self.comps[0].x;a=self.cfg.anchor_xyz;dz=a[2]-self.cfg.robot_z;h=float(np.sqrt((x[0]-a[0])**2+(x[1]-a[1])**2+dz**2))
  if h<=1e-12:return np.nan,np.nan,np.nan,'undefined_geometry'
  H=np.zeros(6);H[:2]=(x[:2]-np.array(a[:2]))/h;m,dm=rm['mu'](h)
  return self.scalar(z,h+m,H*(1+dm),rm['R'](h),'r')
'''
assert a in src;src=src.replace(a,b+a.replace("class Recorder(F.SensorV2Filter):","class _Unused(F.SensorV2Filter):"),1) if False else src.replace(a,b.rstrip('\n').replace("class Recorder(F.SensorV2Filter):\n","")+"\n"+a.replace(a,"")) if False else src
# simpler: insert TABLES/RM before the class and add the range_record method inside the existing Recorder
head,rest=src.split(a,1)
pre=b.split("class Recorder(F.SensorV2Filter):")[0]
meth=b.split("class Recorder(F.SensorV2Filter):\n")[1]
src=head+pre+a+"\n"+meth+rest.lstrip('\n') if False else head+pre+a+"\n"+meth+rest
src=src.replace("META_OFF","meta['range_bias']['mean_m']")
old="f=Recorder(cfg,LUT,x0)";assert old in src;src=src.replace(old,"f=Recorder(cfg,LUT,x0);f.rm=RM(arm,route)")
old2="cfg=configure(case,level,arm!='A',arm in ['C','D','E'],known)";assert old2 in src;src=src.replace(old2,"cfg=configure(case,level,arm!='A',False,known)")
t0="tasks=[(c,d,s,a,'stochastic','unknown',phase) for c in cases for d in range(3) for s in range(50) for a in ['A','B','C','D']]";assert t0 in src
src=src.replace(t0,"tasks=[(c,d,s,a,'stochastic','unknown',phase) for c in cases for d in range(3) for s in range(20) for a in ['A','B','MU','MUVAR','IAT','MUVAR_IAT']]")
(JV/'simulate_v05.py').write_text(src)
print(json.dumps({k:dict(iat=round(v['iat'],2),iat_cond=round(v['iat_cond'],2),mu=[round(x,3) for x in v['mu']],sd=[round(x,3) for x in v['sd']]) for k,v in tables.items()}))
