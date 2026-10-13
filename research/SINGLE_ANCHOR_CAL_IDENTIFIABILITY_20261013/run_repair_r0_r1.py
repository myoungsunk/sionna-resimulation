"""Frozen sequential R0/R1 execution; failures block dependent Range runs."""
from pathlib import Path
import datetime, hashlib, json, platform, subprocess, sys, time, traceback
import numpy as np
from repair_r1_dr import DRReference, run_case, compare_cases
from i2_s0_batch import S0BatchTarget

HERE=Path(__file__).resolve().parent
OUT=HERE/'out/i2_reference_repair_r0_r1_01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    OUT.mkdir(exist_ok=False)
    start=now(); clock=time.perf_counter(); exit_code=1
    frozen=HERE/'I2_REFERENCE_REPAIR_DESIGN.json'; design=json.loads(frozen.read_text())
    files=[frozen,HERE/'repair_target.py',HERE/'repair_r1_dr.py',Path(__file__),
           HERE/'tests/test_repair_target.py',HERE/'tests/test_repair_r1_dr.py']
    for cell in design['dr']['cells']:
        root=HERE/'out/i2_s0_run_01'/cell
        files.extend([root/'DR_public.npz',root/'DR_config.json'])
    audit=json.loads((HERE/'out/I2_S0_REFERENCE_FAILURE_AUDIT.json').read_text())
    protected={n:sha(HERE/n) for n in audit['input_sha256']}
    assert protected==audit['input_sha256'],'Existing audited evidence changed'
    sources={str(p.relative_to(HERE)):sha(p) for p in files}
    write('R0_FROZEN_RECEIPT.json',dict(timestamp_utc=start,design=design,sha256=sources,
        command=[sys.executable,*sys.argv],environment=dict(python=sys.version,platform=platform.platform())))
    try:
        tests=[str(HERE/'tests/test_repair_target.py'),str(HERE/'tests/test_repair_r1_dr.py')]
        result=subprocess.run([sys.executable,'-m','pytest','-q',*tests],capture_output=True,text=True)
        (OUT/'TESTS.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode: raise RuntimeError('R0/R1 unit tests failed')
        cases=[]; density=[]
        for cell in design['dr']['cells']:
            root=HERE/'out/i2_s0_run_01'/cell
            with np.load(root/'DR_public.npz',allow_pickle=False) as raw: public={k:raw[k] for k in raw.files}
            cfg=json.loads((root/'DR_config.json').read_text())
            ref=DRReference(public,cfg); legacy=S0BatchTarget(public,cfg,'DR')
            rng=np.random.default_rng(2026101301); errors=[]
            for z in rng.normal(size=(128,3)):
                old=legacy.evaluate(np.r_[0.,0.,z],np.zeros((2,len(public['t_s'])-1)))-.5*(z@z+3*np.log(2*np.pi))
                errors.append(abs(ref.direct_logdensity(z)-old))
            density.append(dict(cell=cell,points=128,max_absolute_log_error=max(errors),
                                passed=max(errors)<=design['dr']['density_absolute_log_error_max']))
            summaries={}
            schedule=[(n,8) for n in design['dr']['orders']]+[(384,b) for b in (6,10)]
            for order,bound in schedule:
                tick=time.perf_counter(); s=run_case(public,cfg,order,bound)
                s['elapsed_seconds']=time.perf_counter()-tick
                summaries[f'{order}_{bound}']=s
                write(f'{cell}_n{order}_b{bound}.json',s)
                print(cell,order,bound,'seconds',round(s['elapsed_seconds'],2),flush=True)
            checks={label:compare_cases(summaries[a],summaries[b]) for label,a,b in
                [('refinement_96_192','96_8','192_8'),('refinement_192_384','192_8','384_8'),
                 ('domain_6_8','384_6','384_8'),('domain_8_10','384_8','384_10')]}
            required=[checks[k] for k in ('refinement_192_384','domain_8_10')]
            numerical=all(c['normalization_relative_difference']<=1e-6 and
                          max(c['quantile_difference_sd'])<=.01 for c in required)
            tail=summaries['384_10']['posterior_omitted_tail_upper_bound']
            tail_ok=tail is not None and tail<=design['dr']['posterior_omitted_mass_upper_max']
            cases.append(dict(cell=cell,checks=checks,numerical_stability_pass=numerical,
                              tail_upper_bound=tail,tail_pass=tail_ok,
                              reference_validated=numerical and tail_ok and density[-1]['passed']))
        write('TARGET_DENSITY_CHECKS.json',density)
        write('DR_REFERENCE_INTEGRATION.json',cases)
        passed=all(c['reference_validated'] for c in cases)
        write('I2_REFERENCE_REVALIDATION_GATE.json',dict(R0='PASS',R1='PASS' if passed else 'INCONCLUSIVE',
            short_range='NOT_RUN',large_repair='NOT_RUN',I3='NOT_RUN',I7='NOT_RUN',
            reference='DR_ONLY_VALIDATED' if passed else 'REFERENCE_NOT_VALIDATED',
            dependency_action='SHORT_RANGE_NEXT' if passed else 'STOP_DEPENDENT_RANGE_RUNS',
            reasons=[] if passed else ['Independent integration did not meet every frozen numerical/tail criterion']))
        exit_code=0
    except Exception:
        (OUT/'ERROR.log').write_text(traceback.format_exc(),encoding='utf-8')
        raise
    finally:
        unchanged=all(sha(HERE/n)==h for n,h in protected.items())
        code_unchanged=all(sha(HERE/n)==h for n,h in sources.items())
        write('EXECUTION_RECEIPT.json',dict(start_utc=start,end_utc=now(),elapsed_seconds=time.perf_counter()-clock,
            exit_code=exit_code,protected_inputs_unchanged=unchanged,code_inputs_unchanged=code_unchanged,
            input_sha256=sources,output_sha256={str(p.relative_to(OUT)):sha(p) for p in OUT.iterdir() if p.is_file()}))

if __name__=='__main__': main()
