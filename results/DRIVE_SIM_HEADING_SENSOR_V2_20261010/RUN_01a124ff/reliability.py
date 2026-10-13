from pathlib import Path
import json,time,pickle,concurrent.futures
import numpy as np,pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
J=Path('/job');OUT=J/'RELIABILITY';OUT.mkdir(exist_ok=True)
def metrics(y,p):
 y=np.asarray(y,int);p=np.clip(np.asarray(p,float),1e-8,1-1e-8);bins=np.minimum((p*10).astype(int),9);ece=sum(np.mean(bins==i)*abs(y[bins==i].mean()-p[bins==i].mean()) for i in range(10) if np.any(bins==i));r={'n':len(y),'prevalence':float(y.mean()),'brier':brier_score_loss(y,p),'ece10':float(ece),'auroc':None,'pr_auc':None}
 if len(np.unique(y))==2:
  r.update(auroc=roc_auc_score(y,p),pr_auc=average_precision_score(y,p));m=LogisticRegression(C=1e6,max_iter=2000).fit(np.log(p/(1-p)).reshape(-1,1),y);r.update(calibration_intercept=float(m.intercept_[0]),calibration_slope=float(m.coef_[0,0]))
 order=np.argsort(-p,kind='stable')
 for q in [.25,.5,.75,1.]:r[f'risk_at_{q}']=float(1-y[order[:max(1,int(len(y)*q))]].mean())
 return r
def probability(pack,X):
 if pack['constant'] is not None:return np.full(len(X),pack['constant'])
 p=pack['base'].predict_proba(X[pack['columns']])[:,1]
 if pack['calibrator'] is not None:p=pack['calibrator'].predict_proba(np.log(np.clip(p,1e-8,1-1e-8)/(1-np.clip(p,1e-8,1-1e-8))).reshape(-1,1))[:,1]
 return p
def fit(train,columns):
 y=train.correct_5deg.astype(int);pack={'columns':columns,'base':None,'calibrator':None,'constant':None,'calibration_status':'not_applied'}
 if not columns or y.nunique()<2:pack.update(constant=float(y.mean()),calibration_status='training prevalence or one class');return pack
 groups=train.station_group;split=GroupShuffleSplit(n_splits=1,test_size=.2,random_state=20261010);a,b=next(split.split(train,y,groups));fitting=train.iloc[a];cal=train.iloc[b]
 if fitting.correct_5deg.nunique()<2:fitting=train;cal=train.iloc[:0];pack['calibration_status']='insufficient classes; no held-group calibration'
 pack['base']=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),LogisticRegression(C=1,max_iter=2000,class_weight=None)).fit(fitting[columns],fitting.correct_5deg.astype(int))
 if len(cal) and cal.correct_5deg.nunique()==2:
  p=np.clip(pack['base'].predict_proba(cal[columns])[:,1],1e-8,1-1e-8);pack['calibrator']=LogisticRegression(C=1e6,max_iter=2000).fit(np.log(p/(1-p)).reshape(-1,1),cal.correct_5deg.astype(int));pack['calibration_status']='sigmoid on held-out TRAINING stations'
 else:pack['calibration_status']='uncalibrated: calibration classes unavailable'
 pack['training_groups']=sorted(fitting.station_group.unique().tolist());pack['calibration_groups']=sorted(cal.station_group.unique().tolist());return pack
