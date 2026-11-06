"""T0/T1 read-only waveform analysis. No model training, FP writes or EKF.
Fetch only immutable required source/payloads through the workflow token.
The token is never logged or forwarded to external payload URLs.
"""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
if hasattr(os,'sched_getaffinity'):
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:3])
import base64, collections, csv, gzip, hashlib, io, json, math, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
import numpy as np

REPO='myoungsunk/sionna-resimulation'
REF='e4930310987ca89c4ce7d71f33f1a7e3d799fddf'
BRANCH='analysis/fp-sc-missed-onset-t0t1-20261106'
PREFIX='research/FP_SC_MISSED_ONSET_T0T1_20261106'
OUT=Path('output'); CACHE=Path('_inputs'); SRC=Path('_pinned')
TOKEN=os.environ['GH_TOKEN']; API='https://api.github.com/repos/'+REPO
SOURCE_RECORDS={}; START=time.time()
STEP=299792458.0/(1028*1950000)

def sha(b):return hashlib.sha256(b).hexdigest()
def request(url,*,data=None,headers=None,method=None):
    h={'User-Agent':'FP-SC-T0T1-readonly'}
    h.update(headers or {})
    req=Request(url,data=data,headers=h,method=method)
    with urlopen(req,timeout=120) as r:return r.read()
def api(path,data=None,method=None):
    b=None if data is None else json.dumps(data).encode()
    return json.loads(request(API+path,data=b,method=method,headers={
        'Authorization':'Bearer '+TOKEN,'Accept':'application/vnd.github+json',
        'Content-Type':'application/json'}))
def get(path,*,expected=None):
    if path in SOURCE_RECORDS:
        b=(CACHE/path).read_bytes()
    else:
        meta=api('/contents/'+quote(path,safe='/')+'?ref='+REF)
        enc=meta.get('content','')
        if enc and meta.get('encoding')=='base64':b=base64.b64decode(enc)
        else:b=base64.b64decode(api('/git/blobs/'+meta['sha'])['content'])
        git_sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if git_sha!=meta['sha']:raise ValueError('GIT_BLOB_HASH:'+path)
        lfs=False
        if b.startswith(b'version https://git-lfs.github.com/spec/v1'):
            pointer=b.decode();oid=next(x[11:] for x in pointer.splitlines() if x.startswith('oid sha256:'))
            size=int(next(x[5:] for x in pointer.splitlines() if x.startswith('size ')))
            basic=base64.b64encode(('x-access-token:'+TOKEN).encode()).decode()
            batch=json.loads(request('https://github.com/'+REPO+'.git/info/lfs/objects/batch',
                data=json.dumps({'operation':'download','transfers':['basic'],
                    'objects':[{'oid':oid,'size':size}]}).encode(),headers={
                    'Authorization':'Basic '+basic,'Content-Type':'application/vnd.git-lfs+json',
                    'Accept':'application/vnd.git-lfs+json'}))
            obj=batch['objects'][0]
            if obj.get('error'):raise ValueError('LFS_UNAVAILABLE:'+path+':'+str(obj['error']))
            action=obj['actions']['download']
            b=request(action['href'],headers=action.get('header',{}))
            if len(b)!=size or sha(b)!=oid:raise ValueError('LFS_PAYLOAD_HASH:'+path)
            lfs=True
        target=CACHE/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
        SOURCE_RECORDS[path]={'git_blob_sha':meta['sha'],'payload_sha256':sha(b),'bytes':len(b),'lfs_payload_verified':lfs}
        print('INPUT_OK',path,len(b),flush=True)
    if expected is not None and sha(b)!=expected:raise ValueError('EXPECTED_SHA:'+path)
    return b
