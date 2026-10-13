from pathlib import Path
import json,hashlib,datetime,sys
import numpy as np
from repair_r1_dr import DRReference,compare_cases
from i2_s0_batch import S0BatchTarget
H=Path(__file__).resolve().parent; S=H/'out/i2_reference_repair_r0_r1_01'; O=H/'out/i2_reference_repair_r0_r1_recovery_01'
O.mkdir(exist_ok=False); consumed={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 consumed[str(p.relative_to(H))]=sha(p)
 return json.loads(p.read_text())
def write(n,v):(O/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
design=read(H/'I2_REFERENCE_REPAIR_DESIGN.json'); frozen=read(S/'R0_FROZEN_RECEIPT.json')
assert sha(H/'I2_REFERENCE_REPAIR_DESIGN.json')==frozen['sha256']['I2_REFERENCE_REPAIR_DESIGN.json']
cases=[];density=[]
for cell in design['dr']['cells']:
 root=H/'out/i2_s0_run_01'/cell;cfg=read(root/'DR_config.json');p=root/'DR_public.npz';consumed[str(p.relative_to(H))]=sha(p)
 with np.load(p,allow_pickle=False) as raw:pub={k:raw[k] for k in raw.files}
 ref=DRReference(pub,cfg);old=S0BatchTarget(pub,cfg,'DR');errors=[]
 for z in np.random.default_rng(2026101301).normal(size=(128,3)):
  ll=old.evaluate(np.r_[0.,0.,z],np.zeros((2,len(pub['t_s'])-1)))-.5*(z@z+3*np.log(2*np.pi))
  errors.append(abs(ref.direct_logdensity(z)-ll))
 density.append(dict(cell=cell,points=128,max_absolute_log_error=float(max(errors)),passed=bool(max(errors)<=1e-8)))
 samples={f'{n}_{b}':read(S/f'{cell}_n{n}_b{b}.json') for n,b in [(96,8),(192,8),(384,8),(384,6),(384,10)]}
 checks={label:compare_cases(samples[a],samples[b]) for label,a,b in [('refinement_96_192','96_8','192_8'),('refinement_192_384','192_8','384_8'),('domain_6_8','384_6','384_8'),('domain_8_10','384_8','384_10')]}
 stable=all(checks[k]['normalization_relative_difference']<=1e-6 and max(checks[k]['quantile_difference_sd'])<=.01 for k in ('refinement_192_384','domain_8_10'))
 cases.append(dict(cell=cell,checks=checks,numerical_stability_pass=stable,tail_numerical_upper_estimate=samples['384_10']['posterior_omitted_tail_upper_bound'],certified_tail_bound=False,reference_validated=False,tail_note='Numeric inside evidence denominator; estimate 1 uninformative, not proof of large tail',final_finite_box=samples['384_10']))
write('TARGET_DENSITY_CHECKS.json',density);write('DR_REFERENCE_INTEGRATION.json',cases)
write('I2_REFERENCE_REVALIDATION_GATE.json',dict(R0='PASS',R1='INCONCLUSIVE',short_range='NOT_RUN',large_repair='NOT_RUN',I3='NOT_RUN',I7='NOT_RUN',reference='REFERENCE_NOT_VALIDATED',dependency_action='STOP_DEPENDENT_RANGE_RUNS',reasons=['Quantile refinement/domain change exceeds frozen .01 posterior SD','Omitted posterior mass not certified within 1e-6']))
old=read(S/'EXECUTION_RECEIPT.json');assert old['exit_code']==1 and old['protected_inputs_unchanged'] and old['code_inputs_unchanged']
audit=read(H/'out/I2_S0_REFERENCE_FAILURE_AUDIT.json');assert all(sha(H/n)==h for n,h in audit['input_sha256'].items())
consumed['finalize_repair_r0_r1.py']=sha(Path(__file__))
write('RECOVERY_RECEIPT.json',dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=[sys.executable,*sys.argv],exit_code=0,original_execution_exit_code=1,integration_rerun=False,original_run_unchanged=all(sha(H/n)==h for n,h in consumed.items()),input_sha256=consumed,output_sha256={p.name:sha(p) for p in O.iterdir()}))
for c in cases:print(c['cell'],json.dumps(c['checks']['refinement_192_384']),json.dumps(c['checks']['domain_8_10']))
print(json.dumps(density))
