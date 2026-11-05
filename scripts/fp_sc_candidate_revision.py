"""E1 candidate revision revalidation. No selector or E2 imports/calls."""
import argparse, csv, gzip, importlib.util, json, pathlib, resource, sys, time, traceback
from collections import defaultdict
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.candidate_revision import generate_revision, ARMS, REVISION
from qclean_uwb.fp_sc.revision_corpus import locked_corpus
from qclean_uwb.fp_sc.contracts import sha256, write_json, environment, git_head
import numpy as np

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
old=load('original_e1',R/'scripts/fp_sc_e1.py')
E=old.E1
ROOT=E/'CANDIDATE_REVISION_R1_20261105'
BASE=E/'RUN_SNOWBALL_20261105_0643/RUN_001'

def verify(lock_path):
    lock=json.loads(lock_path.read_text())
    assert lock['scope']=={'waveforms':6320,'modes':2,'arms':list(ARMS),'rows':50560,'selector_runs':0,'E2_GO':False}
    assert lock['primary']=='VAB' and lock['authorized_by']=='USER_CURRENT_REQUEST'
    assert git_head(R)==lock['implementation_commit']
    for p,h in lock['files'].items():
        assert sha256(R/p)==h, 'LOCK_DRIFT:'+p
    for entry in json.loads((R/E/'INPUT_LOCK.json').read_text())['files']:
        assert sha256(R/entry['path'])==entry['sha256'], 'INPUT_DRIFT:'+entry['path']
    env=environment()
    assert env['packages']==lock['environment']['packages'] and env['threads']==lock['environment']['threads']
    assert env['python']==lock['environment']['python'] and env['system']=='Linux'
    return lock,env

def run(arm,lock_path,output):
    lock,env=verify(lock_path);output.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();rows=[];burden=[];timings=[];seen=set()
    manifest={'revision':REVISION,'arm':arm,'stage':'E1_CANDIDATE_REVISION_REVALIDATION','utc_start':old.utc_now(),
              'status':'RUNNING','code_commit':git_head(R),'lock_sha256':sha256(lock_path),'environment':env,
              'command':sys.argv,'primary':'VAB','E2_GO':False,'selector_runs':0,'external_independent_accept':False}
    write_json(output/'RUN_MANIFEST.json',manifest)
    baseline={ (r['packet_uid'],r['mode']):r for r in csv.DictReader((R/BASE/'PACKET_CANDIDATE_COVERAGE.csv').open()) }
    try:
        with (output/'PACKET_CANDIDATE_COVERAGE.csv').open('x',newline='') as f, gzip.open(output/'POOLS.ndjson.gz','xt',encoding='utf-8') as g:
            w=csv.DictWriter(f,fieldnames=old.PACKET_FIELDS);w.writeheader()
            for i,(meta,cir,ref_cir) in enumerate(locked_corpus(R)):
                t=time.perf_counter();pools=generate_revision(cir,arm);timings.append(time.perf_counter()-t)
                ref=old.reference_observation(ref_cir)
                # Full trace, without duplicated per-mode lobe arrays.
                trace={'packet_uid':meta['packet_uid'],'lobes':pools['TWO_PORT_UNION']['lobes'],
                       'pools':{m:{k:v for k,v in p.items() if k!='lobes'} for m,p in pools.items()}}
                g.write(json.dumps(trace,separators=(',',':'),allow_nan=False)+'\n')
                for mode,pool in pools.items():
                    row={**meta,'mode':mode,**old.classify(pool,ref)}
                    key=(meta['packet_uid'],mode);assert key not in seen;seen.add(key)
                    assert row['raw_preserved']
                    if arm=='V0':
                        # CSV string representation parity includes pool hash and every original field.
                        for k,v in row.items():
                            text='' if v is None else str(v)
                            assert text==baseline[key][k],f'V0_PARITY:{key}:{k}:{text}:{baseline[key][k]}'
                    w.writerow(row);rows.append(row)
                    groups=sorted({gid for x in pool['candidates'] for gid in x['group_ids']})
                    burden.append({'packet_uid':meta['packet_uid'],'mode':mode,'corpus':meta['corpus'],'channel':meta['channel'],
                                   'route':meta['route'],'normal':row['normal'],'wrong':row['wrong'],'candidate_count':row['candidate_count'],
                                   'group_count':len(groups),'raw_valid':row['raw_valid']})
                if (i+1)%500==0:print(arm,'waveforms',i+1,flush=True)
        assert len(rows)==12640 and len(seen)==12640 and set(baseline)==seen
        summary,episodes,static=old.summarize(rows)
        if arm=='V0': assert summary==json.loads((R/BASE/'SUMMARY.json').read_text()),'V0_SUMMARY_PARITY'
        summary.update(schema='FP_SC_E1_CANDIDATE_R1_SUMMARY',stage='E1_CANDIDATE_REVISION_REVALIDATION',arm=arm)
        write_json(output/'SUMMARY.json',summary);write_json(output/'STATIC_COORDINATE_SUMMARY.json',static)
        write_json(output/'BURDEN_ROWS.json',burden)
        with (output/'EPISODES.csv').open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=old.EPISODE_FIELDS);w.writeheader();w.writerows(episodes)
        manifest.update(status='COMPLETED_PENDING_CHECK',waveforms=6320,packet_mode_rows=len(rows),exit_code=0,
                        generation_seconds=sum(timings),generation_p95_ms=float(np.percentile(timings,95)*1000),
                        elapsed_s=time.monotonic()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        manifest.update(status='FAILED_PRESERVED',exit_code=1,traceback=traceback.format_exc());raise
    finally:
        manifest['utc_end']=old.utc_now();write_json(output/'RUN_MANIFEST.json',manifest)
        write_json(output/'ARTIFACT_HASHES.json',{p.name:sha256(p) for p in output.iterdir() if p.is_file() and p.name!='ARTIFACT_HASHES.json'})
    print(arm,'COMPLETE',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=ARMS,required=True);p.add_argument('--lock',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args();run(a.arm,a.lock,a.output)
