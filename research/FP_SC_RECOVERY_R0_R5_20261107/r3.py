from pathlib import Path
import csv,json,hashlib,datetime,sys,platform,collections,zipfile
import numpy as np
ROOT=Path(__file__).resolve().parent;SRC=ROOT/'RUN_002';R2=ROOT/'R2_RUN_001';OUT=ROOT/'R3_RUN_001'
STEP=299792458/(1028*1950000)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def table(n,rs):
    with (OUT/n).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def metrics(q):
    d={'n':len(q)}
    for x in ['range','S']:
        a=np.array([r[x+'_error'] for r in q]);b=np.array([r['B_'+x+'_error'] for r in q])
        for label,v in [('before',b),('after',a)]:
            for name,value in [('MAE',np.mean(abs(v))),('RMSE',np.sqrt(np.mean(v*v))),('P95_abs',np.quantile(abs(v),.95)),('max_abs',max(abs(v)))]:d[x+'_'+label+'_'+name]=float(value)
        d[x+'_absolute_error_gain_sum']=float(np.sum(abs(b)-abs(a)))
        d[x+'_squared_error_gain_sum']=float(np.sum(b*b-a*a))
        d[x+'_improved']=int(np.sum(abs(a)<abs(b)-1e-12));d[x+'_worsened']=int(np.sum(abs(a)>abs(b)+1e-12));d[x+'_unchanged']=len(q)-d[x+'_improved']-d[x+'_worsened']
    return d
