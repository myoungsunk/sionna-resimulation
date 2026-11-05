"""CSV-only self-check for prior-integrity component evidence; no stage calls."""
import argparse,csv,gzip,json,hashlib
from pathlib import Path
from collections import Counter

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(run,out,baseline):
    out.mkdir(exist_ok=False)
    rec=json.loads((run/'RUN_RECEIPT.json').read_text());assert rec['status']=='PASS_COMPONENT_GUARDS_ONLY'
    for name,h in json.loads((run/'ARTIFACT_HASHES.json').read_text()).items():assert sha(run/name)==h
    old={(r['arm'],r['packet_uid'],r['mode']):r for r in csv.DictReader(baseline.open())}
    expected_primary={};seen=set();counts=Counter()
    with gzip.open(run/'CANDIDATE_RECHECK.csv.gz','rt') as f:
        for r in csv.DictReader(f):
            key=r['arm'],r['packet_uid'],r['mode'];assert key not in seen;seen.add(key)
            ref=old[key];taps=json.loads(r['eligible_taps']);all_taps=json.loads(r['candidate_taps'])
            assert taps==json.loads(ref['actual_taps'])
            assert all_taps==sorted(taps+[v['tap'] for v in json.loads(ref['excluded'])])
            assert r['baseline_match']=='True'
            if r['arm']=='VAB' and r['mode']=='TWO_PORT_UNION':expected_primary[r['packet_uid']]=taps
    assert seen==set(old) and len(seen)==50560
    # Join case/k to exact frozen packet identity, rather than trusting row totals.
    source=run.parent.parent/'DYNAMIC_MAPPING_R1_20261105/RUN_001/NOMINAL.csv'
    nominal={(r['case_id'],r['k']):r for r in csv.DictReader(source.open())}
    guard_seen=set();c_scores={}
    with gzip.open(run/'PROTECTION_RECHECK.csv.gz','rt') as f:
        for r in csv.DictReader(f):
            key=r['case_id'],r['k'],r['scenario'],r['integrity'],r['mode']
            assert key not in guard_seen;guard_seen.add(key)
            n=nominal[key[:2]];uid=f"dynamic:{n['route']}:{n['pose_id']}:{n['channel']}"
            assert json.loads(r['eligible_taps'])==expected_primary[uid]
            assert r['history_cleared']=='True'
            if r['mode']!='C':assert r['active_wrong_score']=='' and r['effective_mode']=='HOLD'
            else:
                assert r['effective_mode']=='C'
                first=c_scores.setdefault(key[:2],r['active_wrong_score']);assert first==r['active_wrong_score']
            counts[(r['integrity'],r['mode'],r['effective_mode'])]+=1
    scenarios=('NOMINAL','COV_001','X_PLUS','X_MINUS','Y_PLUS','Y_MINUS','YAW_PLUS','YAW_MINUS')
    expected={(*k,sc,st,m) for k in nominal for sc in scenarios for st in ('UNKNOWN','INVALID') for m in ('C','P','M','PM')}
    assert guard_seen==expected and len(guard_seen)==401408
    static=json.loads((run/'STATIC48.json').read_text());assert len(static)==48
    assert len({r['case_id'] for r in static})==48
    for r in static:assert r['mode']=='C' and r['prior'] is None and r['history'] is None
    mapping=json.loads((run/'MAPPING_RECHECK/GATE.json').read_text());assert all(mapping['gates'].values())
    result=dict(verdict='PASS_COMPONENT_GUARDS_ONLY',E1_02_gate='HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING',
        candidate_rows=50560,dynamic_packet_scenarios=50176,state_mode_checks=401408,static48=48,
        untrusted_P_M_PM_active_score_violations=0,history_guard_violations=0,candidate_changes=0,
        P_M_PM_usable_fraction=0.,coverage=[dict(integrity=k[0],mode=k[1],effective_mode=k[2],n=v) for k,v in sorted(counts.items())],
        E1_02_started=False,E2_started=False,independent_audit=False,run_receipt_sha256=sha(run/'RUN_RECEIPT.json'))
    (out/'GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('run','output','baseline'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();check(a.run,a.output,a.baseline)
