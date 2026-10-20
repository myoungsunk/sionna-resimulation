"""Route-grouped HGB OOF on fixed nested labels, selected-action 80% margins."""
import argparse,traceback,zipfile,platform,time
from concurrent.futures import ThreadPoolExecutor
from common import *
from sklearn.ensemble import HistGradientBoostingRegressor
import sklearn
sys.path.insert(0,str(HERE.parent/'S0_CORRECTIONS'))
from github_io import session as raw_session,api,download
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
def session():
 s=raw_session();s.mount('https://',HTTPAdapter(max_retries=Retry(total=3,connect=3,read=3,backoff_factor=1,status_forcelist=[502,503,504],allowed_methods=['GET','HEAD'])))
 return s
def shards(df,out,stem,n=10000):
 for j,i in enumerate(range(0,len(df),n)):df.iloc[i:i+n].to_csv(out/f'{stem}_{j:03}.csv',index=False)
def get_artifacts(run):
 s=session();items=[];page=1
 while True:
  part=api(s,f'actions/runs/{run}/artifacts',params=dict(per_page=100,page=page))['artifacts'];items+=part
  if len(part)<100:break
  page+=1
 return items
def restore_artifact(item,out):
 out.mkdir(parents=True,exist_ok=True);path=out/(str(item['id'])+'.zip');s=session()
 got,n=download(s,item['archive_download_url'],path);assert n==item['size_in_bytes'];expected=item.get('digest');assert not expected or expected=='sha256:'+got,('ARTIFACT_DIGEST',item['id'])
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for name in z.namelist():
   if name.endswith('/'):continue
   target=(out/name).resolve();assert target.is_relative_to(out.resolve()),'ZIP_PATH'
  z.extractall(out)
 return dict(artifact_id=item['id'],name=item['name'],sha256=got,bytes=n,run_id=item['workflow_run']['id'] if item.get('workflow_run') else None,github_digest=expected)
