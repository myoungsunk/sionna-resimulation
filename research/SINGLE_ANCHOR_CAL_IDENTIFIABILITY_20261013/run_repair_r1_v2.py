"""R1-only CDF/tail repair execution, additive outputs and explicit stop gates."""
from pathlib import Path
import datetime,hashlib,json,platform,sys,subprocess,time,traceback
import numpy as np
from repair_r1_cdf_v2 import run_case
from repair_r1_tail_v2 import tail_certificate
H=Path(__file__).resolve().parent;O=H/'out/i2_r1_cdf_tail_v2_01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def conv(x):
 if isinstance(x,np.generic):return x.item()
 raise TypeError(type(x).__name__)
def write(n,v):(O/n).write_text(json.dumps(v,indent=2,default=conv,allow_nan=False)+'\n',encoding='utf-8')
def main():
 O.mkdir(exist_ok=False);start=now();tick=time.perf_counter();code=1
 design=json.loads((H/'I2_R1_CDF_TAIL_V2_DESIGN.json').read_text(encoding='utf-8-sig'))
 sources=[H/n for n in ['I2_R1_CDF_TAIL_V2_DESIGN.json','repair_r1_dr.py','repair_r1_cdf_v2.py','repair_r1_tail_v2.py','run_repair_r1_v2.py','tests/test_repair_r1_cdf_v2.py','tests/test_repair_r1_tail_v2.py']]
 for cell in design['cells']:
  sources += [H/'out/i2_s0_run_01'/cell/'DR_public.npz',H/'out/i2_s0_run_01'/cell/'DR_config.json',H/'out/i2_reference_repair_r0_r1_01'/f'{cell}_n384_b10.json']
 hashes={str(p.relative_to(H)):sha(p) for p in sources}
 protected=json.loads((H/'out/I2_S0_REFERENCE_FAILURE_AUDIT.json').read_text())['input_sha256']
 assert all(sha(H/n)==s for n,s in protected.items())
 write('FROZEN_RECEIPT.json',dict(start=start,command=[sys.executable,*sys.argv],design=design,input_sha256=hashes,python=sys.version,platform=platform.platform()))
 try:
  tests=[str(H/'tests/test_repair_r1_cdf_v2.py'),str(H/'tests/test_repair_r1_tail_v2.py')]
  p=subprocess.run([sys.executable,'-m','pytest','-q',*tests],capture_output=True,text=True)
  (O/'TESTS.log').write_text(p.stdout+p.stderr,encoding='utf-8')
  if p.returncode:raise RuntimeError('unit tests failed')
  all_results=[]
  for cell in design['cells']:
   root=H/'out/i2_s0_run_01'/cell
   with np.load(root/'DR_public.npz',allow_pickle=False) as a:pub={k:a[k] for k in a.files}
   cfg=json.loads((root/'DR_config.json').read_text());old=json.loads((H/'out/i2_reference_repair_r0_r1_01'/f'{cell}_n384_b10.json').read_text())
   center=np.asarray(old['mean'])/np.asarray(cfg['p0_std'][3:]);runs=[]
   for i,settings in enumerate(design['settings']):
    print(cell,i,'START',now(),flush=True);st=time.perf_counter()
    tail=tail_certificate(pub,cfg,center,settings['bound'],digits=design['interval_precision_digits'])
    write(f'{cell}_{i}_TAIL.json',tail)
    result=run_case(pub,cfg,shift=old['log_normalization'],timeout_seconds=design['runtime_limit_seconds_per_case'],**settings)
    result['elapsed_seconds']=time.perf_counter()-st;result['tail']=tail
    write(f'{cell}_{i}_CDF.json',result);runs.append(result)
    print(cell,i,'END','seconds',result['elapsed_seconds'],'evals',result['evaluation_count'],flush=True)
   comparisons=[]
   for a,b in [(0,1),(1,2)]:
    q=np.max(np.abs(np.asarray(runs[a]['marginal_quantiles'])-runs[b]['marginal_quantiles'])/np.asarray(old['sd'])[:,None])
    z=abs(np.expm1(runs[a]['log_normalization']-runs[b]['log_normalization']))
    comparisons.append(dict(first=a,second=b,quantile_change_sd=float(q),normalization_relative_change=float(z)))
   passed=all(c['quantile_change_sd']<=.01 and c['normalization_relative_change']<=1e-6 for c in comparisons)
   passed=passed and runs[-1]['tail']['posterior_tail_upper_bound']<=1e-6 and not any(r['integration_warnings'] for r in runs)
   all_results.append(dict(cell=cell,comparisons=comparisons,passed=passed,tail_upper=runs[-1]['tail']['posterior_tail_upper_bound']))
  write('R1_V2_GATE.json',dict(R1='PASS' if all(r['passed'] for r in all_results) else 'INCONCLUSIVE',cases=all_results,
       scope='Conditional measured-input DR numerical reference only; no Range or physical model approval',reference='DR_NUMERICAL_VALIDATED' if all(r['passed'] for r in all_results) else 'REFERENCE_NOT_VALIDATED',short_range='NOT_RUN',I3='NOT_RUN',I7='NOT_RUN'))
  code=0
 except Exception:
  (O/'ERROR.log').write_text(traceback.format_exc(),encoding='utf-8')
  write('R1_V2_GATE.json',dict(R1='INCONCLUSIVE',reference='REFERENCE_NOT_VALIDATED',reason='Execution error or frozen budget exceeded; see ERROR.log',short_range='NOT_RUN',I3='NOT_RUN',I7='NOT_RUN'))
  raise
 finally:
  write('EXECUTION_RECEIPT.json',dict(start=start,end=now(),exit_code=code,elapsed_seconds=time.perf_counter()-tick,
    original_inputs_unchanged=all(sha(H/n)==v for n,v in protected.items()),code_inputs_unchanged=all(sha(H/n)==v for n,v in hashes.items()),input_sha256=hashes,
    output_sha256={p.name:sha(p) for p in O.iterdir() if p.is_file()}))
if __name__=='__main__':main()
