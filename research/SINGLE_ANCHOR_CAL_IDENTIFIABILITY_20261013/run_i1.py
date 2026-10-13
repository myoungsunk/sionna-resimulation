"""One-stage execution receipt; exits before I2."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import subprocess,sys,json,datetime,hashlib
HERE=Path(__file__).resolve().parent
def main():
    out=HERE/'out/i1_run_01'
    runs=[]
    for script in ['i1_structural_observability.py','i1_profile_likelihood.py']:
        args=[sys.executable,str(HERE/script),'--out',str(out)]
        p=subprocess.run(args,capture_output=True,text=True)
        if not out.exists():raise RuntimeError(p.stderr)
        (out/(script+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        print(script,p.returncode,flush=True)
        runs.append(dict(command=args,exit_code=p.returncode))
        if p.returncode:raise RuntimeError(p.stderr)
    receipt=dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),runs=runs,I2='NOT_RUN',source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('i1_*.py')})
    (out/'COMPLETION.json').write_text(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
