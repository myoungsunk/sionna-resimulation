"""Paired all-corpus revision gates and descriptive workload report."""
import csv,gzip,json,pathlib,sys,hashlib
from collections import defaultdict
import numpy as np

def read(path):return json.loads(path.read_text())
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def stats(values):return {'n':len(values),'median':float(np.median(values)) if values else None,'p95':float(np.percentile(values,95)) if values else None,'max':max(values) if values else None}

def finalize(root):
    arms=('V0','VA','VB','VAB');results={};failures=[];oldrows=None
    for arm in arms:
        run=root/arm;review=read(root/(arm+'_CHECK')/'CHECK.json')
        assert review['mismatches']==0 and review['rows']==12640
        rows=list(csv.DictReader((run/'PACKET_CANDIDATE_COVERAGE.csv').open()))
        keyed={(r['packet_uid'],r['mode']):r for r in rows};assert len(keyed)==12640
        if arm=='V0':oldrows=keyed
        assert set(keyed)==set(oldrows)
        regressions=[];overflows=[]
        for key,r in keyed.items():
            old=oldrows[key]
            if old['reference_usable']=='True' and r['reference_usable']!='True':regressions.append(list(key))
            if old['raw_valid']=='True' and old['overflow']=='False' and r['overflow']=='True':overflows.append(list(key))
        lost_candidates=[];lost_support=[]
        with gzip.open(root/'V0/POOLS.ndjson.gz','rt') as a,gzip.open(run/'POOLS.ndjson.gz','rt') as b:
            for x,y in zip(a,b,strict=True):
                x=json.loads(x);y=json.loads(y);assert x['packet_uid']==y['packet_uid']
                for mode in x['pools']:
                    if not set(x['pools'][mode]['candidate_taps'])<=set(y['pools'][mode]['candidate_taps']):lost_candidates.append([x['packet_uid'],mode])
                    if not set(x['pools'][mode]['supported_taps'])<=set(y['pools'][mode]['supported_taps']):lost_support.append([x['packet_uid'],mode])
        burden=read(run/'BURDEN_ROWS.json');groups=defaultdict(list)
        for r in burden:
            label='normal' if r['normal'] else 'wrong' if r['wrong'] else 'other'
            for group in ('all',label):groups[(r['corpus'],r['channel'],r['mode'],group)].append(r)
        distributions=[{'corpus':k[0],'channel':k[1],'mode':k[2],'population':k[3],
                        'candidates':stats([r['candidate_count'] for r in rs]),'groups':stats([r['group_count'] for r in rs])} for k,rs in sorted(groups.items())]
        summary=read(run/'SUMMARY.json');manifest=read(run/'RUN_MANIFEST.json')
        reasons={'success_regressions':regressions,'new_overflows':overflows,'lost_candidate_rows':lost_candidates,'lost_support_rows':lost_support}
        write(root/(arm+'_REGRESSIONS.json'),reasons)
        numerical=summary['observed_gate']['status']=='OBSERVED_THRESHOLD_MET'
        passed=numerical and not any(reasons.values()) and summary['construction_checks']['raw_preserved_all']
        results[arm]={'rows':len(rows),'candidate_availability_gate':summary['observed_gate'],'primary':summary['primary_dynamic_full_two_port_union'],
                     'by_route':summary['primary_by_route'],'success_regressions':len(regressions),'new_overflows':len(overflows),
                     'lost_candidate_rows':len(lost_candidates),'lost_support_rows':len(lost_support),'group_merge_rows':review['group_merge_rows'],
                     'workload_distributions':distributions,'generation_seconds':manifest['generation_seconds'],
                     'generation_p95_ms':manifest['generation_p95_ms'],'elapsed_s':manifest['elapsed_s'],'max_rss_kib':manifest['max_rss_kib'],
                     'all_revision_gates_met':passed}
    result={'stage':'E1_CANDIDATE_REVISION_REVALIDATION','primary_arm':'VAB','rows':sum(r['rows'] for r in results.values()),
            'verdict':'SUPPORTED_EXPOSED_CANDIDATE_AVAILABILITY_ONLY' if results['VAB']['all_revision_gates_met'] else 'VAB_NOT_ACCEPTED',
            'arms':results,'old_E1_failure_preserved':True,'selector_connection':'OPEN_SEPARATE_ISSUE_NOT_CHANGED',
            'E2_GO':False,'E2_started':False,'external_independent_accept':False,
            'review_provenance':'SELF_REVIEW_WITH_SEPARATELY_CODED_SCALAR_CHECKER','unproven':['FP correction','EKF improvement','selection safety','unseen environment generalization']}
    assert result['rows']==50560;write(root/'FINAL_VERDICT.json',result)
    write(root/'ARTIFACT_HASHES.json',{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and p!=root/'ARTIFACT_HASHES.json'})
    print(result['verdict'],50560,flush=True)
if __name__=='__main__':finalize(pathlib.Path(sys.argv[1]))
