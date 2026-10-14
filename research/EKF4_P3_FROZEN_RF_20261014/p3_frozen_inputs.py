"""P3 scoped frozen RF source/input audit; no estimator or sensor outputs.

Run stdlib --stage audit BEFORE generating any RF checks; then expand sparse
checkout to exact manifest-listed files; run --stage verify after audit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime,timezone

REPO=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
MANIFEST=REPO/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
EXPECTED_BLOB="8bf216cf606f5e3c11139cacbf42f15a44556feb"
EXPECTED_COUNTS={'FULL_H':7,'LOS_H':7,'SAMPLES':7,'TIMELINE_TNONE':3,'FREQUENCY':1,'HS_LUT':1,'HS_LUT_META':1,'AUDITED_SOURCE':7,'SENSOR_CONFIG':1,'LINEAGE':4}

def sha256_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while True:
   b=f.read(1048576)
   if not b:break
   h.update(b)
 return h.hexdigest()

def manifest_ok():
 b=MANIFEST.read_bytes()
 blob_sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
 m=json.loads(b)
 counts={}
 for a in m['assets']:counts[a['kind']]=counts.get(a['kind'],0)+1
 okay=blob_sha==EXPECTED_BLOB and counts==EXPECTED_COUNTS and len(m['assets'])==39
 if not okay:
  raise RuntimeError('Frozen manifest integrity/type/shape mismatch')
 if any(Path(a['path']).is_absolute() or '..' in Path(a['path']).parts for a in m['assets']):
  raise RuntimeError('Unsafe asset path')
 return m,blob_sha

def write(out,mode,data):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 (out/(mode.upper()+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--stage',choices=['audit','verify'],required=True)
 ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--audit',type=Path)
 p=ap.parse_args()
 if os.getenv('GITHUB_ACTIONS')!='true':raise RuntimeError('P3 cloud-only scientific source verification')
 receipt={'schema':'EKF4_P3_FROZEN_INPUT_AUDIT','stage':p.stage,
 'run_id':os.getenv('GITHUB_RUN_ID'),'git_sha':os.getenv('GITHUB_SHA'),
 'utc':datetime.now(timezone.utc).isoformat(),'scientific_PASS':False,
 'P4_P6':'NOT_RUN','status':'HOLD','checks':[]}
 try:
  m,blob=manifest_ok()
  receipt['manifest_blob_sha']=blob
  receipt['assets_total']=len(m['assets'])
  receipt['decision']='Verify that the 39 original H/LoS/LUT/observer/sensor/timeline assets are bit-identical before a new RF fusion adapter is implemented.'
  script=Path(__file__)
  receipt['script_sha256']=sha256_file(script)
  if p.stage=='audit':
   workflow=REPO/'.github/workflows/ekf4-p3-frozen-rf.yml'
   s=workflow.read_text()
   idx=[s.index('p3_frozen_inputs.py --stage audit'),s.index('p3_frozen_inputs.py --stage verify')]
   if idx[0]>=idx[1]:raise RuntimeError('Source audit must precede numerical asset verifier')
   receipt['checks'].append({'id':'manifest_and_workflow_source','status':'PASS'})
   receipt['checks'].append({'id':'no_user_impersonation_or_truth_inference','status':'STATIC_SCOPE_ONLY'})
  else:
   audit=json.loads((p.audit/'AUDIT.json').read_text())
   if audit.get('status')!='GO' or audit.get('git_sha')!=os.getenv('GITHUB_SHA') or audit.get('script_sha256')!=sha256_file(script):
    raise RuntimeError('Pre-run audit or commit mismatch')
   import numpy as np
   for a in m['assets']:
    path=REPO/a['path']
    if not path.is_file(): raise RuntimeError('Missing RF file: '+a['path'])
    length=path.stat().st_size
    digest=sha256_file(path)
    # The frozen manifest records SHA256 for the 35 scientific inputs
    # and Git blob SHA1 only for four non-numerical LINEAGE artifacts.
    if length!=a['bytes']:
     raise RuntimeError('Frozen asset size mismatch: '+a['path'])
    if 'sha256' in a and digest!=a['sha256']:
     raise RuntimeError('Frozen asset SHA256 mismatch: '+a['path'])
    if 'sha256' not in a:
     b=path.read_bytes()
     blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\\0'+b).hexdigest()
     if blob!=a.get('git_blob_sha1'):
      raise RuntimeError('Frozen lineage blob SHA1 mismatch: '+a['path'])
    row={'path':a['path'],'kind':a['kind'],'bytes':length,'SHA256_computed':digest,
         'validation_hash_type':'SHA256' if 'sha256' in a else 'GIT_BLOB_SHA1','status':'PASS'}
    if path.suffix=='.npy':
     value=np.load(path,mmap_mode='r',allow_pickle=False)
     row['shape']=list(value.shape)
     if 'shape' in a and row['shape']!=a['shape']:
      raise RuntimeError('Frozen .npy shape mismatch: '+a['path'])
    receipt['checks'].append(row)
  receipt['status']='GO' if p.stage=='audit' else 'P3_INPUT_ELIGIBLE'
  receipt['scientific_PASS']=False
  rc=0
 except Exception as e:
  receipt['status']='HOLD' if p.stage=='audit' else 'P3_INPUT_INVALID'
  receipt['error_type']=type(e).__name__
  receipt['error']=str(e)
  rc=2
 receipt['exit_code']=rc
 receipt['completed_utc']=datetime.now(timezone.utc).isoformat()
 write(p.out,p.stage,receipt)
 print('P3_'+p.stage.upper()+' '+json.dumps({k:v for k,v in receipt.items() if k not in ('checks',)},ensure_ascii=False),flush=True)
 return rc

if __name__=='__main__':
 raise SystemExit(main())
