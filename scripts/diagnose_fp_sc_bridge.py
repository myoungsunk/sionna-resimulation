"""Archived-pool nonrecursive bridge diagnostic; never calls select/history/EKF."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import pathlib
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from dataclasses import asdict
R=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup.bridge import adapt_pool, BridgeConfig, candidate_config_sha, RECIPE_SHA
from qclean_uwb.fp_sc.candidates import _digest

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def check(ok,message):
    if not ok:raise AssertionError(message)
def independent_score(record,tap,peak):
    # Separate scalar accumulation, not a call to the adapter scoring path.
    old=new=0.
    for s in record['support_records']:
        old=max(old, min(1.,s['prominence']/peak)/math.exp(abs(tap-s['edge_tap'])))
        strength=s['left_rise'] if s.get('support_kind')=='LEFT_RISE' else s['prominence']
        amplitude=s['tap_amplitude'];height=s['peak_amplitude']
        new=max(new,(strength if strength<peak else peak)*(amplitude if amplitude<height else height)/(peak*height))
    return old,new

def main(source,out,contract):
    out.mkdir(parents=True,exist_ok=False)
    started=datetime.now(timezone.utc).isoformat();begin=time.perf_counter()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
    code=[R/'scripts/diagnose_fp_sc_bridge.py',R/'tests/test_fp_sc_bridge.py',contract,
          *sorted((R/'src/qclean_uwb/fp_sc/followup').glob('*.py')),
          R/'src/qclean_uwb/fp_sc/candidates.py',R/'src/qclean_uwb/fp_sc/candidate_revision.py']
    lock={str(p.relative_to(R)):sha(p) for p in code}
    for p in code:
        gitbytes=subprocess.check_output(['git','show',head+':'+p.relative_to(R).as_posix()],cwd=R)
        check(hashlib.sha256(gitbytes).hexdigest()==sha(p),'CODE_NOT_COMMITTED:'+str(p))
    inputs={};base_keys=None;summary={};totals=Counter();max_error=0.;allrows=[]
    write(out/'EXECUTION_LOCK.json',dict(commit=head,code=lock,contract_sha256=sha(contract),recipe_sha256=RECIPE_SHA,
        source=str(source),primary='VAB',rows=50560,E2_GO=False,selector_real_calls=0,history_real_calls=0,
        scope='ARCHIVED_POOL_NONRECURSIVE_BRIDGE',utc_start=started,python=sys.version,platform=platform.platform()))
    for arm in ('V0','VA','VB','VAB'):
        t0=time.perf_counter();run=source/arm
        for name in ('POOLS.ndjson.gz','PACKET_CANDIDATE_COVERAGE.csv','ARTIFACT_HASHES.json'):
            inputs[str((run/name).relative_to(R))]=sha(run/name)
        registry=json.loads((run/'ARTIFACT_HASHES.json').read_text())
        for name in ('POOLS.ndjson.gz','PACKET_CANDIDATE_COVERAGE.csv'):
            check(sha(run/name)==registry[name],'SOURCE_HASH_MISMATCH')
        labels=list(csv.DictReader((run/'PACKET_CANDIDATE_COVERAGE.csv').open()))
        lookup={(r['packet_uid'],r['mode']):r for r in labels};check(len(lookup)==len(labels)==12640,'DUPLICATE_OR_COUNT')
        if base_keys is None:base_keys=set(lookup)
        check(set(lookup)==base_keys,'ARM_KEYS_DIFFER')
        seen=set();packet_ids=set();counts=Counter();routes=defaultdict(Counter);burden=defaultdict(list)
        with gzip.open(run/'POOLS.ndjson.gz','rt',encoding='utf-8') as src,gzip.open(out/(arm+'_CANDIDATES.ndjson.gz'),'xt',encoding='utf-8') as dst:
            for line in src:
                trace=json.loads(line);uid=trace['packet_uid'];check(uid not in packet_ids,'DUPLICATE_PACKET');packet_ids.add(uid)
                for mode,p in trace['pools'].items():
                    key=(uid,mode);check(key in lookup and key not in seen,'KEY_MISMATCH');seen.add(key)
                    full={**p,'lobes':[l for l in trace['lobes'] if mode=='TWO_PORT_UNION' or l['rx']==p['raw']['rx']]}
                    claimed=full.pop('pool_hash');check(_digest(full)==claimed,'POOL_HASH_MISMATCH')
                    cfg=BridgeConfig(arm,mode,candidate_config_sha(arm,p['config']))
                    e=adapt_pool(p,cfg)  # Labels/ref/route are NOT inputs.
                    identity=json.loads(e.bridge_identity_json)
                    check(identity['raw_json']==p['raw'],'RAW_LOSS')
                    check(identity['candidate_metadata']==[{k:v for k,v in r.items() if k!='support_records'} for r in p['candidates']],'METADATA_LOSS')
                    check(e.pool_hash==p['pool_hash'] and e.valid==p['raw']['valid'] and e.overflow==p['overflow'],'POOL_LOSS')
                    check(not e.selector_ready,'UNSAFE_SELECTOR_READY')
                    check([c.tap for c in e.candidates]==p['candidate_taps'],'TAP_LOSS')
                    check([c.tap for c in e.candidates if c.supported]==p['supported_taps'],'SUPPORT_LOSS')
                    legacy_taps=set();eligible_taps=set();candidates=[]
                    for r,c in zip(p['candidates'],e.candidates,strict=True):
                        check(json.loads(c.support_records_json)==r['support_records'],'PROVENANCE_LOSS')
                        check(list(c.groups)==r['group_ids'] and c.source_signed_s==r['signed_s'],'GROUP_OR_S_LOSS')
                        expected=bool(p['raw']['valid'] and not p['overflow'] and r['polarization_valid'] and r['supported'])
                        check(c.selection_eligible==expected,'ELIGIBILITY_MISMATCH')
                        old,new=independent_score(r,c.tap,p['raw'].get('peak',1.))
                        err=max(abs(old-c.legacy_support),abs(new-c.support));max_error=max(max_error,err)
                        check(err<=2e-15,'SCORE_MISMATCH')
                        if expected:eligible_taps.add(c.tap)
                        if p['raw']['valid'] and not p['overflow'] and c.supported and c.legacy_support>=.15:legacy_taps.add(c.tap)
                        counts['candidates']+=1;counts['eligible_candidates']+=expected
                        counts['excluded:'+c.exclusion_reason]+=not expected
                        s=r['support_records']
                        candidates.append(dict(tap=c.tap,cir_supported=c.supported,eligible=c.selection_eligible,
                            reason=c.exclusion_reason,legacy_support=c.legacy_support,proposed_rf_score=c.support,
                            groups=list(c.groups),rx=sorted({v['rx'] for v in s}),
                            kinds=sorted({v.get('support_kind','BILATERAL') for v in s}),
                            nearest_edge=min((abs(c.tap-v['edge_tap']) for v in s),default=None)))
                    # Evaluation-only join AFTER complete Evidence construction/checking.
                    r=lookup[key];ref=int(r['reference_tap']) if r['reference_tap'] else None
                    ref_valid=r['reference_valid']=='True'
                    source_usable=r['reference_usable']=='True'
                    ref_new=ref_valid and ref in eligible_taps;ref_old=ref_valid and ref in legacy_taps
                    check(ref_new==source_usable,'REFERENCE_CONNECTION_LOSS')
                    row=dict(arm=arm,packet_uid=uid,mode=mode,corpus=r['corpus'],channel=r['channel'],route=r['route'],
                        normal=r['normal'],wrong=r['wrong'],large_error=r['large_error'],reference_tap=ref,
                        generated_count=len(e.candidates),supported_count=sum(c.supported for c in e.candidates),
                        legacy_eligible_count=len(legacy_taps),revised_eligible_count=len(eligible_taps),
                        reference_source_usable=source_usable,reference_legacy_eligible=ref_old,reference_revised_eligible=ref_new,
                        pool_hash=e.pool_hash,evidence_sha256=_digest(asdict(e)),phase_available=False)
                    allrows.append(row);counts['rows']+=1;counts['reference_source_usable']+=source_usable
                    counts['reference_legacy_eligible']+=ref_old;counts['reference_revised_eligible']+=ref_new
                    if r['corpus']=='dynamic' and r['channel']=='Full' and mode=='TWO_PORT_UNION' and r['large_error']=='True':
                        for route in ('ALL',r['route']):
                            routes[route]['denominator']+=1;routes[route]['source_usable']+=source_usable
                            routes[route]['legacy_eligible']+=ref_old;routes[route]['revised_eligible']+=ref_new
                    group=(r['corpus'],r['channel'],mode,'normal' if r['normal']=='True' else 'wrong' if r['wrong']=='True' else 'other')
                    burden[group].append((len(e.candidates),len(legacy_taps),len(eligible_taps)))
                    dst.write(json.dumps(dict(packet_uid=uid,mode=mode,pool_hash=e.pool_hash,candidates=candidates),separators=(',',':'))+'\n')
                if len(packet_ids)%1000==0:print(arm,len(packet_ids),flush=True)
        check(seen==base_keys and len(packet_ids)==6320,'INCOMPLETE_ARM')
        summary[arm]=dict(counts=counts,primary_routes=routes,elapsed_s=time.perf_counter()-t0,
            burden=[dict(corpus=k[0],channel=k[1],mode=k[2],population=k[3],n=len(v),
                mean_generated=sum(x[0] for x in v)/len(v),mean_legacy_eligible=sum(x[1] for x in v)/len(v),
                mean_revised_eligible=sum(x[2] for x in v)/len(v),max_generated=max(x[0] for x in v)) for k,v in sorted(burden.items())])
        totals.update(counts);print('ARM_COMPLETE',arm,dict(routes['ALL']),flush=True)
    check(len(allrows)==50560,'TOTAL_COUNT')
    with (out/'PACKET_BRIDGE.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(allrows[0]));writer.writeheader();writer.writerows(allrows)
    write(out/'INPUT_HASHES.json',inputs)
    result=dict(status='PASS_CONNECTION_LOSSLESS_ONLY',primary='VAB',rows=len(allrows),arms=summary,
        comparisons=dict(candidate_records=totals['candidates'],preservation_mismatches=0,eligibility_mismatches=0,
                         score_mismatches=0,score_max_abs_error=max_error,score_abs_tolerance=2e-15),
        selector_real_calls=0,history_real_calls=0,new_RF_runs=0,E2_started=False,E2_GO=False,
        selector_adoption='HOLD_SAFETY_NOT_VALIDATED',phase='NOT_IN_ARCHIVED_POOLS_EXPLICITLY_UNAVAILABLE',
        self_review=True,external_independent_accept=False,utc_start=started,utc_end=datetime.now(timezone.utc).isoformat(),
        elapsed_s=time.perf_counter()-begin,implementation_commit=head)
    write(out/'SUMMARY.json',result)
    write(out/'ARTIFACT_HASHES.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print('PASS_CONNECTION_LOSSLESS_ONLY',len(allrows),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--contract',type=pathlib.Path,required=True)
    a=p.parse_args();main(a.source.resolve(),a.output.resolve(),a.contract.resolve())
