"""Fixed no-tuning route-heldout conditional error SECOND-MOMENT regression.
No testing labels enter training or inference. Channel label is never a predictor.
"""
from __future__ import annotations
import json,pickle
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score,roc_auc_score
from features import GROUPS,FEATURES
from common import OUT,AUDIT,write_json,sha,require_gate
R0S=.0081

def split_masks(data,route,tolerance=1e-4):
 te=data.route.to_numpy()==route
 xy=data[['x_eval','y_eval']].to_numpy()
 distance=cKDTree(xy[te]).query(xy,k=1)[0]
 tr=(~te)&(distance>tolerance)
 return tr,te,distance

def site_weights(data):
 keys=list(zip(data.x_eval.round(5),data.y_eval.round(5)))
 counts=pd.Series(keys).value_counts()
 return np.array([1/counts[k] for k in keys],float)

def predictor_table(data,cols):
 if any(c not in FEATURES for c in cols):raise ValueError('ORACLE_OR_UNKNOWN_PREDICTOR')
 arr=data[cols].to_numpy(float)
 if not np.isfinite(arr).all():raise ValueError('NONFINITE_PREDICTOR_REQUIRES_EXPLICIT_POLICY')
 return arr

def fit_train(data,train_mask,cols):
 tr=data.loc[train_mask]
 x=predictor_table(tr,cols);y=tr.e_total_eval.to_numpy()**2
 w=site_weights(tr)
 model=RandomForestRegressor(n_estimators=160,max_depth=6,min_samples_leaf=40,
                             random_state=20261015,n_jobs=2)
 model.fit(x,y,sample_weight=w)
 # Deterministic inference: threaded tree accumulation changes last-bit sums.
 model.n_jobs=1
 return model

def scores(e,r,w):
 r=np.maximum(np.asarray(r),1e-12);e=np.asarray(e);q=e**2
 return {'N':len(e),'MSE_actual':float(np.average(q,weights=w)),
  'R_mean':float(np.average(r,weights=w)),
  'Gaussian_NLL':float(np.average(.5*(np.log(2*np.pi*r)+q/r),weights=w)),
  'normalized_error2_mean':float(np.average(q/r,weights=w)),
  'error95_coverage':float(np.average(q<=3.841458820694124*r,weights=w)),
  'e2_R2':float(r2_score(q,r,sample_weight=w))}