def main():
 start=time.time();files=sorted((J/'LABELS').glob('*.csv.gz'));assert len(files)==1050;data=pd.concat([pd.read_csv(f) for f in files],ignore_index=True);assert not data.duplicated(['case','drift','seed','time_index']).any();D=[x for x in data if x.startswith('D')];P=[x for x in data if x.startswith('P')];K=[x for x in data if x.startswith('K_')];groups={'prevalence':[],'distance':['K_distance'],'distance_slope':['K_distance','K_slope_per_rad'],'D':D,'P':P,'DP':D+P,'DPK':D+P+K};assert not any('truth' in x or 'error' in x or 'correct' in x for c in groups.values() for x in c);rows=[];preds=[];correlations=[];paired=[]
 for route in ['R2','R4','R5']:
  train=data[(data.route!=route)&data.available];test=data[(data.route==route)&data.available];out=test[['case','route','pose_id','station_group','drift','seed','time_index','t_s','correct_5deg','heading_error_deg']].copy()
  assert set(train.station_group).isdisjoint(test.station_group)
  for name,cols in groups.items():
   pack=fit(train,cols);pack.update(held_out_route=route,model_group=name);p=probability(pack,test);out['q_'+name]=p;r=metrics(test.correct_5deg,p);r.update(route=route,model=name,total_rows=int((data.route==route).sum()),available_rows=len(test),availability=float(data[data.route==route].available.mean()),calibration_status=pack['calibration_status']);rows.append(r)
   with (OUT/f'{route}_{name}.pkl').open('wb') as f:pickle.dump(pack,f)
   print('model',route,name,'n',len(test),'brier',r['brier'],flush=True)
  # Paired cluster bootstrap: station is unit, not time sample or seed.
  st=out.assign(delta_dp_d=(out.q_DP-out.correct_5deg.astype(int))**2-(out.q_D-out.correct_5deg.astype(int))**2,delta_dpk_distance=(out.q_DPK-out.correct_5deg.astype(int))**2-(out.q_distance-out.correct_5deg.astype(int))**2).groupby('station_group').agg(n=('seed','size'),dp=('delta_dp_d','sum'),dpk=('delta_dpk_distance','sum'));rng=np.random.default_rng(20261010);idx=rng.integers(0,len(st),(1000,len(st)));den=st.n.to_numpy()[idx].sum(axis=1)
  for col,contrast in [('dp','DP minus D Brier'),('dpk','DPK minus distance Brier')]:values=st[col].to_numpy()[idx].sum(axis=1)/den;paired.append({'route':route,'contrast':contrast,'station_groups':len(st),'bootstrap_replicates':1000,'mean_difference':float(st[col].sum()/st.n.sum()),'ci_low':float(np.quantile(values,.025)),'ci_high':float(np.quantile(values,.975))})
  for col in D+P+K:
   a=test[[col,'heading_error_deg','station_group']].replace([np.inf,-np.inf],np.nan).dropna();station=a.groupby('station_group')[[col,'heading_error_deg']].mean();correlations.append({'route':route,'feature':col,'pearson_sample_descriptive':a[col].corr(a.heading_error_deg),'spearman_sample_descriptive':a[col].corr(a.heading_error_deg,method='spearman'),'pearson_station_means':station[col].corr(station.heading_error_deg),'spearman_station_means':station[col].corr(station.heading_error_deg,method='spearman'),'n_station':len(station)})
  out.to_csv(OUT/f'{route}_HELD_OUT_PREDICTIONS.csv.gz',index=False);preds.append(out)
 pd.DataFrame(rows).to_csv(OUT/'METRICS.csv',index=False);pd.DataFrame(paired).to_csv(OUT/'PAIRED_STATION_BOOTSTRAP.csv',index=False);pd.DataFrame(correlations).to_csv(OUT/'CORRELATIONS.csv',index=False);bins=[]
 for route in ['R2','R4','R5']:
  test=data[(data.route==route)&data.available]
  for col in D+P+K:
   x=test[col].replace([np.inf,-np.inf],np.nan);b=pd.qcut(x,10,duplicates='drop');g=test.assign(bin=b).groupby('bin',observed=True)
   for k,v in g:bins.append({'route':route,'feature':col,'bin':str(k),'n':len(v),'correct_fraction':v.correct_5deg.mean(),'mean_heading_error_deg':v.heading_error_deg.mean()})
 pd.DataFrame(bins).to_csv(OUT/'FEATURE_BINS.csv',index=False);(OUT/'STATUS.json').write_text(json.dumps({'state':'completed','rows':len(data),'available_rows':int(data.available.sum()),'folds':3,'models':len(rows),'seconds':time.time()-start,'split':'leave one ROUTE out; sigmoid calibration uses training station groups only','same_corridor_only':True,'features':groups,'phase_not_used':True,'truth_not_used_for_inference':True},indent=2));print('completed reliability',time.time()-start,flush=True)
if __name__=='__main__':main()

