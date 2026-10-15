"""Audit before stage execution. Source review + exact hashes + negative/math tests.
This is a same-assistant implemented audit, not an independent third-party review.
"""
import ast,hashlib,json,sys,subprocess
from pathlib import Path
from common import ROOT,INPUT,OUT,AUDIT,sha,write_gate,write_json

def audit(stage):
 inputs=json.loads((INPUT/'BUNDLE_AUDIT.json').read_text())
 for row in inputs['files']:
  assert sha(INPUT/row['path'])==row['sha256'],('ORIGINAL_INPUT_CHANGED',row['path'])
 a=ast.parse((INPUT/'research/EKF4_RANGE_S_STAGED_20261014/r2_bias_audit.py').read_text())
 hashes=ast.literal_eval(next(n.value for n in a.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BASE' for t in n.targets)))
 for p,g in hashes.items():
  b=(INPUT/p).read_bytes();assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==g
 for filename,func in [('features.py','extract'),('stage_c.py','recursive_filter')]:
  tree=ast.parse((ROOT/'code'/filename).read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==func)
  forbidden={'truth','oracle','true_bias','e_total_eval','e_MP_eval','e_LUT_eval','lut_s_eval'}
  assert not any(isinstance(n,ast.Name) and n.id in forbidden for n in ast.walk(fn))
 # Validate B uses explicit training slice and predictor whitelist, never model.fit(test).
 b=(ROOT/'code/stage_b.py').read_text();assert 'tr=data.loc[train_mask]' in b and 'ORACLE_OR_UNKNOWN_PREDICTOR' in b
 attempt=len(list(AUDIT.glob(stage+'_TESTS_attempt_*.log')))+1
 tag=f'{stage}_TESTS_attempt_{attempt:02d}'
 cmd=[sys.executable,'-m','pytest','-q','test_features.py','test_validation.py','test_ekf.py','--junitxml='+str(AUDIT/(tag+'.xml'))]
 run=subprocess.run(cmd,cwd=ROOT/'code',text=True,capture_output=True)
 (AUDIT/(tag+'.log')).write_text(run.stdout+'\n'+run.stderr)
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 write_gate(stage,{'input_files_hash_verified':len(inputs['files']),'frozen_base_blobs':len(hashes),'tests':run.stdout.strip(),'source_review':'same assistant static review and independent-formula tests','oracle_arguments_absent':True})
 print(stage,'AUDIT GO',run.stdout.strip())
if __name__=='__main__':audit(sys.argv[1])
