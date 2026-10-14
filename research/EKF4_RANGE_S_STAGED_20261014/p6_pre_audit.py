"""P6 audit-first: source and frozen archive eligibility only, not scientific PASS."""
import ast,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OLD=ROOT/'research/EKF3_INDEPENDENT_20261013'
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\x00'+b).hexdigest()
def main():
 if os.getenv('GITHUB_ACTIONS')!='true':raise RuntimeError('GitHub Actions only')
 checks=[]
 spec=json.loads((OLD/'P0_INPUT_MANIFEST.json').read_text())
 checks.append(('39 assets 7 cases',len(spec['assets'])==39 and len(spec['cases'])==7))
 checks.append(('input units and observer',spec['physical_contract']['state']==['x_m','y_m','yaw_rad'] and
                's=(P1-P2)/(P1+P2)' in spec['physical_contract']['observer']))
 for path in ('p6_r0_recursive.py','core.py','stable_descent.py'):
  try:checks.append(('AST '+path,ast.parse((HERE/path).read_text()) is not None))
  except Exception:checks.append(('AST '+path,False))
 src=(HERE/'p6_r0_recursive.py').read_text()
 checks.append(('P6 uses original RF data not altered','old.read_rf(case,channel,ids,freq)' in src))
 checks.append(('R0 joint innovation once','gaussian_update(prior_x,prior_P,z,model,covR' in src))
 checks.append(('MAP separate failure record',"'failed'" in src and "'MAP_UPDATE'" in src))
 checks.append(('no hidden MAP fallback','sol.status' in src and 'e[\'failed\']' in src))
 workflow=(ROOT/'.github/workflows/ekf4-p6-r0-recursive.yml').read_text()
 seq=[workflow.find(c) for c in (
    'python research/EKF4_RANGE_S_STAGED_20261014/p6_pre_audit.py',
    'python research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py',
    'python research/EKF4_RANGE_S_STAGED_20261014/p6_r0_recursive.py')]
 checks.append(('audit before validation and P6',all(i>=0 for i in seq) and seq==sorted(seq)))
 receipt={'stage':'P6_R0_AUDIT','source_sha':os.getenv('GITHUB_SHA'),
          'run_id':os.getenv('GITHUB_RUN_ID'),
          'decision':'GO' if all(v for _,v in checks) else 'HOLD',
          'checks':[{'check':k,'ok':v} for k,v in checks],
          'limitations':['P4 MAP one-step has numerical invalid cases',
                         'P5 G3 integration reference remains NOT_VALIDATED',
                         'only one RF case and seed; no independent scene generalization'],
          'scientific_PASS':False,'independent_peer_audit':False}
 Path(os.environ['RUNNER_TEMP'],'P6_PRE_RUN.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('P6_PRE_RUN '+json.dumps(receipt),flush=True)
 return 0 if receipt['decision']=='GO' else 2
if __name__=='__main__':raise SystemExit(main())
