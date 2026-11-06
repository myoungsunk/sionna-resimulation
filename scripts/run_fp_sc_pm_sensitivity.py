"""Fixed-policy counterfactual sensitivity; NOT E1-02 or provider activation."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import argparse,csv,gzip,json,platform,subprocess,sys,time,traceback,unittest
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import psutil
proc=psutil.Process();proc.cpu_affinity(proc.cpu_affinity()[:3])
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup.contracts import Policy,Support,sha256,write_json,verify_files
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.detection import binding_for
from qclean_uwb.fp_sc.followup import selection,detection,engine,numerics
from qclean_uwb.fp_sc.followup.input_sensitivity import raw_score_grid,build_intervals,scenario_grid,MODES
B=R/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001'
PKG=B/'PM_INPUT_SENSITIVITY_R1_20261106'; OLD=B/'PRIOR_EVIDENCE_R2_20261106/RUN_001'; MAP=B/'DYNAMIC_MAPPING_R1_20261105/RUN_001'

def forbidden(*a,**k):raise AssertionError('REAL_DETECT_SELECT_HISTORY_MODEL_EKF_FORBIDDEN')

def stop_check():
    s=os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if s and Path(s).exists():raise RuntimeError('MANAGED_STOP_REQUESTED')

def metrics(flags,wrong,base_c,base_nominal):
    flags=np.asarray(flags);wrong=np.asarray(wrong);active=flags>=0;positive=flags==1
    rate=lambda a,b:float(a/b) if b else None
    nw=int(wrong.sum());nn=len(wrong)-nw
    tp=int((positive&wrong).sum());fp=int((positive&~wrong).sum())
    fn=int(((flags==0)&wrong).sum());tn=int(((flags==0)&~wrong).sum())
    hw=int(((flags<0)&wrong).sum());hn=int(((flags<0)&~wrong).sum())
    result=dict(n=len(flags),normal=nn,wrong=nw,tp=tp,fp=fp,tn=tn,fn=fn,held_wrong=hw,held_normal=hn,
        hypothetical_available_rate=rate(active.sum(),len(flags)),hold_rate=rate((~active).sum(),len(flags)),
        fpr_all=rate(fp,nn),tpr_all=rate(tp,nw),miss_burden_all=rate(fn+hw,nw),
        fpr_active=rate(fp,fp+tn),tpr_active=rate(tp,tp+fn),fnr_active=rate(fn,fn+tp))
    for label,base in [('vs_C',base_c),('vs_nominal',base_nominal)]:
        result[label]=dict(new_detection=int((positive&wrong&(base!=1)).sum()),
            new_false_alarm=int((positive&~wrong&(base!=1)).sum()),
            lost_detection_to_negative=int(((flags==0)&wrong&(base==1)).sum()),
            lost_detection_to_hold=int(((flags<0)&wrong&(base==1)).sum()))
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False);start=time.time();policy=Policy();grid=scenario_grid();assert len(grid)==64
    manifest=json.loads((B/'PRIOR_INTEGRITY_R1_20261105/PREPARATION_001/MANIFEST_PREP_ONLY.json').read_text())
    assert policy.sha==manifest['policy_sha256']
    inputs={s['online_npz']:manifest['input_files'][s['online_npz']] for s in manifest['cases'].values()}
    oldreceipt=json.loads((OLD/'RUN_RECEIPT.json').read_text());mapreceipt=json.loads((MAP/'RUN_RECEIPT.json').read_text())
    for path,expected in [(OLD/'C_ONLY_ONLINE.jsonl.gz',oldreceipt['files']['C_ONLY_ONLINE.jsonl.gz']),
                          (MAP/'NOMINAL.csv',mapreceipt['files']['NOMINAL.csv']),
                          (MAP/'STRESS.csv',mapreceipt['files']['STRESS.csv'])]:
        assert sha256(path)==expected;inputs[path.relative_to(R).as_posix()]=expected
    verify_files(R,inputs)
    sources=[Path(__file__),R/'tests/test_fp_sc_input_sensitivity.py',*sorted((R/'src/qclean_uwb/fp_sc/followup').glob('*.py')),
             R/'src/qclean_uwb/fp_sc/candidate_revision.py',R/'src/qclean_uwb/fp_sc/candidates.py']
    receipt=dict(status='STARTED',question_id='FP-SC-PM-INPUT-SENSITIVITY-R1',role='PROPOSER_IMPLEMENTER_SELF_CHECK',
        base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),
        contract_sha256=sha256(PKG/'CONTRACT_KO.md'),policy_sha256=policy.sha,scenarios=grid,modes=MODES,
        input_hashes=inputs,code_hashes={p.relative_to(R).as_posix():sha256(p) for p in sources},
        governance_hashes={n:sha256(Path('C:/Users/Myoungsun Kim/.codex/research-governance')/n) for n in
          ('COMMON_CONTRACT.md','ROLE_PROPOSER.md','ROLE_IMPLEMENTER.md')},
        started_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,cpu_affinity=proc.cpu_affinity(),
        python=platform.python_version(),numpy=np.__version__,E1_02_started=False,E2_started=False,VALID_constructed=0,
        independent_audit=False)
    write_json(out/'RUN_RECEIPT.json',receipt)
    try:
        suite=unittest.TestSuite([unittest.defaultTestLoader.discover(str(R/'tests'),pattern=p) for p in
                               ('test_fp_sc_input_sensitivity.py','test_fp_sc_prior_integrity.py')])
        with (out/'TESTS.log').open('w') as f:tests=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
        assert tests.wasSuccessful()
        selection.select=forbidden;selection.TrustedHistory.observe=forbidden;selection.TrustedHistory.support=forbidden
        detection.detect=forbidden;detection.detection_loop=forbidden;detection.RawDetectionHistory.observe_raw=forbidden
        engine.open_loop=forbidden;engine.OriginalAdapter=forbidden;numerics.update=forbidden
        with gzip.open(OLD/'C_ONLY_ONLINE.jsonl.gz','rt') as f:old={(r['case_id'],r['k']):r for r in map(json.loads,f) if r['corpus']=='dynamic'}
        with (MAP/'NOMINAL.csv').open() as f:nominal=list(csv.DictReader(f))
        with (MAP/'STRESS.csv').open() as f:stress=list(csv.DictReader(f))
        assert len(nominal)==6272 and len(stress)==43904
        assert len({(r['case_id'],r['k'],r['stress']) for r in stress})==43904
        assert sum(int(r['narrow_reference_exclusion']) for r in stress)==11095
        adapter=RevisionEvidenceAdapter('VAB','TWO_PORT_UNION');checks=[];total=0
        for cid,spec in manifest['cases'].items():
            stop_check()
            with np.load(R/spec['online_npz'],allow_pickle=False) as z:a={k:z[k] for k in ('Hrf','t','pose_id','ds')}
            n=spec['expected_rows'];total+=n;assert len(a['t'])==n
            rows=sorted([r for r in nominal if r['case_id']==cid],key=lambda r:int(r['k']))
            assert [int(r['k']) for r in rows]==list(range(n))
            assert np.array_equal(a['pose_id'],[int(r['pose_id']) for r in rows])
            assert np.max(abs(a['t']-np.array([float(r['t']) for r in rows])))<1e-10
            # Allowlist premeasurement mapping fields. No reference/stratum passed downstream.
            lo=np.array([float(r['low']) for r in rows]);hi=np.array([float(r['high']) for r in rows]);offset=np.array([float(r['offset']) for r in rows])
            legacy={(int(r['k']),r['stress']):{'low':r['low'],'high':r['high']} for r in stress if r['case_id']==cid}
            taps=np.array([old[(cid,k)]['raw_tap'] if old[(cid,k)]['raw_tap'] is not None else -1 for k in range(n)])
            shape=(64,n,4);scores=np.full(shape,np.nan);flags=np.full(shape,-1,dtype=np.int8);status=flags.copy()
            ps=np.full((64,n,2),np.nan);ms=ps.copy();hist=np.full((64,n),-1,dtype=np.int32);ages=np.full((64,n),np.nan)
            c_scores=np.full(n,np.nan);pool_hashes=[];maxerr=0.;checked=0
            for k in range(n):
                if k%100==0:stop_check()
                e=adapter.evidence(numerics.cir_from_spectrum(a['Hrf'][k]),spec['metadata']['noise_variance'])
                bind=binding_for(e,policy);c=selection.prepare_candidate_set(e,'C',policy,binding=bind)
                raw=next((r for r in c.rows if r['tap']==e.raw_tap),None);cs=None if raw is None else raw['score']
                prior=old[(cid,k)];assert e.raw_tap==prior['raw_tap'] and e.pool_hash==prior['pool_hash']
                assert cs==prior['wrong_score'];assert c.sha==prior['candidate_set_sha']
                pool_hashes.append(e.pool_hash);c_scores[k]=np.nan if cs is None else cs
                pp,mm,j,age=build_intervals(k,a['t'],a['ds'],taps,lo,hi,offset,legacy,grid,policy)
                sc,fl,st=raw_score_grid(e.raw_tap,cs,pp,mm,policy)
                scores[:,k]=sc;flags[:,k]=fl;status[:,k]=st;ps[:,k]=pp;ms[:,k]=mm;hist[:,k]=j;ages[:,k]=age
                # Every real waveform: actual scorer parity in all modes for nominal.
                for i,mode in enumerate(MODES):
                    p=Support(*pp[0],policy.mapping_slack_m,'DIAGNOSTIC_ONLY')
                    m=None if not np.isfinite(mm[0]).all() else Support(*mm[0],policy.mapping_slack_m,'UNTRUSTED_RAW_HISTORY_DIAGNOSTIC')
                    actual=selection.prepare_candidate_set(e,mode,policy,prior=p,motion=m,binding=bind)
                    ar=next((r for r in actual.rows if r['tap']==e.raw_tap),None)
                    if ar is None:assert fl[0,i]==-1
                    else:
                        err=abs(ar['score']-sc[0,i]);maxerr=max(maxerr,err);assert err<1e-10
                        assert fl[0,i]==int(ar['score']>=policy.wrong_cut)
                    checked+=1
            np.savez_compressed(out/(cid+'_ONLINE.npz'),scores=scores,flags=flags,status=status,p_bounds=ps,m_bounds=ms,
                history_j=hist,history_age=ages,raw_tap=taps,selected_tap=taps,c_score=c_scores,pool_hash=np.array(pool_hashes),
                pose_id=a['pose_id'],t=a['t'],ds=a['ds'],nominal_low=lo,nominal_high=hi,offset=offset,
                scenario_ids=np.array([g['id'] for g in grid]),modes=np.array(MODES))
            checks.append(dict(case_id=cid,n=n,C_baseline_exact=True,scorer_comparisons=checked,max_score_error=maxerr))
            print('ONLINE_COMPLETE',cid,n,flush=True)
        assert total==6272
        # All raw outputs frozen before joining reference labels to any metric.
        online_hashes={p.name:sha256(p) for p in out.glob('*_ONLINE.npz')};write_json(out/'ONLINE_HASHES_BEFORE_EVALUATION.json',online_hashes)
        summaries=[];blocks=[];regressions=[]
        for cid in manifest['cases']:
            with np.load(out/(cid+'_ONLINE.npz')) as z:flags=z['flags'];t=z['t'];raw=z['raw_tap']
            refs=sorted([r for r in nominal if r['case_id']==cid],key=lambda r:int(r['k']))
            ref=np.array([int(r['ref_tap']) for r in refs]);valid=np.array([int(r['ref_valid'])==1 for r in refs])&(raw>=0)
            err=abs(raw-ref);wrong=err!=0;eps=np.floor((t-t[0])/20).astype(int)
            np.savez_compressed(out/(cid+'_EVALUATOR.npz'),reference_tap=ref,label_valid=valid,error_taps=err,episode_id=eps)
            for s,g in enumerate(grid):
                strata={'all':valid,'normal':valid&(err==0),'one_tap':valid&(err==1),'large':valid&(err>=2)}
                if g['profile']!='constant' or g['event']!='none':
                    strata.update(before=valid&(np.arange(len(t))<len(t)//2),after=valid&(np.arange(len(t))>=len(t)//2))
                for i,mode in enumerate(MODES):
                    for name,take in strata.items():
                        summaries.append(dict(case_id=cid,scenario=g['id'],mode=mode,stratum=name,raw_rows=len(t),label_invalid=int((~valid).sum()),
                            **metrics(flags[s,take,i],wrong[take],flags[0,take,0],flags[0,take,i])))
                    for ep in np.unique(eps):
                        take=valid&(eps==ep);blocks.append(dict(case_id=cid,scenario=g['id'],mode=mode,episode=int(ep),
                            **metrics(flags[s,take,i],wrong[take],flags[0,take,0],flags[0,take,i])))
                    if g['legacy']:
                        excluded=np.array([int(r['narrow_reference_exclusion'])==1 for r in sorted(
                            [r for r in stress if r['case_id']==cid and r['stress']==g['legacy']],key=lambda r:int(r['k']))])
                        take=valid&excluded
                        regressions.append(dict(case_id=cid,scenario=g['id'],mode=mode,
                            **metrics(flags[s,take,i],wrong[take],flags[0,take,0],flags[0,take,i])))
        write_json(out/'SUMMARY.json',summaries);write_json(out/'EPISODES.json',blocks);write_json(out/'REGRESSION_11095.json',regressions)
        assert sum(r['n'] for r in regressions if r['mode']=='P')==11095
        receipt.update(status='COMPLETE_DIAGNOSTIC_ONLY_NOT_PROVIDER_OR_E1_02',source_rows=total,scenario_count=64,
            packet_scenario_mode_rows=total*64*4,tests=tests.testsRun,checks=checks,regression_exclusions=11095,
            elapsed_s=time.time()-start,peak_working_set=proc.memory_info().peak_wset,
            files={p.name:sha256(p) for p in out.iterdir() if p.name!='RUN_RECEIPT.json'})
    except BaseException:
        receipt.update(status='FAILED_PRESERVED',error=traceback.format_exc());raise
    finally:write_json(out/'RUN_RECEIPT.json',receipt)
    print(receipt['status'],flush=True)

if __name__=='__main__':main()
