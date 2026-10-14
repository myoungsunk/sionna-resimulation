"""R3 archived four failure regression. GitHub runner only, after audit."""
import argparse, os, io, zipfile, json
from pathlib import Path
import numpy as np
from core import SyntheticRF,map_update
from d3_pre_audit import METADATA,path_for,ARTIFACT_SHA,sha
def main():
 q=argparse.ArgumentParser();q.add_argument('--artifact',required=True);q.add_argument('--audit',required=True);q.add_argument('--out',required=True);a=q.parse_args()
 from pre_run_audit import require_audit_receipt
 require_audit_receipt(a.audit)
 if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('cloud only')
 if sha(Path(a.artifact).read_bytes())!=ARTIFACT_SHA:raise RuntimeError('immutable artifact integrity')
 out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
 cases=[]
 with zipfile.ZipFile(a.artifact) as ar:
  for route,model,k,nsha,jsha in METADATA:
   if sha(ar.read(path_for(route,model,'FAILED_STEP.npz')))!=nsha:raise RuntimeError('fixture mismatch')
   with np.load(io.BytesIO(ar.read(path_for(route,model,'FAILED_STEP.npz')))) as z:
    mu,P,v,R=[z[x] for x in ('prior_x','prior_P','z','R')]
   result=map_update(mu,P,v,SyntheticRF(),R,range_first=True,max_iter=80,gradient_tol=1e-8)
   case={'route':route,'model':model,'step':k,'status':result.status,'gradient_inf':result.gradient_inf,'iterations':result.iterations,'history':result.history}
   cases.append(case)
   print('R3_CASE '+json.dumps({k:v for k,v in case.items() if k!='history'}))
 status='PASS' if len(cases)==4 and all(c['status']=='CONVERGED' and c['gradient_inf']<=1e-8 for c in cases) else 'FAIL'
 (out/'FINAL.json').write_text(json.dumps({'status':status,'source_sha':os.environ['GITHUB_SHA'],'cases':cases,'scientific_PASS':False},indent=2))
 return 0 if status=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
