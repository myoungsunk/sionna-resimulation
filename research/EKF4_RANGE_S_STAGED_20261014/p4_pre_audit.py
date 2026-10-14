"""P4 mandatory source and model audit, run BEFORE all numerical execution."""
import ast,hashlib,json,os
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=ROOT/'research/EKF3_INDEPENDENT_20261013'
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\x00'+b).hexdigest()
def main():
 if os.getenv('GITHUB_ACTIONS')!='true':raise RuntimeError('Actions only')
 checks=[]
 m=json.loads((OLD/'P0_INPUT_MANIFEST.json').read_text())
 checks.append(('39 immutable assets and 7 scenes',len(m['assets'])==39 and len(m['cases'])==7))
 checks.append(('observer original channel semantics','s=(P1-P2)/(P1+P2)' in m['physical_contract']['observer']))
 for name in ('p4_one_step.py','core.py','pre_run_audit.py'):
  try:
   tree=ast.parse((HERE/name).read_text())
   checks.append((name+' AST parse',tree is not None))
  except Exception:checks.append((name+' AST parse',False))
 c=(HERE/'p4_one_step.py').read_text()
 checks.append(('No use of truth in RF likelihood model',not ('truth[k]' in c[c.index('def model(x):'):c.index('freq=np.load(')])))
 checks.append(('one observation per estimator and same-prior parity',
     'sequential_affine(mu,C,z,h,H,R)' in c and 'gaussian_update(mu,C,z,model,R)' in c))
 workflow=(ROOT/'.github/workflows/ekf4-p4-one-step.yml').read_text()
 ids=[workflow.find(x) for x in ('python research/EKF4_RANGE_S_STAGED_20261014/p4_pre_audit.py','python research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py','python research/EKF4_RANGE_S_STAGED_20261014/p4_one_step.py')]
 checks.append(('audit then P0 parity then one-step',all(x>=0 for x in ids) and ids==sorted(ids)))
 receipt={'stage':'P4_PRE_RUN','sha':os.getenv('GITHUB_SHA'),'run':os.getenv('GITHUB_RUN_ID'),
          'checks':[{'name':n,'ok':ok} for n,ok in checks],
          'decision':'GO' if all(v for _,v in checks) else 'HOLD','scientific_PASS':False}
 Path(os.environ['RUNNER_TEMP'],'P4_PRE_RUN.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('P4_PRE_RUN '+json.dumps(receipt),flush=True)
 return 0 if receipt['decision']=='GO' else 2
if __name__=='__main__':raise SystemExit(main())
