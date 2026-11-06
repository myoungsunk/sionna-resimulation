import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json,gzip,hashlib,collections,csv,math,statistics,subprocess,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(xs):
    xs=sorted(x for x in xs if x is not None)
    return dict(n=len(xs),min=min(xs),median=statistics.median(xs),max=max(xs)) if xs else dict(n=0)
allrows=[];hashes={};summary={}
for folder in sorted((root/'research/FP_SC_S2_RUN_20261106/RESULTS').iterdir()):
    cid=folder.name;data=[]
    for stage in ('S1','S2'):
        p=root/f'research/FP_SC_{stage}_RUN_20261106/RESULTS/{cid}/ROWS.json.gz'
        receipt=json.loads((p.parent/'RUN_RECEIPT.json').read_text());assert sha(p)==receipt['result_sha256']
        hashes[str(p.relative_to(root))]=sha(p);data.append(json.load(gzip.open(p,'rt')))
    s1,s2=data;indexed={(r['k'],r['mode']):r for r in s1};assert len(indexed)==len(s1)==len(s2)
    for e in s2:
        r=indexed[e['k'],e['mode']];d=r['decision'];assert e['raw_tap']==r['raw_tap'] and e['proposed_tap']==d['selected_tap']
        assert e['reference_valid'];ref=e['reference_tap'];raw=e['raw_tap'];sel=e['proposed_tap']
        er0=abs(raw-ref);er1=abs(sel-ref)
        cs=d['scores'];eligible=sorted([c for c in cs if c['selection_eligible']],key=lambda c:(c['score'],c['tap']))
        for c in cs:
            assert abs(c['score']-(.7*-math.log(max(c['support'],1e-12))+max(c['p'] or 0,c['m'] or 0)**2))<1e-9
        by={c['tap']:c for c in cs};rr=by.get(ref);rw=by.get(raw);best=eligible[0] if eligible else None
        row=dict(case=cid,k=e['k'],mode=e['mode'],raw=raw,selected=sel,reference=ref,raw_error=er0,selected_error=er1,reason=d['reason'],prepared_status=r['prepared_status'],ref_eligible=bool(rr and rr['selection_eligible']),ref_rank=next((i+1 for i,c in enumerate(eligible) if c['tap']==ref),None),raw_score=None if rw is None else rw['score'],ref_score=None if rr is None else rr['score'],best_tap=None if best is None else best['tap'],best_score=None if best is None else best['score'],margin=d['margin'],gain=None if not best or not rw else rw['score']-best['score'])
        for prefix,c in [('raw',rw),('ref',rr),('best',best)]:
            for key in ('support','p','m'):row[prefix+'_'+key]=None if c is None else c[key]
        allrows.append(row)
assert len(allrows)==25088
for family in ('Full','Native_LoS'):
 for mode in ('C','P','M','PM'):
    rows=[r for r in allrows if family in r['case'] and r['mode']==mode];errors=[r for r in rows if r['raw_error']>0];built=[r for r in errors if r['raw_score'] is not None]
    z=dict(n=len(rows),errors=len(errors),exact_recovered=sum(r['selected_error']==0 for r in errors),closer=sum(r['selected_error']<r['raw_error'] for r in errors),same_distance=sum(r['selected_error']==r['raw_error'] for r in errors),farther=sum(r['selected_error']>r['raw_error'] for r in errors),changed_errors=sum(r['selected']!=r['raw'] for r in errors),normal_damaged=sum(r['raw_error']==0 and r['selected_error']>0 for r in rows),reasons=dict(collections.Counter(r['reason'] for r in errors)),scored_errors=len(built),ref_eligible=sum(r['ref_eligible'] for r in errors),ref_best=sum(r['ref_rank']==1 for r in errors),raw_below_2=sum(r['raw_score']<2 for r in built),score_stats={key:stats([r[key] for r in errors]) for key in ('raw_score','ref_score','best_score','gain','margin')})
    if mode=='PM':
        z['ref_best_reasons']=dict(collections.Counter(r['reason'] for r in errors if r['ref_rank']==1))
        z['by_reason']={reason:dict(n=len(rs),raw_score=stats([r['raw_score'] for r in rs]),gain=stats([r['gain'] for r in rs]),margin=stats([r['margin'] for r in rs]),raw_below_2=sum(r['raw_score'] is not None and r['raw_score']<2 for r in rs),gain_below_point8=sum(r['gain'] is not None and r['gain']<.8 for r in rs),ref_best=sum(r['ref_rank']==1 for r in rs)) for reason in z['reasons'] for rs in [[r for r in errors if r['reason']==reason]]}
        z['routes']={route:dict(errors=len(rs),recovered=sum(r['selected_error']==0 for r in rs),closer=sum(r['selected_error']<r['raw_error'] for r in rs),changed=sum(r['selected']!=r['raw'] for r in rs)) for route in ('R2','R4','R5') for rs in [[r for r in errors if r['case'].startswith(route)]]}
    summary[family+'_'+mode]=z
report=dict(question_id='S2-ALL-ERROR-ATTRITION',role='AUDITOR_SELF_CHECK',independent_audit=False,head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),governance_sha256=sha(Path('C:/Users/Myoungsun Kim/.codex/research-governance/COMMON_CONTRACT.md')),source_hashes=hashes,checks='25088 exact keys/source hashes/selection joins/reference-valid/score formula; saved S2 reference used, no stage rerun',summary=summary)
(out/'SUMMARY.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
with (out/'ROWS.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
print(json.dumps(summary['Full_PM'],indent=2));print('OTHER',[(k,v['errors'],v['exact_recovered'],v['changed_errors']) for k,v in summary.items()])
