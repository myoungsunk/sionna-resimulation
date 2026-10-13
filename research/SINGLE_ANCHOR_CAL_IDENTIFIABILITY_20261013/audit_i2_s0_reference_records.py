"""Read existing records only; no inference runs or canonical result writes."""
from pathlib import Path
import datetime, hashlib, json, sys
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE / 'out/i2_s0_run_01'

def main():
    consumed = {}
    def record(p):
        consumed[str(p.relative_to(HERE))] = hashlib.sha256(p.read_bytes()).hexdigest()
        return p
    rows = []
    for p in sorted(ROOT.glob('*/*_batch.json')):
        j = json.loads(record(p).read_text())
        with np.load(record(p.with_suffix('.npz')), allow_pickle=False) as raw:
            samples = raw['samples']
        accepts = j['acceptance']
        rows.append(dict(case=str(p.relative_to(ROOT)),
            acceptance_ranges={key:[min(a[key] for a in accepts),max(a[key] for a in accepts)]
                               for key in ('rho','delta','bg','sf','eps','latent_pCN')},
            diagnostics=j['diagnostics'], diagnostic_columns=j['diagnostic_columns'],
            chain_calibration_means=samples[:,:,2:].mean(axis=1).tolist(),
            chain_bg_eps_correlations=[float(np.corrcoef(s[:,2],s[:,4])[0,1]) for s in samples]))
    pf=[]
    for route in ('R2','R4'):
        for arm in ('DR','RANGE_0.05_5'):
            p=ROOT/f'A2_3_GAUSS_LEVEL_{route}_d2_s8000/{arm}_area_posterior.json'
            j=json.loads(record(p).read_text())
            pf.append(dict(case=str(p.relative_to(ROOT)), snapshots=[{k:s[k] for k in
                ('k','t_s','ess','min_ess','ancestors','resamples','unique_cal_pairs')} for s in j]))
    for name in ('i2_s0.py','i2_s0_batch.py','i2_batch.py','I2_S0_DESIGN.json',
                 'out/I2_S0_GATE.json','out/I2_S0_VERIFICATION.json'):
        record(HERE/name)
    result=dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        command=[sys.executable,*sys.argv], scope='READ_ONLY_REANALYSIS_OF_EXISTING_RECORDS',
        experiment_rerun=False, batch=rows,pf_checkpoints=pf,input_sha256=consumed)
    out=HERE/'out/I2_S0_REFERENCE_FAILURE_AUDIT.json'
    if out.exists(): raise FileExistsError(out)
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for row in rows:
        print(row['case'],json.dumps(row['acceptance_ranges']), 'bg_eps_corr', row['chain_bg_eps_correlations'])
    for row in pf:
        print(row['case'],[(s['t_s'],s['ancestors'],round(s['ess'],1)) for s in row['snapshots']])

if __name__=='__main__': main()
