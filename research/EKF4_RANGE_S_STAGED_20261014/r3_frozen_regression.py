"""R3 fixed archived numerical failure regression (no synthetic trial rerun).

Audit source and archive before running. Verify original gradient threshold
and same Gaussian joint likelihood, and preserve old failures as old failures.
"""
import argparse,hashlib,io,json,os,traceback,zipfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from core import SyntheticRF,map_update
from pre_run_audit import require_audit_receipt
from r3_archive_audit import CASES,SHA,base,sha

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--source-audit',type=Path,required=True)
 p.add_argument('--input-audit',type=Path,required=True)
 p.add_argument('--archive',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args()
 require_audit_receipt(a.source_audit)
 rec=json.loads(a.input_audit.read_text())
 if rec.get('decision')!='GO' or rec.get('git_sha')!=os.getenv('GITHUB_SHA'):
  raise RuntimeError('frozen four source/input receipt HOLD')
 if sha(a.archive.read_bytes())!=SHA:raise RuntimeError('modified archived P2 data')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 rows=[];rc=1;status='FAIL'
 try:
  with zipfile.ZipFile(a.archive) as z:
   for route,model,k,expected in CASES:
    blob=z.read(base(route,model)+'FAILED_STEP.npz')
    if sha(blob)!=expected:raise RuntimeError('frozen input checksum mismatch')
    with np.load(io.BytesIO(blob),allow_pickle=False) as ff:
     mu,P,obs,R=[np.asarray(ff[x]).copy() for x in ('prior_x','prior_P','z','R')]
     delta=np.asarray(ff['prior_delta']).copy()
    for warm in ('saved','range_first'):
     kwargs=({'range_first':False,'initial_delta':delta} if warm=='saved' else {'range_first':True})
     result=map_update(mu,P,obs,SyntheticRF(),R,max_iter=80,gradient_tol=1e-8,**kwargs)
     Lp=np.linalg.cholesky(P);Lr=np.linalg.cholesky(R)
     y=np.linalg.solve(Lp,result.prior_delta)
     h,H=SyntheticRF()(mu+result.prior_delta)
     v=np.linalg.solve(Lr,obs-h);B=np.linalg.solve(Lr,H@Lp)
     grad=y-B.T@v
     gn=float(np.linalg.norm(grad,ord=np.inf))
     cost=.5*float(y@y+v@v)
     ok=(result.status=='CONVERGED' and gn<=1e-8
         and abs(result.cost-cost)<1e-11
         and float(np.linalg.eigvalsh(result.P)[0])>0)
     row={'route':route,'model':model,'step':k,'warm_start':warm,
          'status':result.status,'gradient_inf':gn,
          'reported_gradient':result.gradient_inf,
          'objective':result.cost,'independent_objective':cost,
          'iterations':result.iterations,
          'last_step_methods':[x.get('step_acceptance') for x in result.history[-4:]],
          'regression_pass':bool(ok)}
     rows.append(row)
     print('R3_CASE '+json.dumps(row),flush=True)
     if not ok:raise RuntimeError('R3 original-gradient regression failed: '+str(row))
  status='PASS';rc=0
 except Exception as e:
  (out/'TRACEBACK.log').write_text(traceback.format_exc())
  status='FAIL_'+type(e).__name__
 result={'stage':'R3_FIXED_FOUR_REGRESSION','status':status,
   'git_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
   'numeric_gradient_original_tolerance':1e-8,
   'source_audit_sha256':sha(a.source_audit.read_bytes()),'input_audit_sha256':sha(a.input_audit.read_bytes()),
   'cases':rows,'total_tests':len(rows),'passed':sum(x['regression_pass'] for x in rows),
   'scientific_PASS':False,'P2_FULL':'NOT_RUN','P3_P6':'NOT_RUN',
   'end_utc':datetime.now(timezone.utc).isoformat(),'exit_code':rc}
 (out/'FINAL.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print('R3_FINAL '+json.dumps({k:result[k] for k in ('status','total_tests','passed','exit_code')}),flush=True)
 return rc
if __name__=='__main__':raise SystemExit(main())