def main():
 p=argparse.ArgumentParser();p.add_argument('--labels-run',type=int,required=True);p.add_argument('--wait',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);errors=[];checks=[]
 try:
  lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text())
  if a.wait:
   started=time.monotonic();s=session()
   while True:
    run=api(s,f'actions/runs/{a.labels_run}')
    if run['status']=='completed':
     assert run['conclusion']=='success',('LABEL_RUN_NOT_SUCCESS',run['conclusion']);break
    assert time.monotonic()-started<18000,'LABEL_WAIT_TIMEOUT'
    print('WAIT_LOCKED_LABEL_RUN',a.labels_run,run['status'],flush=True);time.sleep(30)
  items=[x for x in get_artifacts(a.labels_run) if x['name'].startswith('powerjoint-s3-label-')];assert len(items)==105,('LABEL_ARTIFACT_COUNT',len(items))
  cache=a.out.parent/'label_inputs';cache.mkdir(exist_ok=True)
  with ThreadPoolExecutor(max_workers=6) as pool:receipts=list(pool.map(lambda item:restore_artifact(item,cache/str(item['id'])),items))
  dump(a.out/'LABEL_ARTIFACT_RECEIPT.json',receipts)
  frames=[];summaries=[];p1hash={}
  for directory in sorted(cache.iterdir()):
   man=next(directory.rglob('MANIFEST.json'));m=json.loads(man.read_text());assert m['stage']=='labels' and m['technical']=='TECHNICAL_PASS' and m['protocol_sha256']==sha(HERE/'PROTOCOL_LOCK.json'),('LABEL_SHARD_NOT_PASS',m)
   for rel,want in m['outputs'].items():assert sha(man.parent/rel)==want,('LABEL_OUTPUT_SHA',rel)
   pieces=list(man.parent.glob('UTILITY_LABELS_*.csv'));assert len(pieces)==4
   df=pd.concat([pd.read_csv(x) for x in pieces],ignore_index=True);assert len(df)==m['n_valid']
   index=pd.read_csv(HERE/f"LABEL_PACKET_INDEX_{m['outer']}_{m['case']}.csv");wanted=index[(index.seed==m['seed'])&(index.status=='INCLUDED')]
   keys=['outer','case','bias','seed','frame','pose_id','horizon_samples'];assert set(map(tuple,df[keys].values))==set(map(tuple,wanted[keys].values)) and len(df)==len(wanted),'LOCKED_LABEL_KEYS'
   assert (df.power_restart_state_max<=1e-10).all() and (df.power_restart_cov_max<=1e-10).all() and (df.power_restart_gate_mismatch==0).all(),'RESTART_QA'
   assert np.isfinite(df[FEATURES+['utility_'+x for x in ACTIONS]].to_numpy()).all(),'LABEL_NONFINITE'
   fit=json.loads((man.parent/'P1_MODEL.json').read_text());k=(fit['outer'],fit['inner_route']);p1hash.setdefault(k,fit['model']['sha256']);assert p1hash[k]==fit['model']['sha256'],'DUPLICATE_P1_FIT_DIFF'
   frames.append(df);summaries.append(dict(outer=m['outer'],case=m['case'],seed=m['seed'],rows=len(df),artifact_id=int(directory.name)))
  labels=pd.concat(frames,ignore_index=True);assert len(labels)==sum(x['included'] for x in lock['label_shards']);assert not labels.duplicated(['outer','case','bias','seed','frame']).any()
  pd.DataFrame(summaries).to_csv(a.out/'LABELS_SUMMARY.csv',index=False)
  models=dict(feature_names=FEATURES,actions=NONPOWER,runtime=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__),protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),models={});margins={};oof_rows=[]
  for outer in ['R2','R4','R5','ALL_OLD']:
   df=labels[labels.outer==outer].reset_index(drop=True);groups=sorted(set(df.inner_route));assert outer not in groups
   pred=np.full((len(df),3),np.nan);fold_models=[]
   for held in groups:
    tr=df.inner_route!=held;va=~tr;assert tr.any() and va.any()
    for j,action in enumerate(NONPOWER):
     est=HistGradientBoostingRegressor(**lock['learner']).fit(df.loc[tr,FEATURES].to_numpy(),df.loc[tr,'utility_'+action].to_numpy());pred[va,j]=est.predict(df.loc[va,FEATURES].to_numpy());fold_models.append(dict(validation_route=held,action=action,n_train=int(tr.sum()),n_validation=int(va.sum()),training_routes=sorted(set(df.loc[tr,'inner_route'])),model=serialize(est)))
   assert np.isfinite(pred).all();selected=np.argmax(pred,axis=1);actual=df[['utility_'+x for x in NONPOWER]].to_numpy();margins[outer]={}
   oof=df[['outer','inner_route','case','bias','seed','pose_id','frame','t_s','p1_model_sha256']].copy();oof['selected_unadjusted_action']=np.array(NONPOWER)[selected]
   for j,action in enumerate(NONPOWER):
    sel=selected==j;error=np.maximum(0,pred[sel,j]-actual[sel,j]);delta=float(np.quantile(error,.8,method='linear')) if sel.any() else None
    margins[outer][action]=dict(delta=delta,n_selected=int(sel.sum()),status='CALIBRATED_SELECTED_OOF' if sel.any() else 'UNCALIBRATED_NO_OOF_SELECTION',enabled_v3=bool(sel.any()))
    oof['predicted_'+action]=pred[:,j];oof['actual_'+action]=actual[:,j];oof['overprediction_'+action]=np.maximum(0,pred[:,j]-actual[:,j])
   shards(oof,a.out,'OOF_PREDICTIONS_'+outer)
   final=[]
   for action in NONPOWER:
    est=HistGradientBoostingRegressor(**lock['learner']).fit(df[FEATURES].to_numpy(),df['utility_'+action].to_numpy());rec=serialize(est);reload=deserialize(rec);before=est.predict(df[FEATURES].to_numpy());after=reload.predict(df[FEATURES].to_numpy());assert np.array_equal(before,after),'MODEL_RELOAD';final.append(rec)
   dump(a.out/f'MODELS_OOF_{outer}.json',dict(feature_names=FEATURES,runtime=models['runtime'],models=fold_models))
   models['models'][outer]=dict(n_train=len(df),training_routes=groups,estimators=final,oof_models_file=f'MODELS_OOF_{outer}.json',oof_models_sha256=sha(a.out/f'MODELS_OOF_{outer}.json'))
   checks.append(dict(check='OOF_ROUTE_GROUPS_AND_MODEL_RELOAD',outer=outer,rows=len(df),status='PASS',oof_scope=lock['oof_scope']))
   print('TRAIN_FOLD_DONE',outer,len(df),json.dumps(margins[outer]),flush=True)
  dump(a.out/'MODELS.json',models);dump(a.out/'MARGINS.json',dict(protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),quantile=.8,method='linear',scope=lock['oof_scope'],margins=margins));pd.DataFrame(checks).to_csv(a.out/'CHECKS.csv',index=False)
 except Exception as e:errors.append(dict(error=str(e),traceback=traceback.format_exc(),retry=False))
 manifest(a.out,'train',errors,labels_run=a.labels_run)
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
