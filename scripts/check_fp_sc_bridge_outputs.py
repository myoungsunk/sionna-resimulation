"""Self-review of saved bridge rows, candidate traces, denominators and 8 misses."""
import argparse,csv,gzip,hashlib,json,pathlib
from collections import Counter,defaultdict

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def check(source,run,output):
    output.mkdir(parents=True,exist_ok=False)
    for name,h in read(run/'ARTIFACT_HASHES.json').items():
        assert sha(run/name)==h, name
    rows=list(csv.DictReader((run/'PACKET_BRIDGE.csv').open(encoding='utf-8')))
    keyed={(r['arm'],r['packet_uid'],r['mode']):r for r in rows}
    assert len(keyed)==len(rows)==50560
    summary=read(run/'SUMMARY.json');arms={};misses=[];trace_count=0
    for arm in ('V0','VA','VB','VAB'):
        expected={};routes=defaultdict(Counter);seen=set();totals=Counter()
        for r in rows:
            if r['arm']!=arm:continue
            expected[(r['packet_uid'],r['mode'])]=r
            totals['rows']+=1;totals['candidates']+=int(r['generated_count'])
            totals['eligible_candidates']+=int(r['revised_eligible_count'])
            for k in ('source_usable','legacy_eligible','revised_eligible'):
                totals['reference_'+k]+=r['reference_'+k]=='True'
            if (r['corpus'],r['channel'],r['mode'],r['large_error'])==('dynamic','Full','TWO_PORT_UNION','True'):
                for route in ('ALL',r['route']):
                    routes[route]['denominator']+=1
                    for k in ('source_usable','legacy_eligible','revised_eligible'):
                        routes[route][k]+=r['reference_'+k]=='True'
        assert len(expected)==12640 and dict(routes)==summary['arms'][arm]['primary_routes']
        for k,v in totals.items():assert v==summary['arms'][arm]['counts'][k],k
        with gzip.open(run/(arm+'_CANDIDATES.ndjson.gz'),'rt',encoding='utf-8') as f:
            for line in f:
                d=json.loads(line);key=(d['packet_uid'],d['mode']);assert key in expected and key not in seen;seen.add(key)
                r=expected[key];cs=d['candidates'];ref=int(r['reference_tap']) if r['reference_tap'] else None
                assert len(cs)==int(r['generated_count']) and sum(c['eligible'] for c in cs)==int(r['revised_eligible_count'])
                assert sum(c['cir_supported'] for c in cs)==int(r['supported_count'])
                assert sum(c['cir_supported'] and c['legacy_support']>=.15 for c in cs)==int(r['legacy_eligible_count'])
                assert any(c['tap']==ref and c['eligible'] for c in cs)==(r['reference_revised_eligible']=='True')
                assert any(c['tap']==ref and c['cir_supported'] and c['legacy_support']>=.15 for c in cs)==(r['reference_legacy_eligible']=='True')
                trace_count+=len(cs)
                if arm=='VAB' and (r['corpus'],r['channel'],r['mode'],r['large_error'])==('dynamic','Full','TWO_PORT_UNION','True'):
                    baseline=keyed[('V0',*key)]
                    if baseline['reference_source_usable']=='False':
                        c=next(c for c in cs if c['tap']==ref)
                        misses.append(dict(packet_uid=key[0],mode=key[1],route=r['route'],reference_tap=ref,**{k:v for k,v in c.items() if k!='tap'}))
        assert seen==set(expected)
        assert routes['ALL']['denominator']==87 and {k:v['denominator'] for k,v in routes.items() if k!='ALL'}=={'R2':19,'R4':14,'R5':54}
        arms[arm]=dict(routes)
    assert len(misses)==8 and all(r['eligible'] for r in misses)
    assert trace_count==summary['comparisons']['candidate_records']
    result=dict(status='ACCEPT_CONNECTION_DIAGNOSTIC_SELF_REVIEW',rows=50560,candidate_records=trace_count,
        mismatches=0,arms=arms,original_missing_8=misses,E2_started=False,external_independent_accept=False,
        run_index_sha256=sha(run/'ARTIFACT_HASHES.json'))
    (output/'CHECK.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'rows':50560,'candidates':trace_count,'mismatches':0,'missing8_legacy_eligible':sum(x['legacy_support']>=.15 for x in misses)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--run',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args();check(a.source,a.run,a.output)
