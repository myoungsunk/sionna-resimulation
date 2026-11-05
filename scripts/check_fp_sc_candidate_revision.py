"""Separately calculated scalar R1 checker; same-author self-review, no selector."""
import argparse,csv,gzip,hashlib,importlib.util,json,pathlib,sys,time
import numpy as np
R=pathlib.Path(__file__).resolve().parents[1]
E=pathlib.Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/E1_20261105')
spec=importlib.util.spec_from_file_location('scalar_e1',R/E/'audit/check_candidates.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)

def scalar(cir,arm):
    result=q.scalar_candidate_pools(cir)
    if arm=='V0' or not result['raw']['valid']:return result
    raw=result['raw'];a=raw['magnitudes'];G=raw['peak'];numeric=64*np.finfo(float).eps*G
    for l in result['lobes']:
        port=l['port'];p=l['peak_index'];v=l['left_local_valley'];h=l['peak_amplitude']
        if arm in ('VB','VAB') and l['reason']=='BELOW_PROMINENCE':
            if not l['boundary'] and h>=numeric and a[v,port]<.30*h and h-a[v,port]>=.06*G:
                crossing=next(t for t in range(v,p+1) if a[t,port]>=.30*h)
                l['edge_tap']=crossing;l['candidate_amplitude_floor']=max(numeric,.15*h)
                l['generated_taps']=[t for t in range(max(v,crossing-1),min(p,crossing+1)+1) if a[t,port]>=l['candidate_amplitude_floor']]
                l['reason']='LEFT_RISE_SUPPORTED'
        if l['generated_taps'] and arm in ('VA','VAB'):
            added=[]
            for t in range(l['edge_tap'],p+1):
                if a[t,port]>=l['candidate_amplitude_floor']:added.append(t)
            l['generated_taps']=sorted(set(l['generated_taps']+added))
    for mode in result['pools']:
        support={}
        selected=[l for l in result['lobes'] if l['generated_taps'] and (mode=='TWO_PORT_UNION' or l['port']==raw['rx'])]
        for l in selected:
            for t in l['generated_taps']:support.setdefault(t,[]).append((l['port'],l['peak_index']))
        ts=sorted(set(support)|{raw['tap']})
        result['pools'][mode]={'taps':ts,'supported_taps':sorted(support),'support':{t:sorted(v) for t,v in support.items()},
                               'overflow':len(ts)>64,'groups':q.basin_components(selected)}
    return result

def check(arm,run,output,lock):
    output.mkdir(parents=True,exist_ok=False);t0=time.monotonic()
    for p,h in json.loads(lock.read_text())['files'].items():assert q.digest_file(R/p)==h,p
    for e in json.loads((R/E/'INPUT_LOCK.json').read_text())['files']:assert q.digest_file(R/e['path'])==e['sha256']
    for p,h in json.loads((run/'ARTIFACT_HASHES.json').read_text()).items():assert q.digest_file(run/p)==h,p
    rows=list(csv.DictReader((run/'PACKET_CANDIDATE_COVERAGE.csv').open()));lookup={(r['packet_uid'],r['mode']):r for r in rows}
    assert len(lookup)==len(rows)==12640
    checks=q.Comparisons();expected_rows=[];seen=set();merges=[]
    with gzip.open(run/'POOLS.ndjson.gz','rt') as trace:
        for i,(meta,cir,refcir) in enumerate(q.locked_corpus(R)):
            log=json.loads(next(trace));assert log['packet_uid']==meta['packet_uid'];assert meta['packet_uid'] not in seen;seen.add(meta['packet_uid'])
            computed=scalar(cir,arm);baseline=q.scalar_candidate_pools(cir) if arm!='V0' else computed
            reference=q.original_raw_fields(refcir)
            logged_lobes={(l['rx'],l['peak_tap']):l for l in log['lobes']}
            checks.equal('lobe_count',len(logged_lobes),len(computed['lobes']))
            for l in computed['lobes']:
                actual=logged_lobes[(l['port'],l['peak_index'])]
                checks.fields('lobe',actual,{'candidate_taps':l['generated_taps'],'edge_tap':l['edge_tap'],'reason':l['reason'],
                                             'left_local_valley':l['left_local_valley'],'right_local_valley':l['right_local_valley'],
                                             'prominence':l['prominence'],'peak_amplitude':l['peak_amplitude']})
            for mode,pool in computed['pools'].items():
                actual=log['pools'][mode];key=(meta['packet_uid'],mode)
                checks.fields('pool',actual,{'candidate_taps':pool['taps'],'supported_taps':pool['supported_taps'],'overflow':pool['overflow']})
                checks.fields('raw',actual['raw'],{'tap':computed['raw']['tap'],'rx':computed['raw']['rx'],'valid':computed['raw']['valid']})
                groups={lobe:g for g,ls in enumerate(pool['groups']) for lobe in ls}
                checks.equal('candidate_count',len(actual['candidates']),len(pool['taps']))
                for cand,tap in zip(actual['candidates'],pool['taps']):
                    sources=pool['support'].get(tap,[])
                    ids=sorted(f'rx{rx}_peak{p}' for rx,p in sources)
                    power=np.abs(cir[tap])**2;den=float(power.sum())
                    checks.fields('candidate',cand,{'tap':tap,'supported':tap in pool['supported_taps'],'support_ports':sorted(set(rx for rx,p in sources)),
                        'lobe_ids':ids,'group_ids':sorted(set(groups[x] for x in ids)),'denominator':den,
                        'signed_s':float((power[0]-power[1])/den) if den>0 else None})
                    checks.equal('support_records',sorted((s['rx'],s['peak_tap']) for s in cand['support_records']),sources)
                    if arm!='V0':
                        for s in cand['support_records']:
                            l=logged_lobes[(s['rx'],s['peak_tap'])]
                            checks.fields('support_evidence',s,{'left_rise':float(abs(cir[s['peak_tap'],s['rx']])-abs(cir[l['left_local_valley'],s['rx']])),
                                'support_kind':'LEFT_RISE' if l['reason']=='LEFT_RISE_SUPPORTED' else 'BILATERAL'})
                labels=q.classify_availability(computed,reference,mode)
                qrow=lookup[key]
                for field,value in labels.items():checks.equal('packet:'+field,q.csv_value(qrow[field],value),value)
                expected_rows.append({**meta,'mode':mode,**labels})
                oldgroups=baseline['pools'][mode]['groups'];mapping={}
                for g,ls in enumerate(oldgroups):
                    dest={groups[x] for x in ls};checks.equal('old_group_not_split',len(dest),1);mapping[g]=next(iter(dest))
                merged=[sorted(g for g,d in mapping.items() if d==v) for v in sorted(set(mapping.values())) if sum(d==v for d in mapping.values())>1]
                if merged:merges.append({'packet_uid':meta['packet_uid'],'mode':mode,'old_groups_merged':merged,'mapping':mapping})
            if (i+1)%1000==0:print('CHECK',arm,i+1,flush=True)
        assert trace.readline()==''
    assert len(seen)==6320 and len(expected_rows)==12640
    aggregates=q.compare_aggregates(checks,run,expected_rows)
    result={'arm':arm,'role':'SELF_REVIEW_SEPARATE_SCALAR_CALCULATION','external_independent_accept':False,
            'waveforms':len(seen),'rows':len(expected_rows),'checked':checks.checked,'mismatches':checks.mismatches,'comparison_record':checks.record(),
            'elapsed_s':time.monotonic()-t0,'E2_GO':False,'aggregates':aggregates,'group_merge_rows':len(merges)}
    q.write_json_new(output/'CHECK.json',result);q.write_json_new(output/'GROUP_MERGES.json',merges)
    assert not checks.mismatches,'CHECK_MISMATCH'
    print('CHECK_PASS',arm,checks.checked,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',required=True);p.add_argument('--run',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--lock',type=pathlib.Path,required=True)
    a=p.parse_args();check(a.arm,a.run,a.output,a.lock)