def js(path):return json.loads(get(path))
def save(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def savecsv(name,rows):
    if not rows:raise ValueError('EMPTY_OUTPUT:'+name)
    with (OUT/name).open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def bootstrap():
    for part in ['qclean_uwb','qclean_uwb/drivesim','qclean_uwb/fp_sc']:
        p=SRC/part;p.mkdir(parents=True,exist_ok=True);(p/'__init__.py').write_text('')
    for path in ['src/qclean_uwb/drivesim/observation.py','src/qclean_uwb/fp_sc/candidates.py','src/qclean_uwb/fp_sc/candidate_revision.py']:
        b=get(path);p=SRC/path[4:];p.write_bytes(b)
    sys.path.insert(0,str(SRC.resolve()))
    from qclean_uwb.drivesim import observation
    from qclean_uwb.fp_sc.candidates import CandidateConfig
    from qclean_uwb.fp_sc.candidate_revision import generate_revision
    return observation,CandidateConfig,generate_revision

def raw_scalar(c):
    a=np.abs(c);rx=0 if max(a[:,0])>=max(a[:,1]) else 1
    peak=max(a[:,rx]);return next(i for i,x in enumerate(a[:,rx]) if x>=.3*peak),rx

def features(c,noise,cfg_class,generate):
    # This function sees current CIR and declared noise only. No GT/prior/history.
    pool=generate(c,'VAB',cfg_class(noise_var_per_bin=float(noise)))['TWO_PORT_UNION']
    raw=pool['raw'];a=np.abs(c);floor=max(pool['noise_amplitude_floor'],pool['numeric_amplitude_floor'])
    supported={int(x['tap']) for x in pool['candidates'] if x['supported'] and x['polarization_valid']}
    ports=[];local=[]
    for rx in (0,1):
        peak=float(a[:,rx].max());ids=np.flatnonzero(a[:,rx]>=.3*peak) if peak>0 else []
        edge=int(ids[0]) if len(ids) else None
        ports.append(edge if edge is not None and peak>=floor and a[edge,rx]>=floor else None)
        eligible_edges=sorted({int(l['edge_tap']) for l in pool['lobes']
            if l['rx']==rx and l['eligible'] and l['edge_tap'] is not None
            and int(l['edge_tap']) in supported and a[int(l['edge_tap']),rx]>=floor})
        local.append(eligible_edges[0] if eligible_edges else None)
    usable=pool['usable'];port_values=[x for x in ports if x is not None];local_values=[x for x in local if x is not None]
    predictions={'RAW':int(raw['tap']),
      'VAB_MIN_SUPPORTED':min(supported) if supported and usable else None,
      'TWO_PORT_GLOBAL30':min(port_values) if port_values and usable else None,
      'TWO_PORT_LOCAL_EDGE':min(local_values) if local_values and usable else None}
    return dict(predictions=predictions,raw_rx=int(raw['rx']),port0=ports[0],port1=ports[1],
      local0=local[0],local1=local[1],peak0=float(a[:,0].max()),peak1=float(a[:,1].max()),
      noise_floor=float(floor),candidate_count=len(pool['candidates']),usable=usable)

def synthetic_checks(obs,cc,gen):
    c=np.zeros((1028,2),complex)
    c[10:16,0]=[.1,.3,.5,1,.4,0]
    c[5:11,1]=[.1,.2,.4,.6,.2,0]
    f=features(c,0,cc,gen)
    assert f['predictions']['RAW']==11 and f['predictions']['TWO_PORT_GLOBAL30']==6
    assert raw_scalar(c)[0]==int(obs.first_path_batch(c[None],1950000)['index'][0])
    z=np.zeros((1028,2),complex);fz=features(z,0,cc,gen)
    assert not fz['usable'] and fz['predictions']['TWO_PORT_LOCAL_EDGE'] is None
    # A quiet/null other port never vetoes a supported port.
    c[:,1]=0;f=features(c,0,cc,gen)
    assert f['port1'] is None and f['predictions']['TWO_PORT_GLOBAL30']==f['port0']
    return {'checks':3,'status':'PASS_SELF_SYNTHETIC','independent_audit':False}

def metric(rows,method):
    normal=[x for x in rows if x['raw_error']==0];errors=[x for x in rows if x['raw_error']!=0]
    fn=lambda x:x[method]
    alarm=lambda x:fn(x) is not None and fn(x)!=x['raw']
    tp=sum(alarm(x) for x in errors);fp=sum(alarm(x) for x in normal)
    available=[x for x in rows if fn(x) is not None]
    err=[abs(fn(x)-x['reference']) for x in available]
    missed=[x for x in errors if x['old_selected']==x['raw']]
    notalerted=[x for x in errors if x['old_raw_score'] is None or x['old_raw_score']<2]
    return {'n':len(rows),'raw_errors':len(errors),'raw_normals':len(normal),'available':len(available),
      'held':len(rows)-len(available),'tp_alert':tp,'fp_alert':fp,
      'recall':tp/len(errors) if errors else None,'fpr':fp/len(normal) if normal else None,
      'precision':tp/(tp+fp) if tp+fp else None,
      'hypothetical_exact':sum(fn(x)==x['reference'] for x in available),
      'wrong_to_exact':sum(fn(x)==x['reference'] for x in errors if fn(x) is not None),
      'wrong_closer':sum(abs(fn(x)-x['reference'])<abs(x['raw_error']) for x in errors if fn(x) is not None),
      'wrong_farther':sum(abs(fn(x)-x['reference'])>abs(x['raw_error']) for x in errors if fn(x) is not None),
      'normal_harmed_if_forced':fp,'unmodified_errors':len(missed),'unmodified_alerted':sum(alarm(x) for x in missed),
      'unmodified_would_reach_reference':sum(fn(x)==x['reference'] for x in missed),
      'old_unalerted_errors':len(notalerted),'old_unalerted_now_flagged':sum(alarm(x) for x in notalerted),
      'mean_abs_tap_error':float(np.mean(err)) if err else None,
      'p95_abs_tap_error':float(np.quantile(err,.95)) if err else None}

def main():
    OUT.mkdir(exist_ok=False);CACHE.mkdir(exist_ok=True)
    obs,cc,gen=bootstrap();checks=synthetic_checks(obs,cc,gen);save('SYNTHETIC_CHECKS.json',checks)
    oldpath='research/FP_SC_S2_ALL_ERROR_ANALYSIS_20261106/ROWS.csv'
    prior=list(csv.DictReader(io.StringIO(get(oldpath).decode('utf8-sig'))))
    if len(prior)!=25088:raise ValueError('ORIGINAL_ROWCOUNT')
    index={(r['case'],int(r['k'])):r for r in prior if r['mode']=='PM'}
    if len(index)!=6272:raise ValueError('ORIGINAL_UNIQUE_KEYS')
    allrows=[];parity={};case_summaries={};examples=[]
    for route,nexpected in [('R2',979),('R4',742),('R5',1415)]:
      for family in ['Full','Native_LoS']:
        cid=f'{route}_B0_{family}_10'
        m=js(f'research/FP_SC_S1_PREPARATION_20261106/FINAL_002/{cid}_S1_MANIFEST.json')
        spec=m['case'];lock=m['input_files']
        on_b=get(spec['online_npz'],expected=lock[spec['online_npz']]);ev_b=get(spec['evaluator_npz'],expected=lock[spec['evaluator_npz']])
        with np.load(io.BytesIO(on_b),allow_pickle=False) as f:
            H=f['Hrf'];t=f['t'];pose=f['pose_id']
        with np.load(io.BytesIO(ev_b),allow_pickle=False) as f:
            clean=f['clean_H'];te=f['t'];pe=f['pose_id']
        if len(t)!=nexpected or H.shape!=(nexpected,257,2) or clean.shape!=H.shape or not np.array_equal(t,te) or not np.array_equal(pose,pe):raise ValueError('INPUT_JOIN:'+cid)
        cir=obs.cir_batch(H);cl=obs.cir_batch(clean)
        n0=obs.first_path_batch(cir,1950000)['index'];nL=obs.first_path_batch(cl,1950000)['index']
        noise=float(spec['metadata']['noise_variance']);cr=[];bad=0
        for k in range(nexpected):
            old=index[(cid,k)];raw=int(n0[k]);ref=int(nL[k])
            if int(old['raw'])!=raw or int(old['reference'])!=ref:raise ValueError('OLD_DETECTOR_OR_LABEL_PARITY:'+cid+':'+str(k))
            f=features(cir[k],noise,cc,gen)
            scalar,rx=raw_scalar(cir[k])
            if scalar!=raw or rx!=f['raw_rx'] or f['predictions']['RAW']!=raw:raise ValueError('SCALAR_OR_POOL_RAW_PARITY')
            row=dict(case=cid,route=route,family=family,k=k,t=float(t[k]),pose_id=int(pose[k]),raw=raw,
              reference=ref,raw_error=raw-ref,old_selected=int(old['selected']),old_reason=old['reason'],
              old_raw_score=float(old['raw_score']) if old['raw_score'] else None,
              old_ref_rank=int(old['ref_rank']) if old['ref_rank'] else None,
              error_sign='LATE' if raw>ref else 'EARLY' if raw<ref else 'CORRECT',
              magnitude='GE2' if abs(raw-ref)>=2 else 'ONE' if raw!=ref else 'ZERO',
              **f['predictions'],**{key:value for key,value in f.items() if key!='predictions'})
            row['port_disagreement']=f['port0'] is not None and f['port1'] is not None and f['port0']!=f['port1']
            # No P or M, current or future labels were passed to feature extraction.
            cr.append(row)
        allrows.extend(cr);parity[cid]={'n':nexpected,'raw_exact':nexpected,'reference_exact':nexpected,'scalar_raw_exact':nexpected,'noise_variance':noise}
        case_summaries[cid]={method:metric(cr,method) for method in f['predictions']}
        savecsv(cid+'_FEATURES.csv',cr)
        print('CASE_COMPLETE',cid,json.dumps(case_summaries[cid]),flush=True)
        # Deterministic exposed illustrative cases, never used to choose detector parameters.
        if family=='Full':
          for sign in ('EARLY','LATE'):
            group=[r for r in cr if r['raw_error']!=0 and r['old_selected']==r['raw'] and r['error_sign']==sign]
            for typ,pred in [('NEW_ALERT',lambda r:r['TWO_PORT_LOCAL_EDGE'] is not None and r['TWO_PORT_LOCAL_EDGE']!=r['raw']),('MISSED',lambda r:r['TWO_PORT_LOCAL_EDGE']==r['raw'])]:
              matches=[r for r in group if pred(r)]
              if matches:
                r=matches[0];k=r['k'];examples.append(r)
                low=max(0,min(r['raw'],r['reference'],r['TWO_PORT_LOCAL_EDGE'] or r['raw'])-12)
                high=min(1027,max(r['raw'],r['reference'],r['port0'] or r['raw'],r['port1'] or r['raw'])+15)
                wave=[{'tap':i,'rx0_real':float(cir[k,i,0].real),'rx0_imag':float(cir[k,i,0].imag),'rx1_real':float(cir[k,i,1].real),'rx1_imag':float(cir[k,i,1].imag)} for i in range(low,high+1)]
                savecsv(f'EXAMPLE_{cid}_{k}_{typ}_CIR.csv',wave)
        del H,clean,cir,cl,on_b,ev_b
    full=[r for r in allrows if r['family']=='Full'];los=[r for r in allrows if r['family']=='Native_LoS']
    errors=[r for r in full if r['raw_error']!=0];miss=[r for r in errors if r['old_selected']==r['raw']]
    if len(full)!=3136 or len(los)!=3136 or len(errors)!=1003 or len(miss)!=998 or sum(r['raw_error']!=0 for r in los)!=0:raise ValueError('COHORT_CONTRACT_FAILURE')
    methods=['RAW','VAB_MIN_SUPPORTED','TWO_PORT_GLOBAL30','TWO_PORT_LOCAL_EDGE']
    summary={'status':'T0_T1_COMPLETE_SELF_CHECK_NOT_INDEPENDENT_AUDIT','source_commit':REF,
      'scope':'CIR_ONLY_DETECTION_DIAGNOSTIC_NO_FP_WRITES_NO_EKF_NO_NEW_RT',
      'cohort':{'Full':len(full),'errors':len(errors),'normal':len(full)-len(errors),'unchanged_errors':len(miss),'Native_LoS':len(los),
        'error_by_route':dict(collections.Counter(r['route'] for r in errors)),
        'error_by_sign':dict(collections.Counter(r['error_sign'] for r in errors)),
        'error_by_magnitude':dict(collections.Counter(r['magnitude'] for r in errors)),
        'old_final_reasons':dict(collections.Counter(r['old_reason'] for r in errors))},
      'Full':{m:metric(full,m) for m in methods},'Native_LoS':{m:metric(los,m) for m in methods},
      'by_case':case_summaries,
      'by_error_sign':{sign:{m:metric([r for r in full if r['error_sign'] in (sign,'CORRECT')],m) for m in methods} for sign in ('EARLY','LATE')},
      'FP_production_changes':0,'EKF_calls':0,'S3_calls':0,'training_calls':0,'independent_audit':False,
      'limitations':['All RF and labels were previously exposed; exploratory only.','Operational LoS detector reference, not continuous true TOA.','Thresholds unchanged; earliest supported edge is a hypothesis, not validated credibility.','An alert is not a correct FP replacement.','Adjacent taps/packets and repeated modes are not independent samples.'],
      'elapsed_s':time.time()-START,'logical_cpu_limit':len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
      'numpy':np.__version__,'python':sys.version}
    save('SUMMARY.json',summary);save('INPUT_HASHES.json',SOURCE_RECORDS);save('PARITY.json',parity);save('EXAMPLE_INDEX.json',examples)
    savecsv('MISSED_998.csv',miss)
    episodes=[]
    for route in ('R2','R4','R5'):
        prev=None;ep=None
        for r in [x for x in full if x['route']==route]:
            if r['raw_error']==0:prev=None;ep=None;continue
            consecutive=prev is not None and r['k']==prev['k']+1 and r['t']-prev['t']<=.201
            if not consecutive:
                ep={'route':route,'start_k':r['k'],'end_k':r['k'],'start_t':r['t'],'end_t':r['t'],'n':0,'local_edge_alerts':0,'max_abs_tap_error':0};episodes.append(ep)
            ep.update(end_k=r['k'],end_t=r['t'],n=ep['n']+1,local_edge_alerts=ep['local_edge_alerts']+int(r['TWO_PORT_LOCAL_EDGE'] is not None and r['TWO_PORT_LOCAL_EDGE']!=r['raw']),max_abs_tap_error=max(ep['max_abs_tap_error'],abs(r['raw_error'])))
            prev=r
    savecsv('ERROR_EPISODES.csv',episodes)
    report=['# T0/T1 두 RX 초기 에지 전수 진단','', '고정 원본 '+REF, '', '**자기검산 결과. FP 교체·EKF·S3·원래 E1-02/E2를 실행하지 않음.**','',
      f'Full {len(full)}개: 오류 {len(errors)} / 정상 {len(full)-len(errors)}; 미교체 오류 {len(miss)}. Native-LoS {len(los)}개.',
      '', '| 진단 | 오류 경보/1003 | 정상 오경보/2133 | 미교체998 경보 | 오류에서 참조와 일치할 가상 tap |', '|---|---:|---:|---:|---:|']
    for method in methods:
        q=summary['Full'][method];report.append(f"| {method} | {q['tp_alert']} | {q['fp_alert']} | {q['unmodified_alerted']} | {q['wrong_to_exact']} |")
    report+=['','경보는 원래 raw와 새 에지가 다르다는 진단이다. 잘못됐다는 확정이나 정정 성공과 구별한다. 기존 normal을 훼손할 위험도 동시에 보고한다.', '', 'VAB_MIN_SUPPORTED는 e-1을 포함할 수 있다. TWO_PORT_GLOBAL30는 각 포트 자체 peak30% crossing, TWO_PORT_LOCAL_EDGE는 VAB로 채택된 lobe의 실제 edge이다. 두 방법 모두 P/M/정답 없이 current CIR만 사용했다.','', '원래 오류 방향과 크기: '+json.dumps(summary['cohort'],ensure_ascii=False), '', '기존 참조/원래 detector를 전수 재현했으며 원시 payload는 INPUT_HASHES.json에 기록. 새로운 진단의 통계적 일반화/독립감사는 수행하지 않았다.']
    (OUT/'RESULTS_KO.md').write_text('\n'.join(report)+'\n',encoding='utf8')
    hashes={p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file()}
    save('ARTIFACT_HASHES.json',hashes)
    print('FINAL_SUMMARY',json.dumps({k:v for k,v in summary.items() if k not in ('by_case','by_error_sign')},ensure_ascii=False),flush=True)

def publish():
    # Create new files only in this analysis branch; do not modify any old evidence.
    for p in sorted(OUT.iterdir()):
        if not p.is_file():continue
        dest=PREFIX+'/RUN_001/'+p.name
        api('/contents/'+quote(dest,safe='/'),{'message':'Publish T0/T1 detection diagnostic '+p.name,
            'branch':BRANCH,'content':base64.b64encode(p.read_bytes()).decode()},method='PUT')
    print('PUBLISHED_NEW_ANALYSIS_ONLY',flush=True)

if __name__=='__main__':
    try:
        main()
        if '--publish' in sys.argv:publish()
    except Exception as exc:
        if OUT.exists():save('FAILURE.json',{'type':type(exc).__name__,'message':str(exc),'elapsed_s':time.time()-START,'scientific_success':False})
        raise
