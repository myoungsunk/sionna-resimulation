import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import argparse,csv,gzip,importlib.util,json,platform,subprocess,sys,time,traceback,unittest,types
from collections import Counter
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import psutil
process=psutil.Process();process.cpu_affinity(process.cpu_affinity()[:3])
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup.contracts import Policy,Support,sha256,write_json,verify_files
from qclean_uwb.fp_sc.followup.integrity import PriorIntegrity,assess_prior,INTEGRITY_RECIPE
from qclean_uwb.fp_sc.followup import selection,detection,static_detection,engine,numerics,runner
from qclean_uwb.fp_sc.followup.bridge import adapt_pool,BridgeConfig,candidate_config_sha,RECIPE_SHA
from qclean_uwb.fp_sc.candidate_revision import generate_revision
from qclean_uwb.fp_sc.revision_corpus import production_cir
B=R/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001'
M=B/'DYNAMIC_MAPPING_R1_20261105'
PACKAGE=B/'PRIOR_INTEGRITY_R1_20261105'

def forbidden(*a,**k):raise AssertionError('REAL_STAGE_OR_DETECTION_OR_SELECTION_FORBIDDEN')

def tests(out):
    out.mkdir(exist_ok=False);total=0;details={}
    for name in ('test_fp_sc_prior_integrity.py','test_fp_sc_mapping_static.py','test_fp_sc_detection_prep.py','test_fp_sc_bridge.py','test_fp_sc_selector_reach.py'):
        suite=unittest.defaultTestLoader.discover(str(R/'tests'),pattern=name)
        with (out/(name+'.log')).open('x') as f:res=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
        details[name]=res.testsRun;total+=res.testsRun
        assert res.wasSuccessful(),name
    code=subprocess.check_output(['git','show','486f0b6c008e7a953ada75a03a941ffa46994985:tests/test_fp_sc_followup.py'],cwd=R)
    mod=types.ModuleType('prior_integrity_legacy');mod.__file__=str(R/'tests/test_fp_sc_followup.py')
    sys.modules[mod.__name__]=mod;exec(compile(code,mod.__file__,'exec'),mod.__dict__)
    with (out/'LEGACY.log').open('x') as f:res=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(mod.ReceiverSelectionTest))
    assert res.wasSuccessful();total+=res.testsRun;details['legacy']=res.testsRun
    write_json(out/'RECEIPT.json',dict(total_tests=total,details=details,failures=0,legacy_exact_decisions=1000))
    print('TESTS_PASS',total,flush=True)

