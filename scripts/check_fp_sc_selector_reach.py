"""Saved-output gate: no selector, mapping, history, RF or E2 invocation."""
import csv,json,pathlib,hashlib,subprocess
from collections import defaultdict,Counter

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def check(source,package,output):
    output.mkdir(parents=True,exist_ok=False);run=package/'RUN_001'
    for p,h in read(run/'ARTIFACT_HASHES.json').items():assert sha(run/p)==h,p
    labels={}
    for arm in ('V0','VA','VB','VAB'):
        rows=list(csv.DictReader((source/arm/'PACKET_CANDIDATE_COVERAGE.csv').open()))
        assert len(rows)==12640
        for r in rows:
            key=(arm,r['packet_uid'],r['mode']);assert key not in labels;labels[key]=r
    seen=set();routes=defaultdict(lambda:defaultdict(Counter));counts=defaultdict(Counter);missing8=[]
    with (run/'ACTUAL_SELECTOR_SETS.csv').open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key=(r['arm'],r['packet_uid'],r['mode']);assert key in labels and key not in seen;seen.add(key)
            label=labels[key];expected=json.loads(r['expected_taps']);actual=json.loads(r['actual_taps']);excluded=json.loads(r['excluded'])
            assert actual==expected==sorted(set(expected))
            assert not set(actual)&{v['tap'] for v in excluded}
            assert len(actual)+len(excluded)==int(label['candidate_count'])
            for field in ('corpus','channel','route','large_error','reference_tap','pool_hash'):assert r[field]==label[field],(key,field)
            assert r['source_usable']==label['reference_usable']==r['actual_set_contains_reference']
            arm=r['arm'];counts[arm]['rows']+=1;counts[arm]['eligible']+=len(actual);counts[arm]['excluded']+=len(excluded)
            if (r['corpus'],r['channel'],r['mode'],r['large_error'])==('dynamic','Full','TWO_PORT_UNION','True'):
                for route in ('ALL',r['route']):
                    routes[arm][route]['n']+=1;routes[arm][route]['in_actual_set']+=r['actual_set_contains_reference']=='True'
                if arm=='VAB' and labels[('V0',*key[1:])]['reference_usable']=='False':missing8.append(key[1:])
    assert seen==set(labels) and len(seen)==50560 and len(missing8)==8
    summary=read(run/'SUMMARY.json');tests=read(package/'TEST_RECEIPT.json')
    for arm in counts:
        assert dict(counts[arm])==summary['arms'][arm]['counts']
        assert dict(routes[arm])==summary['arms'][arm]['routes']
    assert summary['set_mismatches']==summary['unauthorized_candidate_inclusions']==0
    assert summary['score_max_abs_error']<=summary['score_abs_tolerance']
    assert tests['new_tests']==14 and tests['bridge_tests']==18 and tests['legacy_tests']==24
    assert tests['legacy_exact_decisions']==1000 and tests['failures']==0
    assert summary['real_select_calls']==summary['history_calls']==0
    assert summary['E1_02_started'] is False and summary['E2_started'] is False
    root=pathlib.Path(__file__).resolve().parents[1]
    protected=[source.parents[1].relative_to(root).as_posix(),package.parent.joinpath('BRIDGE_R1_20261105').relative_to(root).as_posix(),
        'src/qclean_uwb/fp_sc/candidates.py','src/qclean_uwb/fp_sc/candidate_revision.py','src/qclean_uwb/fp_sc/followup/contracts.py']
    assert not subprocess.check_output(['git','diff','ce4ae9c5a5bf6841fc2059f6bf0fcf0dad4e40fe','--name-only','--',*protected],cwd=root).strip()
    result=dict(verdict='PASS_THREE_REACH_CHECKS',checks={'actual_selector_synthetic':'PASS','all_50560_actual_sets':'PASS','completion_gate':'PASS'},
        rows=len(seen),candidate_records=summary['candidate_records'],eligible_records=sum(c['eligible'] for c in counts.values()),
        excluded_records=sum(c['excluded'] for c in counts.values()),set_mismatches=0,unauthorized_candidate_inclusions=0,
        primary='VAB',primary_routes=routes['VAB'],missing8=missing8,tests=56,legacy_exact_decisions=1000,
        preserved_records='UNCHANGED',production_selection_adoption='HOLD',E1_02_started=False,E2_started=False,
        external_independent_accept=False,self_review=True,run_index_sha256=sha(run/'ARTIFACT_HASHES.json'),checker_sha256=sha(pathlib.Path(__file__).resolve()))
    (output/'GATE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--package',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args();check(a.source.resolve(),a.package.resolve(),a.output.resolve())
