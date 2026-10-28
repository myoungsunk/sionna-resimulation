import os, sys, json, hashlib, subprocess, datetime, traceback
from pathlib import Path
P=Path(r'D:\SLAM_bot\DELTA_S_INFO_AUDIT_V1_1_CODE')
E=Path(__file__).parent
R=Path(r'D:\SLAM_bot\DS_X1_X2_RESULTS_COMMIT_20261026')
O=Path(r'D:\SLAM_bot\DELTA_S_INFO_AUDIT_V1_1_RESULTS')
S=Path(r'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2')
A=S.parent/'p2_artifacts'
C=R/'research/DS_RF_CAUSAL_STAGE7_8_V1_20261028/code'
os.environ.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
def sha(p): return hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
def git(*args): return subprocess.check_output(['git','-C',str(R),*args],text=True).strip()
receipt={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[]}
rc=1
try:
    assert not O.exists(), 'OUTPUT_ALREADY_EXISTS'
    manifest=json.loads((P/'PACKAGE_CONTENT_SHA256.json').read_text(encoding='utf-8'))
    for name,h in manifest.items():
        assert sha(P/name)==h, 'PACKAGE_HASH: '+name
    receipt['package_hashes_verified']=len(manifest)
    receipt['repo_head']=git('rev-parse','HEAD')
    receipt['repo_status_before']=git('status','--porcelain')
    before={str(p.relative_to(C)):sha(p) for p in C.rglob('*.py')}
    receipt['code_hashes_before']=before
    commands=[('REGRESSION.log',[sys.executable,'-B','-m','unittest','-v','test_ds_info_audit']),('ACTUAL_DATA.log',[sys.executable,'-B','-u',str(P/'ds_info_audit.py'),'--mode','real','--repo-root',str(R),'--source-root',str(S),'--artifacts-root',str(A),'--code-root',str(C),'--output-root',str(O)])]
    for name,cmd in commands:
        print('START',name,flush=True)
        with (E/name).open('x',encoding='utf-8') as log:
            result=subprocess.run(cmd,cwd=P,stdout=log,stderr=subprocess.STDOUT)
        receipt['commands'].append({'argv':cmd,'log':name,'exit_code':result.returncode})
        if result.returncode: raise RuntimeError(f'{name}: exit {result.returncode}')
        print('PASS',name,flush=True)
    status=json.loads((O/'INFORMATION_AUDIT_STATUS.json').read_text())
    for name,h in status['outputs'].items(): assert sha(O/name)==h, 'OUTPUT_HASH: '+name
    receipt['output_status']=status['status']
    receipt['outputs_verified']=len(status['outputs'])
    receipt['status']='EXECUTION_COMPLETED_NOT_SCIENTIFIC_ADOPTION'
    rc=0
except BaseException as exc:
    receipt.update(status='STOPPED_ON_FAILURE',error=repr(exc))
    traceback.print_exc()
finally:
    receipt['repo_status_after']=git('status','--porcelain')
    receipt['package_preserved']=all(sha(P/n)==h for n,h in manifest.items())
    receipt['code_preserved']=before=={str(p.relative_to(C)):sha(p) for p in C.rglob('*.py')}
    receipt['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (E/'EXECUTION_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
sys.exit(rc)