def main():
    OUT.mkdir(exist_ok=False)
    summary=json.loads((SRC/'SUMMARY.json').read_text());manifest=summary['source_hashes']
    gov=Path('C:/Users/Myoungsun Kim/.codex/research-governance')
    write('CONTRACT.json',dict(question_id='B-PONLY-RECOVERY-R3-20261107',source_commit=summary['contract']['source_commit'],role='IMPLEMENTER_SELF_CHECK',scope='R3 only; frozen R2 decisions, P radius .075, no M, no R4 or EKF',range_definition='(selected tap - Native LoS reference tap)*299792458/(1028*1950000), meters; not geometric range error',S_definition='(abs(CIR0[n])**2-abs(CIR1[n])**2)/sum; common selected tap; compare Native LoS S',gain_definition='positive = baseline error minus selected error; additive absolute and squared errors, not additive RMSE',inputs={str(p.relative_to(ROOT)):sha(p) for p in [SRC/'A_ALL_3136.csv',SRC/'SUMMARY.json',R2/'ROWS.csv',R2/'SUMMARY.json']},script_sha256=sha(Path(__file__)),governance={n:sha(gov/n) for n in ['COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md']},started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=platform.python_version(),numpy=np.__version__,command='python r3.py'))
    for folder,hfile,files in [(SRC,'ARTIFACT_HASHES.json',['A_ALL_3136.csv','SUMMARY.json']),(R2,'HASHES.json',['ROWS.csv','SUMMARY.json'])]:
        hashes=json.loads((folder/hfile).read_text())
        for n in files:assert sha(folder/n)==hashes[n]
    sys.path.insert(0,str(ROOT/'sources/src'))
    from qclean_uwb.drivesim import observation as obs
    sp='src/qclean_uwb/drivesim/observation.py';assert sha(ROOT/'sources'/sp)==manifest[sp]['sha256']
    base=read(SRC/'A_ALL_3136.csv');decisions=read(R2/'ROWS.csv');idx={(r['case'],int(r['k'])):r for r in base}
    assert len(idx)==3136 and len(decisions)==12544
    assert len({(r['policy'],r['case'],r['k']) for r in decisions})==12544
    results=[];inputhash={};maxdiff=0.
    for case in sorted({r['case'] for r in base}):
        payload={}
        for name in ['online.npz','evaluator.npz']:
            p=next(p for p in manifest if p.endswith('/'+case+'/'+name))
            local=ROOT/'inputs'/(hashlib.sha256(p.encode()).hexdigest()[:20]+'_'+name)
            assert sha(local)==manifest[p]['sha256'];inputhash[p]=sha(local)
            with np.load(local,allow_pickle=False) as f:payload[name]={k:f[k] for k in (['Hrf','t','pose_id'] if name=='online.npz' else ['clean_H','t','pose_id'])}
        on=payload['online.npz'];ev=payload['evaluator.npz']
        assert np.array_equal(on['t'],ev['t']) and np.array_equal(on['pose_id'],ev['pose_id'])
        cir=obs.cir_batch(on['Hrf']);refs=obs.first_path_batch(obs.cir_batch(ev['clean_H']),1950000)
        powers=abs(cir)**2
        def sval(k,n):
            p=powers[k,n];assert np.isfinite(p).all() and p.sum()>0
            return float((p[0]-p[1])/p.sum())
        for r in decisions:
            if r['case']!=case:continue
            k=int(r['k']);b=idx[case,k];B=int(b['B']);n=int(r['selected']);ref=int(b['reference'])
            assert ref==int(refs['index'][k]) and int(r['reference'])==ref and int(r['B'])==B
            assert abs(float(r['time_s'])-on['t'][k])<1e-12
            bs=sval(k,B);los=float(refs['s'][k]);s=sval(k,n)
            maxdiff=max(maxdiff,abs(bs-float(b['B_S'])),abs(los-float(b['LOS_S'])))
            assert maxdiff<1e-12
            if r['cohort'] in ['FN','TN']:assert n==B
            results.append(dict(policy=r['policy'],case=case,k=k,time_s=float(r['time_s']),cohort=r['cohort'],outcome=r['outcome'],B=B,selected=n,reference=ref,changed=n!=B,exact=n==ref,range_error=(n-ref)*STEP,B_range_error=(B-ref)*STEP,S=s,B_S=bs,LOS_S=los,S_error=s-los,B_S_error=bs-los))
    table('ROWS_12544.csv',results)
    stats=[];cross=[]
    for policy in ['K0','K1','K2','K3']:
        q=[r for r in results if r['policy']==policy]
        assert len(q)==3136
        groups={'ALL':q}
        for key in ['TP','FP','FN','TN']:groups[key]=[r for r in q if r['cohort']==key]
        for case in sorted({r['case'] for r in q}):groups[case]=[r for r in q if r['case']==case]
        groups['TP_EXACT_RECOVERED']=[r for r in q if r['outcome']=='EXACT_RECOVERY']
        groups['TP_NOT_EXACT_RECOVERED']=[r for r in q if r['cohort']=='TP' and r['outcome']!='EXACT_RECOVERY']
        for group,g in groups.items():
            if g:stats.append(dict(policy=policy,group=group,**metrics(g)))
        allm=metrics(q)
        for x in ['range','S']:
            for kind in ['absolute','squared']:
                key=x+'_'+kind+'_error_gain_sum'
                assert abs(allm[key]-sum(metrics(groups[c])[key] for c in ['TP','FP','FN','TN']))<1e-10
        for exact in [False,True]:
            g=[r for r in q if r['cohort']=='TP' and r['exact']==exact]
            for change in ['improved','unchanged','worsened']:
                count=sum(('improved' if abs(r['S_error'])<abs(r['B_S_error'])-1e-12 else 'worsened' if abs(r['S_error'])>abs(r['B_S_error'])+1e-12 else 'unchanged')==change for r in g)
                cross.append(dict(policy=policy,TP_exact_after=exact,S_change=change,n=count))
    # unchanged K0/K3 must match sample by sample; baseline S agrees with prior report.
    for r in results:
        if r['policy'] in ['K0','K3']:assert r['range_error']==r['B_range_error'] and r['S_error']==r['B_S_error']
    allstats=[r for r in stats if r['group']=='ALL']
    assert abs(allstats[0]['S_after_MAE']-.0473033)<5e-8 and abs(allstats[0]['S_after_RMSE']-.0798753)<5e-8
    table('METRICS.csv',stats);table('TP_EXACT_VS_S.csv',cross);table('FP11_DETAILS.csv',[r for r in results if r['cohort']=='FP'])
    write('SUMMARY.json',{'overall':allstats,'groups':stats,'cross':cross})
    write('CHECKS.json',dict(status='PASS',rows_per_policy=3136,policies=4,baseline_max_S_difference=maxdiff,input_sha256=inputhash,nonalarm_unchanged=True,gain_additivity=True,K0_K3_equal_B=True,baseline_S_matches_R1=True,independent_audit=False,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=0))
    lines=['# R3: 고정 B + P 7.5 cm 관측 오차 비교','','전체 3,136행, R2 K0–K3 선택 결과를 그대로 사용했다. 거리 오차는 Native-LoS 참조 tap과의 차이 × tap 간격이며 기하학적 참거리 오차와 다르다. S는 실제 Full CIR의 선택된 공통 tap에서 재추출하여 Native-LoS S와 비교했다. 정답은 평가 전용이다.','','|정책|거리 MAE (cm)|거리 RMSE (cm)|S MAE|S RMSE|','|---|---:|---:|---:|---:|']
    for v in allstats:lines.append(f"|{v['policy']}|{100*v['range_after_MAE']:.6f}|{100*v['range_after_RMSE']:.6f}|{v['S_after_MAE']:.8f}|{v['S_after_RMSE']:.8f}|")
    lines+=['','## 집단별 손익','','양의 이득은 개선, 음수는 손해다. 절대오차 합과 제곱오차 합만 집단 간 가산할 수 있으며 RMSE 자체를 더하거나 빼서 손익을 합산하지 않는다. 아래 거리 합은 m, S 합은 무차원이다.','','|정책|집단|N|거리 MAE 전→후(cm)|S MAE 전→후|거리 절대오차 합 이득|S 절대오차 합 이득|','|---|---|---:|---:|---:|---:|---:|']
    for v in stats:
        if v['group'] not in ['TP','FP','TP_EXACT_RECOVERED','TP_NOT_EXACT_RECOVERED']:continue
        lines.append(f"|{v['policy']}|{v['group']}|{v['n']}|{100*v['range_before_MAE']:.6f} → {100*v['range_after_MAE']:.6f}|{v['S_before_MAE']:.8f} → {v['S_after_MAE']:.8f}|{v['range_absolute_error_gain_sum']:.6f}|{v['S_absolute_error_gain_sum']:.6f}|")
    lines+=['','## 경로별 결과','','|정책|경로|거리 MAE(cm)|거리 RMSE(cm)|S MAE|S RMSE|','|---|---|---:|---:|---:|---:|']
    for v in stats:
        if '_Full_' in v['group']:lines.append(f"|{v['policy']}|{v['group']}|{100*v['range_after_MAE']:.6f}|{100*v['range_after_RMSE']:.6f}|{v['S_after_MAE']:.8f}|{v['S_after_RMSE']:.8f}|")
    lines+=['','[全 행별 결과](ROWS_12544.csv) · [집단별 MAE/RMSE/P95/최대 및 가산 손익](METRICS.csv) · [정확 tap × S 개선 교차표](TP_EXACT_VS_S.csv) · [정상 11건 상세](FP11_DETAILS.csv) · [계약](CONTRACT.json) · [검증](CHECKS.json)','','실행 성공 및 구현자 자체 검증 완료. 입력 SHA, 실제 CIR 기준선 재현, 동일 표본/키, 비경보 불변, 집단 손익 합계 검사를 통과했다. 독립 감사·최종 정책 채택·새 환경 일반화를 뜻하지 않는다. R3까지만 실행했으며 P 중심 변화·R4·폐루프 EKF는 실행하지 않았다.']
    (OUT/'REPORT_KO.md').write_text('\n'.join(lines),encoding='utf-8')
    write('HASHES.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file()})
    with zipfile.ZipFile(ROOT/'R3_RESULTS.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.iterdir():z.write(p,p.relative_to(ROOT))
        z.write(Path(__file__),'r3.py')
    print(json.dumps({'overall':allstats,'effects':[r for r in stats if r['policy'] in ['K1','K2'] and r['group'] in ['TP','FP','TP_EXACT_RECOVERED']],'cross':cross},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
