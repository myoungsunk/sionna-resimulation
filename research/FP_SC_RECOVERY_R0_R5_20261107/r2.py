from pathlib import Path
import csv,json,math,hashlib,datetime,platform,collections,zipfile
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'RUN_002'
OUT=ROOT/'R2_RUN_001'
STEP=299792458/(1028*1950000)
EPS=1e-12
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,x): (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def choose(B,center,candidates,policy):
    # Input contract deliberately excludes cohort, reference, true pose and S.
    if policy=='K0':return B,'BASELINE'
    inside=lambda n:abs(n*STEP-center)<=.075+EPS
    if policy=='K1':
        x=center/STEP
        opts=[n for n in {math.floor(x),math.ceil(x)} if 0<=n<1028 and inside(n)]
        scores=[(abs(n*STEP-center),n) for n in opts]
    else:
        opts=[c for c in candidates if c['eligible'] and (policy=='K3' or inside(c['tap']))]
        scores=[(c['cost'],c['tap']) for c in opts]
    if not scores:return B,'NO_CANDIDATE'
    scores.sort()
    if len(scores)>1 and abs(scores[0][0]-scores[1][0])<=EPS:return B,'TIE'
    n=scores[0][1]
    if policy=='K3' and not inside(n):return B,'RF_P_DISAGREE'
    return n,'KEEP_B' if n==B else 'REPLACE'
def main():
    OUT.mkdir(exist_ok=False)
    governance=Path('C:/Users/Myoungsun Kim/.codex/research-governance')
    write('CONTRACT.json',dict(question_id='B-PONLY-RECOVERY-R2-20261107',role='IMPLEMENTER_SELF_CHECK',source_commit='fca24720524068badeab79b78098a244cebc62b5',local_analysis_script_sha256=sha(Path(__file__)),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=platform.python_version(),command='python r2.py',scope='R2 only; frozen 3136 rows and 689 alarms; no R3 metrics or EKF',radius_m=.075,M=False,tie_tolerance=EPS,policies={'K0':'retain B','K1':'nearest integer tap to fixed P center; no RF eligibility requirement','K2':'minimum existing RF cost among eligible RF candidates inside P','K3':'minimum existing RF cost among all eligible RF candidates, replace only if inside P'},abstention='retain B on absent/tied candidate or K3 mismatch; alarm remains',inputs={n:sha(SRC/n) for n in ['A_ALL_3136.csv','B_CANDIDATES.csv','SUMMARY.json']},governance={n:sha(governance/n) for n in ['COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md']}))
    old=json.loads((SRC/'ARTIFACT_HASHES.json').read_text())
    for n in ['A_ALL_3136.csv','B_CANDIDATES.csv','SUMMARY.json']:assert old[n]==sha(SRC/n)
    rows=list(csv.DictReader((SRC/'A_ALL_3136.csv').open(encoding='utf-8-sig')))
    pools=collections.defaultdict(list)
    for c in csv.DictReader((SRC/'B_CANDIDATES.csv').open(encoding='utf-8-sig')):
        pools[(c['case'],int(c['k']))].append(dict(tap=int(c['tap']),eligible=c['eligible']=='True',cost=float(c['RF_cost'])))
    assert len(rows)==3136 and len(pools)==689
    assert len({(r['case'],r['k']) for r in rows})==3136
    assert collections.Counter(r['cohort'] for r in rows)==dict(TP=678,FP=11,FN=321,TN=2126)
    # Boundary, abstention, and policy-distinction checks without evaluation labels.
    mid=10.5*STEP
    assert choose(9,mid,[],'K1')==(9,'TIE')
    assert choose(9,10*STEP,[],'K2')==(9,'NO_CANDIDATE')
    toy=[dict(tap=10,eligible=True,cost=2),dict(tap=12,eligible=True,cost=1)]
    assert choose(9,10*STEP,toy,'K2')[0]==10
    assert choose(9,10*STEP,toy,'K3')==(9,'RF_P_DISAGREE')
    assert choose(9,10*STEP,[dict(tap=10,eligible=True,cost=1)],'K3')[0]==10
    results=[]
    for r in rows:
        B=int(r['B']);ref=int(r['reference']);center=float(r['P_center_m'])
        alarm=abs(B*STEP-center)>.075+EPS
        assert alarm==(r['cohort'] in ['TP','FP'])
        candidates=pools.get((r['case'],int(r['k'])),[])
        for policy in ['K0','K1','K2','K3']:
            n,reason=choose(B,center,candidates,policy) if alarm else (B,'NONALARM_FIXED')
            before=abs(B-ref);after=abs(n-ref)
            outcome=('EXACT_RECOVERY' if after==0 else 'PARTIAL_IMPROVEMENT' if after<before else 'WORSENED' if after>before else 'ERROR_UNCHANGED') if before else ('NORMAL_HARM' if after else 'NORMAL_PROTECTED')
            results.append(dict(policy=policy,case=r['case'],k=r['k'],time_s=r['t'],cohort=r['cohort'],B=B,reference=ref,selected=n,changed=n!=B,reason=reason,outcome=outcome,before_abs_tap=before,after_abs_tap=after))
    stats={}
    for policy in ['K0','K1','K2','K3']:
        q=[r for r in results if r['policy']==policy];tp=[r for r in q if r['cohort']=='TP'];fp=[r for r in q if r['cohort']=='FP']
        count=lambda group,key:sum(r['outcome']==key for r in group)
        g=count(tp,'EXACT_RECOVERY');h=count(fp,'NORMAL_HARM')
        stats[policy]=dict(TP_exact=g,TP_exact_percent=100*g/678,TP_partial=count(tp,'PARTIAL_IMPROVEMENT'),TP_worsened=count(tp,'WORSENED'),TP_error_unchanged=count(tp,'ERROR_UNCHANGED'),TP_retained=sum(not r['changed'] for r in tp),FP_harmed=h,FP_protected=11-h,alarm_replaced=sum(r['changed'] for r in tp+fp),alarm_retained=sum(not r['changed'] for r in tp+fp),exact_after=sum(r['after_abs_tap']==0 for r in q),reasons=dict(collections.Counter(r['reason'] for r in tp+fp)))
        assert stats[policy]['exact_after']==2137+g-h
        assert all(not r['changed'] for r in q if r['cohort'] in ['TN','FN'])
        assert g+stats[policy]['TP_partial']+stats[policy]['TP_worsened']+stats[policy]['TP_error_unchanged']==678
    for name,subset in [('ROWS.csv',results),('FP11_POLICIES.csv',[r for r in results if r['cohort']=='FP'])]:
        with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(subset)
    write('SUMMARY.json',stats)
    write('CHECKS.json',dict(status='PASS',baseline_rows=3136,alarms=689,nonalarm_fixed_each_policy=2447,source_hashes='PASS',synthetic_boundary_and_abstention_checks='PASS',exact_count_identity='2137 + g - h verified',independent_audit=False,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=0))
    lines=['# R2: B + P 7.5 cm 고정 K0–K3 비교','', '기존 3,136행과 경보 689건을 고정한 오프라인 선택 비교. 비경보 2,447건은 모두 B 유지. 정답은 평가에만 사용하며 선택 함수 입력에서 제외했다. M·미래 프레임·LoS S·true pose를 사용하지 않았다.','', '|정책|TP 정확 복구 /678|부분 개선|오류 악화|오류 동일|FP 훼손 /11|FP 보호 /11|경보 교체|경보 유지|','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for p,v in stats.items():lines.append(f"|{p}|{v['TP_exact']} ({v['TP_exact_percent']:.2f}%)|{v['TP_partial']}|{v['TP_worsened']}|{v['TP_error_unchanged']}|{v['FP_harmed']}|{v['FP_protected']}|{v['alarm_replaced']}|{v['alarm_retained']}|")
    lines+=['','K0: B 유지. K1: P 중심 최근접 정수 tap(유효 CIR 후보를 요구하지 않는 진단 기준선). K2: P 안의 유효 RF 후보 중 기존 RF 비용 최솟값. K3: P를 넣지 않은 전체 유효 RF 후보의 비용 최솟값이 P 안에 있을 때만 교체. K3는 대안이 B보다 좋은지만 비교하는 규칙과 다르다.','', '거리 최근접 및 RF 비용 동률 허용오차는 1e-12. 동률·후보 부재·K3 불일치는 B 유지, 경보 유지. K0의 유지는 보류 판단이 아닌 기준 정책이다. RF 비용 함수·계수는 R1 저장값을 그대로 사용했다.','', 'FP 정상 보호는 이 11행에서 B를 유지했다는 뜻이며 일반화된 안전성 증명이 아니다. 정확 복구와 S 개선도 동일한 성과가 아니다. 거리/S MAE·RMSE 및 EKF를 계산하지 않았으며 R2까지만 실행했다.','', '[행별 4정책 결과](ROWS.csv) · [정상 오경보 11건 비교](FP11_POLICIES.csv) · [집계](SUMMARY.json) · [고정 계약 및 해시](CONTRACT.json) · [자체 검사](CHECKS.json)','', '기준선 판정·입력 SHA·코호트 수·비경보 불변·2137+복구−훼손 항등식 및 합계 검사를 통과했다. 구현자 자체 검증이며 독립 감사 또는 최종 정책 채택은 아니다.']
    (OUT/'REPORT_KO.md').write_text('\n'.join(lines),encoding='utf-8')
    write('HASHES.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file()})
    with zipfile.ZipFile(ROOT/'R2_RESULTS.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.iterdir():z.write(p,p.relative_to(ROOT))
        z.write(Path(__file__),'r2.py')
    print(json.dumps(stats,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
