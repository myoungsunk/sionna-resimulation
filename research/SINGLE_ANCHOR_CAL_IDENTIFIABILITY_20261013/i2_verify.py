"""Verify completed I2 bundle, pairing, I0 reuse, and current code tests."""
from pathlib import Path
import json,subprocess,sys,hashlib,datetime
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
OUT=HERE/'out/i2_run_01'

def main():
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    command=[sys.executable,'-m','pytest','-q',str(HERE/'tests')]
    result=subprocess.run(command,capture_output=True,text=True)
    (HERE/'out/I2_TESTS.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    checks={'tests':result.returncode==0}
    checks['execution_exit_zero']=json.loads((HERE/'out/I2_EXECUTION_RECEIPT.json').read_text())['exit_code']==0
    manifest=json.loads((OUT/'I2_RUN_MANIFEST.json').read_text())
    checks['output_hashes']=all(hashlib.sha256((OUT/p).read_bytes()).hexdigest()==h for p,h in manifest['outputs_sha256'].items())
    checks['source_hashes']=all(hashlib.sha256((HERE.parents[1]/p).read_bytes()).hexdigest()==h for p,h in manifest['input_code_sha256'].items())
    pairing=[];i0=[]
    for episode in [p for p in OUT.iterdir() if p.is_dir()]:
        with np.load(episode/'DR_public.npz') as z: base=dict(z)
        for path in episode.glob('*_public.npz'):
            with np.load(path) as z:
                pairing.append(all(np.array_equal(z[k],base[k]) for k in ('t_s','dt_s','ds_odom','dtheta_gyro','dtheta_odom','x0')))
                pairing.append(set(z.files)=={'t_s','dt_s','ds_odom','dtheta_gyro','dtheta_odom','x0','range_m','range_mask'})
        if episode.name.endswith('s8000'):
            with np.load(HERE/'out/run_01'/episode.name/'public.npz') as z:
                i0.append(all(np.array_equal(z[k],base[k]) for k in z.files))
    checks.update(common_public_inputs=all(pairing),i0_exact_reuse=all(i0),i0_reused_episodes=len(i0)==4)
    f=pd.read_csv(OUT/'I2_CALIBRATION_POSTERIOR.csv')
    checks.update(primary_runs=len(f.groupby(['episode','arm']))==144,snapshot_rows=len(f)==864,batch_runs=len(list(OUT.rglob('*_batch.npz')))==4,high_pf_runs=len(list(OUT.rglob('*_pf_high_*.npz')))==8)
    receipt=dict(start=start,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,test_exit_code=result.returncode,checks=checks,status='PASS' if all(checks.values()) else 'FAIL',independent_pre_execution_review='ACCEPT; implementation only, not scientific outcome',finalization_first_attempt=dict(exit_code=1,error='ValueError: Out of range float values are not JSON compliant: inf',cause='zero PF variance in derived ratio',repair='undefined ratio stored null, convergence check false; no changes to PF samples'),finalization_second_attempt_exit_code=0)
    (HERE/'out/I2_VERIFICATION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
