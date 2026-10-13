"""Audit immutable inputs, verify code, then execute only the frozen I2 S0 design."""
from pathlib import Path
import subprocess,sys,os,json,hashlib,datetime,platform
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    receipt=HERE/'out/I2_S0_EXECUTION_RECEIPT.json'
    if receipt.exists():raise RuntimeError('Existing run receipt must be preserved')
    record=dict(start=now(),thread_id=os.environ.get('CODEX_THREAD_ID'),platform=platform.platform(),python=sys.version,executable=sys.executable,base='ed1dc86221c54553e50b1204aab3129d95e1cbef',local_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    frozen=json.loads((HERE/'out/I2_PACKAGE_SHA256.json').read_text())
    mismatches=[p for p,h in frozen.items() if digest(ROOT/p)!=h]
    record['prior_I2_package_verified_files']=len(frozen);record['prior_mismatches']=mismatches
    if mismatches:raise RuntimeError('Frozen I2 files changed: '+str(mismatches))
    command=[sys.executable,'-m','pytest','-q',str(HERE/'tests')]
    test=subprocess.run(command,capture_output=True,text=True,cwd=ROOT)
    (HERE/'out/I2_S0_TESTS.log').write_text(test.stdout+test.stderr,encoding='utf-8')
    record.update(test_command=command,test_exit_code=test.returncode)
    record['code_sha256']={p.name:digest(p) for p in [HERE/'i2_s0.py',HERE/'i2_s0_batch.py',HERE/'I2_S0_DESIGN.json',Path(__file__)]}
    command=[sys.executable,str(HERE/'i2_s0.py'),'--out',str(HERE/'out/i2_s0_run_01')]
    record['command']=command
    receipt.write_text(json.dumps(record,indent=2),encoding='utf-8')
    if test.returncode:raise SystemExit(test.returncode)
    with (HERE/'out/I2_S0_EXECUTION.log').open('w',encoding='utf-8') as log:
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
    record.update(end=now(),exit_code=result.returncode)
    receipt.write_text(json.dumps(record,indent=2),encoding='utf-8')
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
