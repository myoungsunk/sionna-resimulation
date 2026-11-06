"""Apply B + fixed P-only 7.5 cm diagnostic; no M, replacement or EKF."""
import argparse,csv,gzip,hashlib,io,json,math,datetime,urllib.request
from pathlib import Path
REF='cecb38cbaa507ea08f597ae441dbd929c3b8a24e'
STEP=299792458/(1028*1950000)
RADIUS=.075
def p_only(b_tap,p_interval):
    if p_interval is None:return None
    lo,hi=p_interval['low'],p_interval['high']
    if not math.isfinite(lo+hi) or lo>hi:raise ValueError('INVALID_PRIOR_INTERVAL')
    return abs(b_tap*STEP-(lo+hi)/2)>RADIUS+1e-12
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,default=Path('_inputs'));ap.add_argument('--out',type=Path,default=Path('P_ONLY_RUN'));a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);hashes={}
    def get(path):
        p=a.cache/path
        if not p.exists():
            b=urllib.request.urlopen('https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/'+REF+'/'+path,timeout=60).read();p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        b=p.read_bytes();hashes[path]=hashlib.sha256(b).hexdigest();return b
    assert p_only(0,dict(low=-.075,high=.075)) is False
    assert p_only(1,dict(low=-.075,high=.075)) is True
    assert p_only(0,None) is None
    rows=[]
    for route,n in [('R2',979),('R4',742),('R5',1415)]:
        cid=route+'_B0_Full_10';stages={}
        for stage in ['S1','S2']:
            prefix=f'research/FP_SC_{stage}_RUN_20261106/RESULTS/{cid}/'
            receipt=json.loads(get(prefix+'RUN_RECEIPT.json'));b=get(prefix+'ROWS.json.gz');assert hashlib.sha256(b).hexdigest()==receipt['result_sha256']
            stages[stage]={r['k']:r for r in json.loads(gzip.decompress(b)) if r['mode']=='C'}
            assert sorted(stages[stage])==list(range(n))
        features=list(csv.DictReader(io.StringIO(get(f'research/FP_SC_MISSED_ONSET_T0T1_20261106/RUN_001/{cid}_FEATURES.csv').decode('utf-8-sig'))));assert len(features)==n
        for f in features:
            k=int(f['k']);r=stages['S1'][k];e=stages['S2'][k];b=int(f['TWO_PORT_GLOBAL30']);ref=int(f['reference'])
            assert e['reference_valid'] and ref==e['reference_tap'] and int(f['raw'])==r['raw_tap']
            scores={c['tap']:c['signed_s'] for c in r['decision']['scores']};raws=r['observations']['F00'][1];los=raws-e['errors']['F00'][1]
            flag=p_only(b,r['p_interval']);center=(r['p_interval']['low']+r['p_interval']['high'])/2
            assert flag==(not center-RADIUS-1e-12<=b*STEP<=center+RADIUS+1e-12)
            rows.append(dict(case=cid,k=k,t=r['t'],B=b,reference=ref,error=b-ref,P_center_m=center,P_radius_m=RADIUS,alarm=flag,LOS_S=los,B_S=scores[b],B_S_error=scores[b]-los,raw_S_error=raws-los))
    assert len(rows)==3136 and len({(r['case'],r['k']) for r in rows})==3136
    def stats(rs,key):
        v=[r[key] for r in rs];return dict(n=len(v),mae=sum(abs(x) for x in v)/len(v),rmse=math.sqrt(sum(x*x for x in v)/len(v)))
    errs=[r for r in rows if r['error']];norm=[r for r in rows if not r['error']];kept=[r for r in rows if r['alarm'] is False]
    assert len(errs)==999 and len(norm)==2137
    tp=sum(r['alarm'] is True for r in errs);fp=sum(r['alarm'] is True for r in norm)
    out=dict(question_id='B-PONLY-075-20261106',source_commit=REF,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),policy=dict(detector='B_TWO_PORT_GLOBAL30',P_final_radius_m=RADIUS,M_enabled=False,history_required=False,action='FLAG_ONLY_NO_FP_REPLACEMENT',boundary_tolerance_m=1e-12),TP=tp,FP=fp,FN=sum(r['alarm'] is False for r in errs),TN=sum(r['alarm'] is False for r in norm),held=sum(r['alarm'] is None for r in rows),recall=tp/999,FPR=fp/2137,retained=len(kept),all_B_S=stats(rows,'B_S_error'),retained_B_S=stats(kept,'B_S_error'),same_rows_raw_S=stats(kept,'raw_S_error'),first_packets=[r for r in rows if r['k']==0],input_hashes=hashes,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),limits=['Posthoc user-selected setting on exposed data; not independent validation.','P remains archived model prior, not a validated integrity provider.','No FP replacement, EKF or production deployment.'])
    (a.out/'SUMMARY.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    with (a.out/'ROWS.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({k:v for k,v in out.items() if k not in ['input_hashes','first_packets']},indent=2))
if __name__=='__main__':main()
