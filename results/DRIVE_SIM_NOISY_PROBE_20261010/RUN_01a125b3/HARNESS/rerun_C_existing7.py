import json,time,concurrent.futures
import pandas as pd
import body_controls as C
C.OUT=C.J/'BODY_CONTROLS_C_CORRECTED'
def one(task):return C.one(tuple(task),arms=['C'])
if __name__=='__main__':
 C.OUT.mkdir(exist_ok=False);start=time.time();tasks=json.loads((C.J/'BODY_TASKS_existing7.json').read_text())['tasks'];rows=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=24) as ex:
  for result in ex.map(one,tasks,chunksize=3):rows.extend(result)
 df=pd.DataFrame(rows);df.to_csv(C.J/'10_PAIRED_FILTER_RESULTS_C_CORRECTED.csv',index=False);status={'state':'COMPLETED' if not (df.status=='FAILED').any() else 'PARTIAL_FAILED','completed_runs':int((df.status=='COMPLETED').sum()),'missing_prior_tasks':int((df.status=='NO_EVALUATION_PRIOR').sum()),'failed_runs':int((df.status=='FAILED').sum()),'seconds':time.time()-start,'change':'C retains full-RF range; only s is LoS. Pre-correction retained, not treated as specification C.'};(C.J/'C_CORRECTION_STATUS.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
