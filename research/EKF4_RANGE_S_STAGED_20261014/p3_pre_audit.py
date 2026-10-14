"""P3 read-only source and frozen RF manifest audit, before numerical tests."""
import ast
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/'research/EKF3_INDEPENDENT_20261013'
EXPECTED={
  'P0_INPUT_MANIFEST.json':'8bf216cf606f5e3c11139cacbf42f15a44556feb',
  'p0_verify_inputs.py':'507e0f6588d6cddcc358c630c538770ccbaaedbc'
}
# Git blob SHA1, not content SHA256.
def gitblob(b):
 return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\x00'+b).hexdigest()

def main():
 if os.environ.get('GITHUB_ACTIONS')!='true':
  raise RuntimeError('GitHub Actions required')
 errors=[]
 for name,expect in EXPECTED.items():
  f=DIR/name
  if not f.is_file():
   errors.append({'missing':name});continue
  if gitblob(f.read_bytes())!=expect:
   errors.append({'blob_mismatch':name})
 if not errors:
  spec=json.loads((DIR/'P0_INPUT_MANIFEST.json').read_text())
  if len(spec.get('assets',[]))!=39 or len(spec.get('cases',[]))!=7:
   errors.append({'frozen_shape_contract':'39 assets and 7 cases'})
  if spec['physical_contract'].get('state')!=['x_m','y_m','yaw_rad']:
   errors.append({'state_contract_changed':True})
  observer=spec['physical_contract'].get('observer','')
  if 'Hann' not in observer or 's=(P1-P2)/(P1+P2)' not in observer:
   errors.append({'observer_contract_changed':True})
  ast.parse((DIR/'p0_verify_inputs.py').read_text())
 workflow=(ROOT/'.github/workflows/ekf4-p3-rf-input.yml').read_text()
 ix=workflow.find('p3_pre_audit.py')
 iy=workflow.find('p0_verify_inputs.py')
 if not (0<=ix<iy):errors.append({'execution_audit_order':False})
 receipt={'stage':'P3_RF_INPUT','run_id':os.environ.get('GITHUB_RUN_ID'),
  'git_sha':os.environ.get('GITHUB_SHA'),'decision':'GO' if not errors else 'HOLD',
  'errors':errors,'scientific_PASS':False,'independent_audit':False,
  'check_scope':'frozen provenance/source and P0 input parity, not RF performance'}
 Path(os.environ['RUNNER_TEMP'],'P3_PREAUDIT.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('P3_PREAUDIT '+json.dumps(receipt),flush=True)
 return 0 if not errors else 2

if __name__=='__main__':
 raise SystemExit(main())
