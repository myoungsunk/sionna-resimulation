"""Check S0 outputs, initial-range counting, frozen inputs and source hashes."""
from pathlib import Path
import json,hashlib,datetime,sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=HERE/'out/i2_s0_run_01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    start=datetime.datetime.now(datetime.timezone.utc).isoformat();checks={}
    receipt=json.loads((HERE/'out/I2_S0_EXECUTION_RECEIPT.json').read_text())
    checks['tests_and_execution_zero']=receipt['test_exit_code']==0 and receipt['exit_code']==0
    prior=json.loads((HERE/'out/I2_PACKAGE_SHA256.json').read_text())
    checks['prior_I2_files_unchanged']=all(sha(ROOT/p)==v for p,v in prior.items())
    m=json.loads((OUT/'I2_S0_RUN_MANIFEST.json').read_text())
    checks['code_hashes']=all(sha(HERE/p)==v for p,v in m['code_sha256'].items())
    checks['input_hashes']=all(sha(HERE/p)==v for p,v in m['input_sha256'].items())
    checks['run_output_hashes']=all(sha(OUT/p)==v for p,v in m['output_sha256'].items())
    a=json.loads((OUT/'I2_S0_ANALYSIS_MANIFEST.json').read_text())
    checks['analysis_output_hashes']=all(sha(OUT/p)==v for p,v in a['output_sha256'].items())
    public_ok=[];cfg_ok=[];range_count_ok=[];weights_ok=[]
    for p in OUT.rglob('*_public.npz'):
        with np.load(p) as z:
            public_ok.append(set(z.files)=={'t_s','dt_s','ds_odom','dtheta_gyro','dtheta_odom','range_m','range_mask'})
            source=HERE/'out/i2_run_01'/p.parent.name/p.name
            with np.load(source) as original:
                public_ok.append(all(np.array_equal(z[k],original[k]) for k in z.files))
            count=int(np.count_nonzero(z['range_mask'][1:]))
        cfg=json.loads(p.with_name(p.name.replace('_public.npz','_config.json')).read_text())
        cfg_ok.append(cfg['p0_std'][:3]==[0,0,0] and cfg['anchor_xyz'][:2]==[0,0])
        arm=p.stem.removesuffix('_public')
        for s in p.parent.glob(arm+'_*_posterior.json'):
            snaps=json.loads(s.read_text());range_count_ok.append(snaps[-1]['range_updates_after_initialization']==(0 if arm=='DR' else count))
        for b in p.parent.glob(arm+'_*_batch.json'):
            data=json.loads(b.read_text());range_count_ok.append(data['initial_range_consumed']==(arm!='DR') and data['subsequent_range_count']==(0 if arm=='DR' else count))
    for p in OUT.rglob('*_pf.npz'):
        with np.load(p) as z:weights_ok.append(np.allclose(z['weights_0'],np.full(len(z['weights_0']),1/len(z['weights_0'])),rtol=0,atol=1e-16))
    checks.update(public_sensor_reuse_and_no_pose=all(public_ok),gauge_config=all(cfg_ok),first_range_once=all(range_count_ok),initial_weights_uniform=all(weights_ok))
    frame=pd.read_csv(OUT/'I2_S0_CALIBRATION_POSTERIOR.csv')
    checks.update(primary_and_sensitivity_108=len(frame.groupby(['episode','label']))==108,snapshot_rows_648=len(frame)==648,high_pf_16=len(list(OUT.rglob('*_N*_pf.npz')))==16,batch_8=len(list(OUT.rglob('*_batch.npz')))==8)
    result=dict(start=start,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,script_sha256=sha(Path(__file__)),status='PASS' if all(checks.values()) else 'FAIL',checks=checks,prior_files_verified=len(prior))
    (HERE/'out/I2_S0_VERIFICATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not all(checks.values()):raise SystemExit(1)
if __name__=='__main__':main()
