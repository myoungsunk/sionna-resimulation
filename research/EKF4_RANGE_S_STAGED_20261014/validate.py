"""Execute P0/P1 on GitHub Actions; never mark later stages executed."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--until',choices=['P0','P1'],default='P1')
    args=ap.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Scientific execution is restricted to GitHub Actions by user contract')
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    source={str(p.relative_to(HERE)):sha(p) for p in sorted(HERE.rglob('*'))
            if p.is_file() and p.suffix in ('.py','.json','.md','.ini','.txt') and '__pycache__' not in str(p)}
    receipt={'created_utc':datetime.now(timezone.utc).isoformat(),
             'git_sha':os.environ.get('GITHUB_SHA'), 'run_id':os.environ.get('GITHUB_RUN_ID'),
             'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'), 'runner_os':os.environ.get('RUNNER_OS'),
             'python':platform.python_version(),'packages':{p:importlib.metadata.version(p) for p in ['numpy','scipy','pytest']},
             'source_sha256':source,'command':sys.argv,
             'stages':{f'P{i}':'NOT_RUN' for i in range(7)},
             'scientific_PASS':False,'scope':'mathematics and local solver only; no RF or recursive experiment'}
    write(out/'START.json',receipt)
    exit_code=0
    for stage in ['P0','P1'][:1 if args.until=='P0' else 2]:
        junit=out/(stage+'.xml')
        command=[sys.executable,'-m','pytest','-q','-s','--strict-markers',
                 '-c',str(HERE/'pytest.ini'),'-m',stage.lower(),str(HERE/'test_core.py'),
                 '--junitxml='+str(junit)]
        begin=datetime.now(timezone.utc).isoformat()
        proc=subprocess.run(command,cwd=HERE,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (out/(stage+'.log')).write_text(proc.stdout,encoding='utf-8')
        print(proc.stdout,flush=True)
        tests={}
        if junit.exists():
            tree=ET.parse(junit)
            suites=tree.getroot().findall('testsuite')
            tests={k:sum(int(s.attrib.get(k,'0')) for s in suites) for k in ['tests','failures','errors','skipped']}
        passed=proc.returncode==0 and tests.get('tests',0)>0 and tests.get('skipped',0)==0
        status='PASS' if passed else 'IMPLEMENTATION_OR_NUMERICAL_GATE_FAILED'
        sr={'stage':stage,'status':status,'tests':tests,'started_utc':begin,
            'ended_utc':datetime.now(timezone.utc).isoformat(),'exit_code':proc.returncode,
            'command':command,'git_sha':receipt['git_sha'],'source_sha256':source,
            'log_sha256':sha(out/(stage+'.log')),'scientific_PASS':False}
        write(out/(stage+'_RECEIPT.json'),sr)
        receipt['stages'][stage]=status
        print('STAGE_RESULT '+json.dumps(sr,ensure_ascii=False),flush=True)
        if not passed:
            exit_code=proc.returncode or 1
            break
    receipt['exit_code']=exit_code
    receipt['status']='IMPLEMENTED_SCOPE_PASS' if exit_code==0 else 'FAIL_CLOSED'
    receipt['ended_utc']=datetime.now(timezone.utc).isoformat()
    receipt['output_sha256']={p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    write(out/'FINAL.json',receipt)
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f:
            f.write('# EKF4 P0/P1\n\n'+json.dumps(receipt['stages'],ensure_ascii=False)+'\n\nscientific_PASS=false\n')
    print('FINAL_RESULT '+json.dumps(receipt,ensure_ascii=False),flush=True)
    return exit_code


if __name__=='__main__':
    raise SystemExit(main())
