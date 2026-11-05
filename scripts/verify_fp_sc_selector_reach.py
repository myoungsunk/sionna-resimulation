"""Run the selector's real candidate-set path on all frozen rows. No decisions."""
import csv,gzip,json,pathlib,sys,subprocess,time,platform,hashlib,math
from collections import Counter,defaultdict
from dataclasses import asdict
from datetime import datetime,timezone
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup import selection as s
from qclean_uwb.fp_sc.followup.bridge import adapt_pool,BridgeConfig,candidate_config_sha,RECIPE_SHA
from qclean_uwb.fp_sc.followup.contracts import Policy,digest
from qclean_uwb.fp_sc.candidates import _digest

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def forbidden(*args,**kwargs):raise AssertionError('REAL_SELECTION_OR_HISTORY_FORBIDDEN')

def run(source,output,contract):
    output.mkdir(parents=True,exist_ok=False);start=time.perf_counter();utc=datetime.now(timezone.utc).isoformat()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();policy=Policy()
    code=[pathlib.Path(__file__).resolve(),contract,R/'tests/test_fp_sc_selector_reach.py',R/'tests/test_fp_sc_bridge.py',
          R/'src/qclean_uwb/fp_sc/candidates.py',R/'src/qclean_uwb/fp_sc/candidate_revision.py',
          *sorted((R/'src/qclean_uwb/fp_sc/followup').glob('*.py'))]
    hashes={p.relative_to(R).as_posix():sha(p) for p in code}
    for path,h in hashes.items():assert hashlib.sha256(subprocess.check_output(['git','show',head+':'+path],cwd=R)).hexdigest()==h,path
    write(output/'LOCK.json',dict(implementation_commit=head,code=hashes,policy=asdict(policy),policy_sha256=policy.sha,
        selector_recipe=s.SELECTOR_SET_RECIPE,bridge_recipe_sha256=RECIPE_SHA,primary='VAB',utc=utc,
        python=sys.version,platform=platform.platform(),command=sys.argv,stage='SELECTOR_SET_REACH_ONLY',E1_02_started=False,E2_started=False))
    # If this runner accidentally invokes a decision/history path, fail the run.
    s.select=forbidden;s.TrustedHistory.observe=forbidden;s.TrustedHistory.advance=forbidden
    arms={};inputs={};all_keys=None;total=0;candidates=0;score_error=0.;missing8=[];baseline={}
    fields=['arm','packet_uid','mode','corpus','channel','route','large_error','reference_tap','source_usable',
            'actual_set_contains_reference','expected_taps','actual_taps','excluded','candidate_set_sha256','pool_hash']
    with (output/'ACTUAL_SELECTOR_SETS.csv').open('x',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for arm in ('V0','VA','VB','VAB'):
            t=time.perf_counter();folder=source/arm;registry=json.loads((folder/'ARTIFACT_HASHES.json').read_text())
            for name in ('POOLS.ndjson.gz','PACKET_CANDIDATE_COVERAGE.csv'):
                h=sha(folder/name);assert h==registry[name];inputs[(folder/name).relative_to(R).as_posix()]=h
            rows=list(csv.DictReader((folder/'PACKET_CANDIDATE_COVERAGE.csv').open()))
            labels={(r['packet_uid'],r['mode']):r for r in rows};assert len(labels)==len(rows)==12640
            if all_keys is None:all_keys=set(labels)
            assert set(labels)==all_keys
            seen=set();waveforms=set();routes=defaultdict(Counter);counts=Counter()
            with gzip.open(folder/'POOLS.ndjson.gz','rt',encoding='utf-8') as f:
                for line in f:
                    log=json.loads(line);uid=log['packet_uid'];assert uid not in waveforms;waveforms.add(uid)
                    for mode,pool in log['pools'].items():
                        key=(uid,mode);assert key not in seen and key in labels;seen.add(key)
                        full={**pool,'lobes':[l for l in log['lobes'] if mode=='TWO_PORT_UNION' or l['rx']==pool['raw']['rx']]}
                        ph=full.pop('pool_hash');assert _digest(full)==ph
                        cfg=candidate_config_sha(arm,pool['config'])
                        e=adapt_pool(pool,BridgeConfig(arm,mode,cfg))
                        bind=s.SelectionBinding(arm,mode,cfg,RECIPE_SHA,policy.sha)
                        actual=s.prepare_candidate_set(e,'C',policy,binding=bind)
                        # Expected set calculated directly from frozen source fields,
                        # not from bridge flags or shared selector code.
                        expected=sorted(c['tap'] for c in pool['candidates'] if pool['raw']['valid'] and
                                        not pool['overflow'] and c['polarization_valid'] and c['supported'])
                        got=sorted(r['tap'] for r in actual.eligible)
                        assert got==expected and len(got)==len(set(got)),(arm,key,'SET_MISMATCH')
                        excluded=[r['tap'] for r in actual.excluded]
                        if actual.status=='BUILT':
                            assert set(got).isdisjoint(excluded)
                            assert set(got)|set(excluded)==set(pool['candidate_taps'])
                            assert len(actual.rows)==len(pool['candidates'])
                            assert [r['tap'] for r in actual.eligible]==[r['tap'] for r in sorted(actual.eligible,key=lambda r:(r['score'],r['tap']))]
                        # Separate scalar score comparison, no candidate threshold.
                        for c in pool['candidates']:
                            strength=[]
                            for rec in c['support_records']:
                                b=rec['left_rise'] if rec.get('support_kind')=='LEFT_RISE' else rec['prominence']
                                strength.append(min(b,pool['raw']['peak'])*min(rec['tap_amplitude'],rec['peak_amplitude'])/(pool['raw']['peak']*rec['peak_amplitude']))
                            q=max(strength,default=0.);expected_score=-math.log(max(q,1e-12))*policy.rf_weight
                            if actual.status=='BUILT':
                                row=next(r for r in actual.rows if r['tap']==c['tap'])
                                err=abs(row['score']-expected_score);score_error=max(score_error,err);assert err<=2e-14
                        # Evaluation-only join after real production set construction.
                        r=labels[key];ref=int(r['reference_tap']) if r['reference_tap'] else None
                        contains=r['reference_valid']=='True' and ref in got
                        assert contains==(r['reference_usable']=='True')
                        if arm=='V0':baseline[key]=r
                        if (r['corpus'],r['channel'],mode,r['large_error'])==('dynamic','Full','TWO_PORT_UNION','True'):
                            for route in ('ALL',r['route']):
                                routes[route]['n']+=1;routes[route]['in_actual_set']+=contains
                            if arm=='VAB' and baseline[key]['reference_usable']=='False':missing8.append(dict(packet_uid=uid,mode=mode,reference_tap=ref,in_actual_set=contains))
                        writer.writerow(dict(arm=arm,packet_uid=uid,mode=mode,corpus=r['corpus'],channel=r['channel'],route=r['route'],
                            large_error=r['large_error'],reference_tap=ref,source_usable=r['reference_usable'],actual_set_contains_reference=contains,
                            expected_taps=json.dumps(expected),actual_taps=json.dumps(got),excluded=json.dumps(actual.excluded),
                            candidate_set_sha256=actual.sha,pool_hash=ph))
                        total+=1;candidates+=len(pool['candidates']);counts['rows']+=1;counts['eligible']+=len(got);counts['excluded']+=len(excluded)
                    if len(waveforms)%1000==0:print(arm,len(waveforms),flush=True)
            assert seen==all_keys and len(waveforms)==6320
            assert {k:v['n'] for k,v in routes.items()}=={'ALL':87,'R2':19,'R4':14,'R5':54}
            arms[arm]=dict(counts=counts,routes=routes,elapsed_s=time.perf_counter()-t)
            print('ARM_PASS',arm,dict(routes['ALL']),flush=True)
    assert total==50560 and len(missing8)==8 and all(r['in_actual_set'] for r in missing8)
    write(output/'INPUT_HASHES.json',inputs)
    write(output/'SUMMARY.json',dict(status='PASS_ACTUAL_SELECTOR_SET_REACH',rows=total,candidate_records=candidates,
        arms=arms,missing8=missing8,set_mismatches=0,unauthorized_candidate_inclusions=0,score_max_abs_error=score_error,
        score_abs_tolerance=2e-14,primary='VAB',real_select_calls=0,history_calls=0,E1_02_started=False,E2_started=False,
        production_selection_adoption='HOLD',external_independent_accept=False,elapsed_s=time.perf_counter()-start,
        utc_start=utc,utc_end=datetime.now(timezone.utc).isoformat(),implementation_commit=head))
    write(output/'ARTIFACT_HASHES.json',{p.name:sha(p) for p in output.iterdir() if p.is_file()})
    print('PASS_ACTUAL_SELECTOR_SET_REACH',total,flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--contract',type=pathlib.Path,required=True)
    a=p.parse_args();run(a.source.resolve(),a.output.resolve(),a.contract.resolve())
