"""Additive batch runner; identical preregistered tasks/arms, no filter changes."""
import argparse,json,time,concurrent.futures,hashlib,traceback
import pandas as pd
import body_controls as C

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch',choices=['existing7','new5'],required=True);a=p.parse_args()
 allcases=[f'{r}_{anc}_m{m}' for r in ['R2','R4','R5'] for anc in ['aA','aB'] for m in [0,45]]
 existing={x['case'] for x in json.loads((C.B/'CASES.json').read_text())}
 cases=[x for x in allcases if (x in existing)==(a.batch=='existing7')]
 if a.batch=='new5':assert json.loads((C.J/'NATIVE_FULL_STATUS.json').read_text())['state']=='COMPLETED'
 tasks=[(case,gi,d,s,snr) for case in cases for gi in range(len(C.casepack(case)[3])) for d in range(3) for s in range(5) for snr in [30,10]]
 C.OUT.mkdir(exist_ok=True)
 plan=C.J/f'BODY_TASKS_{a.batch}.json';assert not plan.exists();plan.write_text(json.dumps({'tasks':tasks,'sample_unit':'sensor seed within station; time samples not independent','source_sha256':{x.name:sha(x) for x in C.J.glob('*.py')},'prereg_sha256':sha(C.J/'BODY_CONTROL_PREREG.json'),'lut_sha256':sha(C.L/'hs_lut_2deg.npy'),'metadata_sha256':sha(C.L/'hs_lut_meta.json'),'freq_sha256':sha(C.B/'freqs_hz.npy'),'scope':'same prereg; batch existing inputs first while new RF completes'},indent=2))
 start=time.time();rows=[]
 try:
  with concurrent.futures.ProcessPoolExecutor(max_workers=24) as ex:
   for i,out in enumerate(ex.map(C.one,tasks,chunksize=3)):
    rows.extend(out)
    if i%100==0:print(a.batch,i,len(tasks),flush=True)
  df=pd.DataFrame(rows);df.to_csv(C.J/f'10_PAIRED_FILTER_RESULTS_{a.batch}.csv',index=False)
  status={'state':'COMPLETED' if not (df.status=='FAILED').any() else 'PARTIAL_FAILED','tasks':len(tasks),'executed_runs':int((df.status!='NO_EVALUATION_PRIOR').sum()),'missing_prior_tasks':int((df.status=='NO_EVALUATION_PRIOR').sum()),'failure_runs':int((df.status=='FAILED').sum()),'seconds':time.time()-start,'G3_alias_of_D':True,'mode':C.P['mode'],'scientific_PASS':False}
 except BaseException as e:
  pd.DataFrame(rows).to_csv(C.J/f'10_PAIRED_FILTER_RESULTS_{a.batch}_PARTIAL.csv',index=False);status={'state':'FAILED','error':str(e),'traceback':traceback.format_exc(),'seconds':time.time()-start,'scientific_PASS':False}
  (C.J/f'BODY_CONTROL_STATUS_{a.batch}.json').write_text(json.dumps(status,indent=2));raise
 (C.J/f'BODY_CONTROL_STATUS_{a.batch}.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
