"""Record test receipts and source identities; never advances I1."""
from pathlib import Path
import subprocess, sys, json, hashlib, datetime, shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE='160841d93fbd09c1949551ba08fcd0ed2a8c42ab'

def digest(b): return hashlib.sha256(b).hexdigest()
def write(p,x): p.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def git(*a): return subprocess.check_output(['git',*a],cwd=ROOT)

def main():
    out=HERE/'out'; run=out/'run_01'
    manifest=json.loads((run/'I0_INPUT_MANIFEST.json').read_text(encoding='utf-8'))
    normalized=[p.replace('\\','/') for p in manifest['source_hashes']]
    paths=[p for p in normalized if not p.startswith('research/SINGLE_ANCHOR')]
    identity={}
    for p in paths:
        committed=git('show',BASE+':'+p)
        # Local checkout may use CRLF. Distinguish exact bytes from normalized text.
        local=(ROOT/p).read_bytes()
        identity[p]=dict(committed_sha256=digest(committed),local_sha256=digest(local),exact_bytes=committed==local,normalized_text=committed.replace(b'\r\n',b'\n')==local.replace(b'\r\n',b'\n'))
    write(out/'SOURCE_IDENTITY.json',dict(reference=BASE,files=identity,all_normalized_equal=all(x['normalized_text'] for x in identity.values())))
    prefix='research/LOS_RANGE_RECAL_20261012/'
    evidence=['P5_AUDIT_R2_1_KO.md','R23_PREREG_KO.md','R23_RESULT_KO.md','R2_STATUS_KO.md','p3_common.py','out_p0_p5/R1/P0/P0_INPUT_MANIFEST.json','out_p0_p5/R1/P3/P3_FREEZE_ADDENDUM.json','out_p0_p5/R1/P3/P3_FROZEN_MODEL.json','out_p0_p5/R1/P5/P5_GATE.md']
    rf={prefix+p:dict(sha256=digest(git('show',BASE+':'+prefix+p)),verified='committed source/document bytes; full RF data NOT verified') for p in evidence}
    write(out/'RF_SOURCE_INVENTORY.json',dict(reference=BASE,sources=rf,full_RF_inputs='UNRESOLVED_CONFIG',frequency_array='UNRESOLVED_CONFIG',R23_runner='MISSING_FROM_INSPECTED_TREE'))
    checks=[]
    for label,args in [('compile',[sys.executable,'-m','compileall','-q',str(HERE)]),('pytest',[sys.executable,'-m','pytest','-q',str(HERE/'tests')])]:
        p=subprocess.run(args,capture_output=True,text=True,cwd=ROOT)
        (out/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        checks.append(dict(name=label,command=args,exit_code=p.returncode))
    write(out/'VERIFICATION.json',dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=checks,source_equivalence=all(x['normalized_text'] for x in identity.values())))
    for name in ('I0_INPUT_MANIFEST.json','I0_REPRODUCTION.json','I0_GATE.json'):
        shutil.copyfile(run/name,out/name)
    assert all(c['exit_code']==0 for c in checks)
    assert all(x['normalized_text'] for x in identity.values())
    print(json.dumps(dict(checks=checks,source_files=len(identity),rf_evidence=len(rf))))

if __name__=='__main__':main()