def run(out):
    out.mkdir(exist_ok=False);started=time.monotonic();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
    receipt=dict(status='RUNNING',code_commit=head,command=sys.argv,started_utc=datetime.now(timezone.utc).isoformat(),
        contract_sha256=sha256(PACKAGE/'FROZEN_CONTRACT_KO.md'),integrity_recipe=INTEGRITY_RECIPE,
        cpu_affinity=process.cpu_affinity(),threads=1,python=platform.python_version(),platform=platform.platform(),
        E1_02_started=False,E2_started=False,real_detect_calls=0,real_select_calls=0,new_model_calls=0,EKF_calls=0,
        independent_audit=False)
    code_paths=[Path(__file__),*sorted((R/'src/qclean_uwb/fp_sc/followup').glob('*.py')),
                R/'src/qclean_uwb/fp_sc/candidates.py',R/'src/qclean_uwb/fp_sc/candidate_revision.py']
    receipt['code_hashes']={p.relative_to(R).as_posix():sha256(p) for p in code_paths}
    for p,h in receipt['code_hashes'].items():
        import hashlib
        assert hashlib.sha256(subprocess.check_output(['git','show',head+':'+p],cwd=R)).hexdigest()==h,p
    write_json(out/'RUN_RECEIPT.json',receipt)
    try:
        tests(out/'TESTS')
        subprocess.run([sys.executable,str(R/'scripts/check_fp_sc_dynamic_mapping.py'),'--run',str(M/'RUN_001'),
            '--static',str(M/'STATIC48'),'--tests',str(out/'TESTS/RECEIPT.json'),'--output',str(out/'MAPPING_RECHECK')],check=True,cwd=R)
        selection.select=forbidden;detection.detect=forbidden;detection.detection_loop=forbidden
        static_detection.detect=forbidden;static_detection.evaluate_static=forbidden
        engine.open_loop=forbidden;numerics.update=forbidden;runner.run=forbidden
        manifest=json.loads((M/'FINAL_PREPARATION_MANIFEST.json').read_text())
        verify_files(R,manifest['input_files'])
        static_detection.validate_static_specs(R,manifest)
        old=B/'SELECTOR_REACH_R2_20261105/RUN_001'
        expected_hash=json.loads((old/'ARTIFACT_HASHES.json').read_text())['ACTUAL_SELECTOR_SETS.csv']
        assert sha256(old/'ACTUAL_SELECTOR_SETS.csv')==expected_hash
        expected={(r['arm'],r['packet_uid'],r['mode']):r for r in csv.DictReader((old/'ACTUAL_SELECTOR_SETS.csv').open())}
        assert len(expected)==50560
        nominal=list(csv.DictReader((M/'RUN_001/NOMINAL.csv').open()))
        stresses=list(csv.DictReader((M/'RUN_001/STRESS.csv').open()))
        scenarios={}
        for r in nominal:scenarios[(r['case_id'],int(r['k']))]=[dict(r,stress='NOMINAL')]
        for r in stresses:scenarios[(r['case_id'],int(r['k']))].append(r)
        assert len(scenarios)==6272 and all(len(v)==8 for v in scenarios.values())
        policy=Policy();counts=Counter();seen=set();peak=0
        fields=['arm','packet_uid','mode','pool_hash','baseline_pool_hash_equal','eligible_taps','candidate_taps','baseline_match']
        guardfields=['case_id','k','scenario','integrity','mode','effective_mode','active_wrong_score','eligible_taps','diagnostic_status','diagnostic_raw_score','history_cleared']
        with gzip.open(out/'CANDIDATE_RECHECK.csv.gz','wt',newline='') as cf,gzip.open(out/'PROTECTION_RECHECK.csv.gz','wt',newline='') as gf:
            cw=csv.DictWriter(cf,fields);cw.writeheader();gw=csv.DictWriter(gf,guardfields);gw.writeheader()
            def check_wave(uid,cir):
                primary=None
                for arm in ('V0','VA','VB','VAB'):
                    pools=generate_revision(cir,arm)
                    for mode,pool in pools.items():
                        key=(arm,uid,mode);assert key not in seen;seen.add(key);oldrow=expected[key]
                        e=adapt_pool(pool,BridgeConfig(arm,mode,candidate_config_sha(arm,pool['config'])),cir)
                        binding=selection.SelectionBinding(arm,mode,candidate_config_sha(arm,pool['config']),RECIPE_SHA,policy.sha)
                        s=selection.prepare_candidate_set(e,'C',policy,binding=binding)
                        got=sorted(r['tap'] for r in s.eligible);wanted=json.loads(oldrow['actual_taps'])
                        allwanted=sorted(wanted+[r['tap'] for r in json.loads(oldrow['excluded'])])
                        assert got==wanted and sorted(pool['candidate_taps'])==allwanted,(key,'CANDIDATE_MISMATCH')
                        cw.writerow(dict(arm=arm,packet_uid=uid,mode=mode,pool_hash=pool['pool_hash'],
                            baseline_pool_hash_equal=pool['pool_hash']==oldrow['pool_hash'],eligible_taps=json.dumps(got),
                            candidate_taps=json.dumps(sorted(pool['candidate_taps'])),baseline_match=True))
                        counts['candidate_rows']+=1
                        counts['pool_hash_matches']+=pool['pool_hash']==oldrow['pool_hash']
                        if arm=='VAB' and mode=='TWO_PORT_UNION':primary=e
                return primary
            for cid,spec in manifest['cases'].items():
                import numpy as np
                with np.load(R/spec['online_npz'],allow_pickle=False) as z:
                    for k in range(len(z['t'])):
                        uid=f"dynamic:{spec['metadata']['route']}:{int(z['pose_id'][k])}:{spec['metadata']['channel']}"
                        e=check_wave(uid,production_cir(z['Hrf'][k]))
                        assessed=assess_prior(z['prior'][k],z['Pprior'][k],float(z['t'][k]),None if k==0 else float(z['t'][k-1]))
                        assert assessed.state=='UNKNOWN'
                        expected_taps=sorted(c.tap for c in e.candidates if c.selection_eligible)
                        for sc in scenarios[(cid,k)]:
                            prior=Support(float(sc['low']),float(sc['high']),.15,'HASH_LOCKED_MAPPING_R1_DIAGNOSTIC')
                            # Deliberately contaminated stale motion tests the guard; never called a trusted live history.
                            motion=prior
                            for state in (assessed,PriorIntegrity('INVALID','INJECTED_COMPONENT_NEGATIVE_CONTROL')):
                                for mode in ('C','P','M','PM'):
                                    p=detection.prepare_detection(e,mode,policy,prior=prior,motion=motion,integrity=state)
                                    assert sorted(r['tap'] for r in p.active.eligible)==expected_taps
                                    h=detection.RawDetectionHistory(t=-1.,detector_m=100.,offset_m=50.,streak=5)
                                    assert h.support(float(z['t'][k]),50.,policy,integrity=state) is None
                                    h.observe_raw(e,float(z['t'][k]),50.,prior,policy,integrity=state)
                                    cleared=h.t is None and h.detector_m is None and h.offset_m==0. and h.streak==0
                                    assert cleared
                                    if mode!='C':assert p.effective_mode=='HOLD' and p.active_wrong_score is None
                                    else:assert p.effective_mode=='C'
                                    raw=next((r for r in p.diagnostic.rows if r['tap']==e.raw_tap),None)
                                    gw.writerow(dict(case_id=cid,k=k,scenario=sc['stress'],integrity=state.state,mode=mode,
                                        effective_mode=p.effective_mode,active_wrong_score=p.active_wrong_score,
                                        eligible_taps=json.dumps(expected_taps),diagnostic_status=p.diagnostic.status,
                                        diagnostic_raw_score=None if raw is None else raw['score'],history_cleared=cleared))
                                    counts['state_mode_checks']+=1;counts['held_checks']+=mode!='C'
                        counts['dynamic_waveforms']+=1
                        if counts['dynamic_waveforms']%500==0:print('DYNAMIC',counts['dynamic_waveforms'],flush=True)
                        peak=max(peak,process.memory_info().rss)
                print('CASE_PASS',cid,flush=True)
            staticrows=[]
            for cid,spec in manifest['static_cases'].items():
                online,ev=static_detection.load_static(R,spec,manifest['input_files'])
                uid=f"static_g4:{online.condition_id}:{online.channel}"
                e=check_wave(uid,production_cir(online.spectrum))
                s=detection.prepare_detection(e,'C',policy)
                assert s.effective_mode=='C'
                staticrows.append(dict(case_id=cid,mode='C',eligible_taps=[r['tap'] for r in s.active.eligible],prior=None,history=None))
                counts['static_waveforms']+=1
            write_json(out/'STATIC48.json',staticrows)
        assert seen==set(expected) and counts['candidate_rows']==50560
        assert counts['state_mode_checks']==401408 and counts['held_checks']==301056
        assert counts['dynamic_waveforms']==6272 and counts['static_waveforms']==48
        receipt.update(status='PASS_COMPONENT_GUARDS_ONLY',counts=dict(counts),candidate_mismatches=0,
            untrusted_active_score_violations=0,history_guard_violations=0,primary='VAB',
            P_M_PM_usable_fraction=0.,E1_02_gate='HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING',
            peak_sampled_rss_bytes=peak,input_manifest_sha256=sha256(M/'FINAL_PREPARATION_MANIFEST.json'),
            baseline_sets_sha256=expected_hash)
    except Exception:
        receipt.update(status='FAILED_PRESERVED',error=traceback.format_exc());raise
    finally:
        receipt.update(elapsed_s=time.monotonic()-started,ended_utc=datetime.now(timezone.utc).isoformat())
        write_json(out/'RUN_RECEIPT.json',receipt)
        write_json(out/'ARTIFACT_HASHES.json',{p.relative_to(out).as_posix():sha256(p) for p in out.rglob('*') if p.is_file() and p.name!='ARTIFACT_HASHES.json'})
    print('PASS_COMPONENT_GUARDS_ONLY',dict(counts),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);args=a.parse_args();run(args.output.resolve())