def run(selected_route=None):
 require_gate('B')
 afinal=json.loads((OUT/'A_FINAL.json').read_text());assert afinal['status']=='EXTRACTION_AND_PARITY_PASS'
 assert sha(OUT/'A_FEATURES_LABELS.csv.gz')==afinal['feature_file_sha256']
 data=pd.read_csv(OUT/'A_FEATURES_LABELS.csv.gz')
 allpred=[];rows=[];splits=[];calbins=[]
 for route in ([selected_route] if selected_route else ('R2','R4','R5')):
  tr,te,dist=split_masks(data,route)
  assert not (tr&te).any() and np.min(dist[tr])>1e-4
  assert len(set(data.loc[tr,'route']) & {route})==0
  assert tr.sum()>100 and te.sum()>100
  test=data.loc[te].copy();w=site_weights(data.loc[tr]);y=data.loc[tr,'e_total_eval'].to_numpy()**2
  const=float(np.average(y,weights=w))
  split={'route':route,'train_rows':int(tr.sum()),'test_rows':int(te.sum()),'coincident_train_removed':int(((~te)&(~tr)).sum()),
    'min_train_test_distance_m':float(dist[tr].min()),'train_routes':sorted(data.loc[tr,'route'].unique().tolist()),
    'test_keys_sha256':__import__('hashlib').sha256(test[['case','channel','pose_id']].to_csv(index=False).encode()).hexdigest()}
  splits.append(split)
  for group in ['R0','CONST']+list(GROUPS):
   model=None
   if group=='R0':pred=np.full(te.sum(),R0S)
   elif group=='CONST':pred=np.full(te.sum(),const)
   else:
    cols=GROUPS[group];path=OUT/'models'/f'{route}_{group}.pkl'
    if path.exists():
     with open(path,'rb') as f: prior=pickle.load(f)
     assert prior['train_source']==afinal['feature_file_sha256'] and prior['features']==cols
     assert prior['heldout_route']==route and prior['split']==split
     model=prior['model'];params=model.get_params()
     assert params['n_estimators']==160 and params['max_depth']==6 and params['min_samples_leaf']==40 and params['random_state']==20261015
     assert model.n_jobs==1
    else:
     model=fit_train(data,tr,cols);path.parent.mkdir(exist_ok=True)
     with open(path,'wb') as f:
      pickle.dump({'model':model,'features':cols,'heldout_route':route,'split':split,'train_source':afinal['feature_file_sha256']},f)
    pred=model.predict(predictor_table(test,cols))
   assert np.isfinite(pred).all() and np.all(pred>=0)
   effective=np.clip(pred,R0S,100*R0S)
   p=test[['case','channel','pose_id','route','x_eval','y_eval','e_total_eval','e_MP_eval']].copy()
   p['group']=group;p['R_pred_raw']=pred;p['R_eff']=effective;allpred.append(p)
   for channel in ('los','full'):
    sub=test.channel.to_numpy()==channel;ww=site_weights(test.loc[sub]);ee=test.loc[sub,'e_total_eval'].to_numpy()
    for usage,rr in [('raw_second_moment',pred[sub]),('bounded_inflation',effective[sub])]:
     met=scores(ee,rr,ww)
     row={'heldout_route':route,'channel':channel,'group':group,'usage':usage,**met}
     bad=abs(test.loc[sub,'e_MP_eval'].to_numpy())>.1
     row['MP_risk_AUROC']=float(roc_auc_score(bad,rr,sample_weight=ww)) if len(set(bad))==2 else None
     rows.append(row)
   # Calibration bins are TEST readout only; never used for model fitting.
   order=np.argsort(pred)
   for ib,idx in enumerate(np.array_split(order,10)):
    if len(idx):
     calbins.append({'route':route,'group':group,'decile':ib,'n':len(idx),
        'predicted_second_moment':float(np.mean(pred[idx])),
        'actual_second_moment':float(np.mean(test.e_total_eval.to_numpy()[idx]**2))})
   print('B_FOLD',route,group,int(tr.sum()),int(te.sum()),flush=True)
 pred=pd.concat(allpred,ignore_index=True)
 expected=len(data) if selected_route is None else int((data.route==selected_route).sum())
 assert len(pred)==expected*8 and not pred.duplicated(['case','channel','pose_id','group']).any()
 if selected_route:
  folder=OUT/'B_PARTS';folder.mkdir(exist_ok=True)
  pred.to_csv(folder/f'{selected_route}_pred.csv.gz',index=False)
  pd.DataFrame(rows).to_csv(folder/f'{selected_route}_metrics.csv',index=False)
  pd.DataFrame(calbins).to_csv(folder/f'{selected_route}_bins.csv',index=False)
  write_json(folder/f'{selected_route}_split.json',splits)
  print('B_ROUTE_SAVED',selected_route,flush=True)
  return
 pred.to_csv(OUT/'B_OOF_PREDICTIONS.csv.gz',index=False)
 pd.DataFrame(rows).to_csv(OUT/'B_METRICS.csv',index=False)
 pd.DataFrame(calbins).to_csv(OUT/'B_CALIBRATION_BINS.csv',index=False)
 write_json(OUT/'B_SPLITS.json',splits)
 write_json(OUT/'B_FINAL.json',{'status':'HELDOUT_EVALUATION_COMPLETE','rows':len(data),'prediction_rows':len(pred),
  'models':18,'outer_folds':3,'predictor_whitelist':GROUPS,'no_heldout_tuning':True,
  'calibration_PASS':'NOT_ASSERTED','scientific_PASS':False,'predictions_sha256':sha(OUT/'B_OOF_PREDICTIONS.csv.gz'),
  'limitations':['one corridor','noise-free RF','second moment not centered variance','colored error unmodeled','C remains exploratory']})
if __name__=='__main__':
 import sys
 run(sys.argv[1] if len(sys.argv)>1 else None)
