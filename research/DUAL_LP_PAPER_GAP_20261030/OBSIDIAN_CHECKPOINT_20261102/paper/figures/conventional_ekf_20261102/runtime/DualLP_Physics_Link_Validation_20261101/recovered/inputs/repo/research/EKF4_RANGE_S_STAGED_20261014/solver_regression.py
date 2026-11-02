"""R1 GitHub cloud-only frozen solver regression; never runs P2."""
import argparse
import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from core import SyntheticRF,map_update
from validate import sha,write

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--gates',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    a=p.parse_args()
    from pre_run_audit import require_audit_receipt
    audit=require_audit_receipt(a.audit)
    if os.getenv('GITHUB_ACTIONS')!='true':
        raise RuntimeError('GitHub-hosted runner only')
    gate=json.loads((a.gates/'FINAL.json').read_text())
    if (gate['git_sha']!=os.getenv('GITHUB_SHA') or gate['exit_code']!=0 or
        gate['stages']['P0']!='PASS' or gate['stages']['P1']!='PASS' or
        gate['source_sha256'].get('core.py')!=sha(HERE/'core.py') or
        gate['source_sha256'].get('test_solver_regression.py')!=sha(HERE/'test_solver_regression.py')):
        raise RuntimeError('same-commit P0/P1/source integrity gate failed')
    out=a.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    result={'schema':'SOLVER_R1_NUMERICAL_ONLY','start_utc':datetime.now(timezone.utc).isoformat(),
            'git_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
            'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
            'python':platform.python_version(),'stage':'SOLVER_R1',
            'gate_receipt_sha256':sha(a.gates/'FINAL.json'),
            'snapshot_sha256':sha(HERE/'FAILURE_SNAPSHOT.json'),
            'frozen_D1_summary_sha256':sha(HERE/'D1_RESULT_SUMMARY.json'),
            'core_sha256':sha(HERE/'core.py'),'test_sha256':sha(HERE/'test_solver_regression.py'),
            'audit_receipt_sha256':sha(a.audit),'audit_status':audit['decision'],
            'original_gradient_tol':1e-8,'P2':'NOT_RUN','P3_P6':'NOT_RUN','scientific_PASS':False,
            'status':'STARTED'}
    write(out/'START.json',result)
    code=1
    try:
        cmd=[sys.executable,'-m','pytest','-q','-s','--strict-markers',
             '-c',str(HERE/'pytest.ini'),'-m','regression',str(HERE/'test_solver_regression.py'),
             '--junitxml='+str(out/'REGRESSION.xml')]
        proc=subprocess.run(cmd,cwd=HERE,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (out/'REGRESSION.log').write_text(proc.stdout,encoding='utf-8')
        print(proc.stdout,flush=True)
        result['command']=cmd
        result['pytest_exit_code']=proc.returncode
        if proc.returncode!=0:
            raise RuntimeError('frozen failure solver regression failed')
        f=json.loads((HERE/'FAILURE_SNAPSHOT.json').read_text())
        x,P,z,R=map(lambda name:np.asarray(f[name]),('prior_x','prior_P','z','R'))
        local=map_update(x,P,z,SyntheticRF(),R,range_first=False,
                         initial_delta=np.asarray(f['prior_delta']),max_iter=40,gradient_tol=1e-8)
        regular=map_update(x,P,z,SyntheticRF(),R,range_first=True,max_iter=40,gradient_tol=1e-8)
        if (local.status!='CONVERGED' or regular.status!='CONVERGED' or
            local.gradient_inf>1e-8 or regular.gradient_inf>1e-8 or
            not local.history):
            raise RuntimeError('original stationary gradient criterion failed')
        result['diagnostics']={'original_status':f['recorded_status'],
              'original_gradient':f['recorded_gradient_inf'],
              'saved_iterate_gradient':local.gradient_inf,
              'range_first_gradient':regular.gradient_inf,
              'accepted_via':local.history[0].get('step_acceptance','UNKNOWN'),
              'double_cost_delta':local.history[0].get('direct_cost_difference'),
              'integral_cost_delta':local.history[0].get('gradient_integral_difference'),
              'curvature_ratio':local.history[0].get('curvature_ratio')}
        result['status']='REGRESSION_PASS'
        code=0
    except Exception:
        result['status']='FAIL_CLOSED'
        (out/'TRACEBACK.log').write_text(traceback.format_exc(),encoding='utf-8')
        print(traceback.format_exc(),flush=True)
    result['exit_code']=code
    result['end_utc']=datetime.now(timezone.utc).isoformat()
    result['output_sha256']={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    write(out/'FINAL.json',result)
    print('R1_FINAL '+json.dumps({k:v for k,v in result.items() if k!='output_sha256'},ensure_ascii=False,allow_nan=False),flush=True)
    return code

if __name__=='__main__':
    raise SystemExit(main())
