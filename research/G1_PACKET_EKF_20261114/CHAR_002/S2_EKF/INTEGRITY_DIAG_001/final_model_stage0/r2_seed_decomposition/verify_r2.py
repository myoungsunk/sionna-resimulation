"""Separate trace/CSV self-check; no filter replay."""
from pathlib import Path
import csv, json, hashlib, datetime
import numpy as np
P=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
summary=json.loads((P/'SUMMARY.json').read_text(encoding='utf-8'))
with (P/'PACKET_TIMELINE.csv').open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
max_ledger=0.; max_rms=0.
for seed in range(10,15):
    for arm in ('G0','G1_LORO','G1_KI'):
        sub=[r for r in rows if int(r['seed'])==seed and r['arm']==arm]
        error=np.array([float(r['heading_error_deg']) for r in sub])
        prior=np.array([float(r['prior_error_deg']) for r in sub])
        pred=np.array([float(r['gyro_white_deg'])+float(r['bg_correction_deg']) for r in sub])
        update=np.array([float(r['range_update_deg'])+float(r['conditional_s_update_deg']) for r in sub])
        np.testing.assert_allclose(error,prior+update,rtol=0,atol=1e-10)
        np.testing.assert_allclose(prior[1:],error[:-1]+pred[1:],rtol=0,atol=1e-10)
        max_ledger=max(max_ledger,float(np.max(np.abs(error-prior-update))))
        times=np.array([float(r['t_s']) for r in sub])
        for w in summary['windows']:
            if (w['seed'],w['arm'])!=(seed,arm):continue
            m=(times>=w['start_s'])&(times<w['end_s'])
            rms=float(np.sqrt(np.mean(error[m]**2)))
            max_rms=max(max_rms,abs(rms-w['heading_rmse_deg']))
            assert abs(rms-w['heading_rmse_deg'])<1e-10
for p,digest in {**summary['inputs'],**summary['sources']}.items():assert sha(p)==digest,p
lane=json.loads((P/'RUN_CONTRACT_ATTEMPT02.json').read_text(encoding='utf-8'))
assert sha(lane['code']['path'])==lane['code']['sha256']
result=dict(status='PASS',classification='SELF_CHECK',no_replay=True,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),traces=15,packets=len(rows),max_csv_ledger_abs_deg=max_ledger,max_csv_rms_abs_deg=max_rms,input_source_hashes_unchanged=True,code_sha256=sha(__file__),outputs={p.name:sha(p) for p in P.iterdir() if p.is_file() and p.name!='VERIFICATION.json'})
(P/'VERIFICATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='outputs'},indent=2))
