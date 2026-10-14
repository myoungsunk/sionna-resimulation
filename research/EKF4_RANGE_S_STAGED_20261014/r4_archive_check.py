"""R4 numerical-only replay of all sixteen immutable R3 full-P2 failure inputs.

Run ONLY in GitHub Actions after source-bound PRE_RUN_AUDIT.
It must not produce scientific performance ranking or edit original data.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import traceback
import zipfile

import numpy as np
from core import map_update, SyntheticRF
from pre_run_audit import require_audit_receipt

ORIGINAL_ARTIFACT_SHA="f80f9f749da08e3abd9c14e2e0241ba956cd4cae3f9935ec7815a966a39d60bd"
ORIGINAL_RUN=38538726484
ORIGINAL_COMMIT="94a14b1a62dd360dff72c8852d0011bf11edaea2"

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):
   h.update(b)
 return h.hexdigest()

def save(path,data):
 Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--audit',type=Path,required=True)
 ap.add_argument('--artifact',type=Path,required=True)
 ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args()
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 audit=require_audit_receipt(a.audit)
 out=a.out.resolve()
 out.mkdir(parents=True,exist_ok=False)
 result={'stage':'R4_SNAPSHOT_REGRESSION','original_run':ORIGINAL_RUN,
         'original_commit':ORIGINAL_COMMIT,
         'git_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
         'expected_cases':16,'cases':[],'scientific_PASS':False,
         'P2_FULL':'NOT_RUN_IN_THIS_RUNNER','status':'STARTED'}
 try:
  if sha(a.artifact)!=ORIGINAL_ARTIFACT_SHA:
   raise RuntimeError('R3 archived ZIP SHA256 mismatch')
  with zipfile.ZipFile(a.artifact) as z:
   if z.testzip() is not None: raise RuntimeError('Archive CRC mismatch')
   finals=[p for p in z.namelist() if p.endswith('/p2_full/FINAL.json')]
   if len(finals)!=1:raise RuntimeError('R3 final manifest not unique')
   manifest=json.loads(z.read(finals[0]))
   if not(manifest['run_id']==str(ORIGINAL_RUN) and manifest['commit']==ORIGINAL_COMMIT
          and manifest['invalid_model_cases']==16):
    raise RuntimeError('R3 original run/provenance mismatch')
   roots=[x for x in z.namelist() if x.endswith('/FAILED_STEP.npz') and '/p2_full/' in x]
   if len(roots)!=16:raise RuntimeError('Original failure set count mismatch')
   for p in sorted(roots):
    f=json.loads(z.read(p.replace('FAILED_STEP.npz','FAILURE.json')))
    with np.load(io.BytesIO(z.read(p)),allow_pickle=False) as n:
     x,P,zobs,R=[np.array(n[q],dtype=float) for q in ('prior_x','prior_P','z','R')]
    fit=map_update(x,P,zobs,SyntheticRF(),R,max_iter=80,gradient_tol=1e-8)
    row={'path':p,'model':f['model'],'route':f['cell']['path'],
         'bias':f['cell']['true_bias_dps'],'trial':f['cell']['trial'],
         'original_failure':f['solver_status'],
         'original_gradient_inf':f['gradient_inf'],
         'updated_status':fit.status,'updated_gradient_inf':fit.gradient_inf,
         'iterations':fit.iterations,
         'status_valid':fit.status=='CONVERGED' and fit.gradient_inf<=1e-8,
         'p_symmetry':bool(np.allclose(fit.P,fit.P.T,atol=1e-12,rtol=1e-12)),
         'p_min_eigenvalue':float(np.linalg.eigvalsh(fit.P)[0]),
         'last_step_method':fit.history[-2].get('step_acceptance') if len(fit.history)>1 else None}
    result['cases'].append(row)
    print('R4_CASE '+json.dumps({k:row[k] for k in ('route','bias','trial','model','original_gradient_inf','updated_status','updated_gradient_inf','iterations','last_step_method')}),flush=True)
  count=sum(c['status_valid'] and c['p_min_eigenvalue']>0 and c['p_symmetry'] for c in result['cases'])
  result['passed_cases']=count
  result['status']='R4_FIXED_INPUT_PASS' if count==16 else 'R4_FIXED_INPUT_INCOMPLETE'
  result['exit_code']=0 if count==16 else 3
 except Exception:
  result['status']='R4_AUDIT_OR_TEST_ERROR'
  result['exit_code']=2
  result['traceback']=traceback.format_exc()
 save(out/'FINAL.json',result)
 print('R4_FINAL '+json.dumps({k:v for k,v in result.items() if k!='cases'},flush=True) if False else 'R4_FINAL '+json.dumps({k:v for k,v in result.items() if k!='cases'}),flush=True)
 return result['exit_code']

if __name__=='__main__':
 raise SystemExit(main())
