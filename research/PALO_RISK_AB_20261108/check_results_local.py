"""Post-run arithmetic and decision verification. Same author, not independent audit."""
from pathlib import Path
import numpy as np,pandas as pd,json,hashlib,joblib,warnings
ROOT=Path(__file__).resolve().parent;P=ROOT/'results';O=ROOT/'verification';O.mkdir(exist_ok=True)
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--artifact',type=Path);args=ap.parse_args()
manifest=json.loads((P/'OUTPUT_SHA256.json').read_text())
for name,record in manifest.items():
 b=(P/name).read_bytes();assert len(b)==record['bytes'] and hashlib.sha256(b).hexdigest()==record['sha256']
F=pd.read_csv(P/'online_features.csv.gz');Y=pd.read_csv(P/'offline_labels.csv.gz');A=pd.read_csv(P/'fixed_prior_actions.csv.gz');B=pd.read_csv(P/'B_test_metrics.csv');Q=pd.read_csv(P/'B_test_predictions.csv.gz');M=json.loads((P/'FROZEN_MODELS.json').read_text())
key=['group','level','donor','k','t']
assert F[key].equals(Y[key])
assert not set(F[(F.split=='fit')].k)&set(F[(F.split=='test')].k)
assert F.groupby('k').split.nunique().max()==1
h0=Y.prior_h_deg.to_numpy();h1=Y.post_h_deg.to_numpy();dp=np.rad2deg(F.delta_psi.to_numpy());after=(h0+dp+180)%360-180
errs={'angle_reconstruction_deg':float(np.max(abs(after-h1))),'heading_gain_deg2':float(np.max(abs(Y.gh-(h0*h0-h1*h1)))),'xy_gain_m2':float(np.max(abs(Y.gx-(Y.prior_xy**2-Y.post_xy**2))))}
assert errs['angle_reconstruction_deg']<1e-10
J=A.merge(F[key+['delta_psi','delta_x','delta_y']],on=key,validate='many_to_one').merge(Y[key+['prior_h_deg']],on=key,validate='many_to_one')
h=(J.prior_h_deg+np.rad2deg(J.alpha*J.delta_psi)+180)%360-180
errs['alpha_heading_gain_deg2']=float(np.max(abs(J.gh-(J.prior_h_deg**2-h*h))))
assert errs['alpha_heading_gain_deg2']<1e-7
calout=[];testmax=0.;thresholds=[]
for name in ['M1','M2','M3']:
 with warnings.catch_warnings():
  warnings.simplefilter('ignore');model=joblib.load(P/(name+'_models.joblib'))
 cols=M[name]['features'];test=F.split=='test';cal=(F.split=='calibration')&(F.group=='baseline')&F.donor.isin(['s4','dr'])
 def risk(m,x):
  classes=list(m.classes_);return m.predict_proba(x)[:,classes.index(True)] if True in classes else np.zeros(len(x))
 def predict(x):
  g=model['gain'].predict(x)*model['scale'];return g[:,0],g[:,1],np.maximum(risk(model['hazard_h'],x),risk(model['hazard_xy'],x))
 ph,px,pr=predict(F.loc[test,cols]);stored=Q[Q.model==name]
 assert F.loc[test,key].reset_index(drop=True).equals(stored[key].reset_index(drop=True))
 testmax=max(testmax,float(np.max(abs(ph-stored.pred_gh.to_numpy()))),float(np.max(abs(px-stored.pred_gx.to_numpy()))),float(np.max(abs(pr-stored.risk_score.to_numpy()))))
 assert testmax<1e-9
 lock=M[name]['threshold'];yes=F.loc[test,'gate'].to_numpy()&(ph>0)&(px>=0)&(pr<=lock)
 assert np.array_equal(yes,stored.selected.to_numpy())
 # Recompute case metrics from a separately merged prediction/label table.
 z=stored.merge(Y,on=key,validate='one_to_one')
 for (gr,lv,dn),r in z.groupby(['group','level','donor']):
  e=B[(B.model==name)&(B.group==gr)&(B.level==lv)&(B.donor==dn)].iloc[0];s=r[r.selected]
  assert len(s)==e.accepted
  assert abs(s.gh.sum()-e.heading_gain_deg2)<1e-8 and abs(s.gx.sum()-e.xy_gain_m2)<1e-8
 ph,px,pr=predict(F.loc[cal,cols]);z=Y.loc[cal].copy();z['selected']=F.loc[cal,'gate'].to_numpy()&(ph>0)&(px>=0)&(pr<=lock)
 for (lv,dn),r in z.groupby(['level','donor']):
  s=r[r.selected];calout.append(dict(model=name,level=lv,donor=dn,n=len(r),accepted=len(s),heading_gain_deg2=float(s.gh.sum()),xy_gain_m2=float(s.gx.sum()),large_h_fraction=float(s.risk_h.mean()) if len(s) else None,large_xy_fraction=float(s.risk_xy.mean()) if len(s) else None))
# action tables include rejected candidates; rescue summaries distinguish gate.
soft=[]
for (gr,lv,dn),r in Y.groupby(['group','level','donor']):
 r=r[(r.t>=(140 if gr=='development' else 40))&r.gate]
 a=A[(A.group==gr)&(A.level==lv)&(A.donor==dn)&A.k.isin(r.k)]
 both=a[(a.gh>1e-10)&(a.gx>1e-12)]
 origjoint=r[(r.gh>1e-10)&(r.gx>1e-12)]
 rescued=set(both.k)-set(origjoint.k)
 soft.append(dict(group=gr,level=lv,donor=dn,n=len(r),full_joint_good=len(origjoint),soft_joint_possible=both.k.nunique(),additional_soft_joint_cases=len(rescued)))
pd.DataFrame(calout).to_csv(O/'calibration_by_prior.csv',index=False)
pd.DataFrame(soft).to_csv(O/'soft_joint_rescue.csv',index=False)
errs.update(frozen_prediction_max_difference=testmax,artifact_sha256=hashlib.sha256(args.artifact.read_bytes()).hexdigest() if args.artifact else None,source_code_sha256=hashlib.sha256((ROOT/'run_ab.py').read_bytes()).hexdigest(),status='ARITHMETIC_RECHECK_PASS_SAME_AUTHOR',new_closed_loop_run=False,independent_audit=False)
(O/'RECHECK.json').write_text(json.dumps(errs,indent=2)+'\n');print(json.dumps(errs,indent=2));print(pd.DataFrame(calout).to_string(index=False));print(pd.DataFrame(soft).to_string(index=False))
