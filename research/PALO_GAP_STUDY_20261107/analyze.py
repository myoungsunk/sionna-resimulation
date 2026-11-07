import json,csv,hashlib,itertools,sys
from pathlib import Path
import numpy as np
B=Path(__file__).resolve().parent;O=B/'results';A=B/'analysis'
def save(name,x):
 (A/name).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csvout(name,rows):
 if not rows:return
 with (A/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def wrap(a):return (a+np.pi)%(2*np.pi)-np.pi
def main():
 A.mkdir(exist_ok=False)
 s=json.loads((O/'SUMMARY.json').read_bytes());rows=s['rows'];assert len(rows)==636
 baseline={(r['level'],r['name']):r for r in rows if r['group']=='baseline'}
 aggregated=[];sens=[];cov=[];events=[];maxerr=0.
 for r in rows:
  with np.load(O/'trajectories'/r['path']) as a:
   take=a['t']>=(140 if r['group']=='development' else 40)
   e=a['X'][:,:3]-a['truth'];e[:,2]=wrap(e[:,2]);P=a['P'];xyn=np.linalg.norm(e[:,:2],axis=1)
   hn=e[:,2]**2/P[:,2,2]
   xn=(P[:,1,1]*e[:,0]**2-2*P[:,0,1]*e[:,0]*e[:,1]+P[:,0,0]*e[:,1]**2)/(P[:,0,0]*P[:,1,1]-P[:,0,1]**2)
   calc={'heading_rmse_deg':float(np.rad2deg(np.sqrt(np.mean(e[take,2]**2)))),'xy_rmse_m':float(np.sqrt(np.mean(xyn[take]**2))),'heading_nees':float(hn[take].mean()),'xy_nees':float(xn[take].mean()),'heading_95_coverage':float(np.mean(hn[take]<=3.841458820694124)),'xy_95_coverage':float(np.mean(xn[take]<=5.991464547107979))}
   maxerr=max(maxerr,max(abs(calc[k]-r[k]) for k in calc));assert maxerr<1e-9
   yes=a['accepted'];assert np.array_equal(a['P'][~yes],a['prior_P'][~yes]) and np.array_equal(a['X'][~yes],a['prior_X'][~yes])
   assert np.array_equal(a['P'][yes],a['candidate_P'][yes]) and np.array_equal(a['X'][yes],a['candidate_X'][yes])
   assert int(yes.sum())==r['applied_all']
   pre=a['prior_X'][:,:3]-a['truth'];pre[:,2]=wrap(pre[:,2])
   cand=a['candidate_X'][:,:3]-a['truth'];cand[:,2]=wrap(cand[:,2])
   benefit=abs(pre[:,2])-abs(cand[:,2])
   assert np.max(abs(benefit-a['benefit']))<1e-12
   if r['group']=='sensitivity':
    rng=np.random.default_rng(r['seed']);masks=[]
    for _ in range(2):
     u=rng.random(len(yes));mask=np.zeros(len(yes),bool)
     if r['pattern']=='iid':mask=u<r['rate']
     else:
      mask[0]=u[0]<r['rate']
      for i in range(1,len(yes)):mask[i]=(u[i]>=.2) if mask[i-1] else (u[i]<r['rate']/(5*(1-r['rate'])))
     masks.append(mask)
    expected=(benefit>1e-12)
    if r['kind'] in ('fn','both'):expected&=~masks[0]
    if r['kind'] in ('fp','both'):expected|=(benefit< -1e-12)&masks[1]
    expected&=a['nis']<=6.6348966010212145
    assert np.array_equal(expected,yes)
   if r['group']=='sensitivity':
    h0=baseline[r['level'],'s4']['heading_rmse_deg'];ho=baseline[r['level'],'heading']['heading_rmse_deg']
    retention=(h0-r['heading_rmse_deg'])/(h0-ho)
    sens.append(dict(level=r['level'],pattern=r['pattern'],kind=r['kind'],rate=r['rate'],seed=r['seed'],heading_rmse_deg=r['heading_rmse_deg'],xy_rmse_m=r['xy_rmse_m'],gain_retention=retention,criterion_pass=bool(retention>=.8 and r['xy_rmse_m']<=1.05*baseline[r['level'],'s4']['xy_rmse_m']),realized_fn=r['false_reject']/r['beneficial_opportunities'] if r['beneficial_opportunities'] else None,realized_fp=r['false_accept']/r['harmful_opportunities'] if r['harmful_opportunities'] else None))
   if r['group'] in ('baseline','rf','development'):
    longest=0;streak=0;reaccept=0;shrink_bad=0
    for k in range(len(yes)):
     if yes[k]:
      if streak>=5 and take[k]:
       pre=a['prior_X'][k,:3]-a['truth'][k];pre[2]=wrap(pre[2]);pp=a['prior_P'][k]
       pre_h=pre[2]**2/pp[2,2]
       ev=dict(group=r['group'],level=r['level'],name=r['name'],k=k,t=float(a['t'][k]),preceding_rejects=streak,prior_heading_abs_deg=float(np.rad2deg(abs(pre[2]))),posterior_heading_abs_deg=float(np.rad2deg(abs(e[k,2]))),Ppsi_before=float(pp[2,2]),Ppsi_after=float(P[k,2,2]),heading_nees_before=float(pre_h),heading_nees_after=float(hn[k]),xy_nees_after=float(xn[k]),heading_95_exceedance=bool(hn[k]>3.841458820694124),xy_95_exceedance=bool(xn[k]>5.991464547107979))
       events.append(ev);reaccept+=1;shrink_bad+=int(P[k,2,2]<pp[2,2] and abs(e[k,2])>abs(pre[2]))
      streak=0
     else:streak+=1;longest=max(longest,streak)
    cov.append(dict(group=r['group'],level=r['level'],name=r['name'],max_reject_streak=longest,reaccept_events_after5=reaccept,P_shrinks_error_grows=shrink_bad,**calc))
 for lv,pattern,kind,rate in itertools.product(('B0','L0','L1','L2'),('iid','burst'),('fn','fp','both'),(.01,.05,.1,.2)):
  q=[r for r in sens if (r['level'],r['pattern'],r['kind'],r['rate'])==(lv,pattern,kind,rate)]
  assert len(q)==5
  aggregated.append(dict(level=lv,pattern=pattern,kind=kind,rate=rate,heading_median=float(np.median([r['heading_rmse_deg'] for r in q])),heading_min=min(r['heading_rmse_deg'] for r in q),heading_max=max(r['heading_rmse_deg'] for r in q),retention_median=float(np.median([r['gain_retention'] for r in q])),pass_count=sum(r['criterion_pass'] for r in q),all5_pass=all(r['criterion_pass'] for r in q)))
 rfcompare=[]
 for lv,tau in itertools.product(('B0','L0','L1','L2'),(.02,.05,.1,.2)):
  rf=next(r for r in rows if r['group']=='rf' and r['level']==lv and r['tau']==tau and not r['gated'])
  gate=next(r for r in rows if r['group']=='rf' and r['level']==lv and r['tau']==tau and r['gated'])
  controls=[r for r in rows if r['group']=='random' and r['level']==lv and r['tau']==tau]
  assert len(controls)==5 and all(r['applied_all']==rf['applied_all'] for r in controls)
  rfcompare.append(dict(level=lv,tau=tau,ungated_heading=rf['heading_rmse_deg'],gated_heading=gate['heading_rmse_deg'],ungated_xy=rf['xy_rmse_m'],gated_xy=gate['xy_rmse_m'],rf_count=rf['applied_all'],gated_count=gate['applied_all'],random_heading_median=float(np.median([r['heading_rmse_deg'] for r in controls])),random_heading_min=min(r['heading_rmse_deg'] for r in controls),random_heading_max=max(r['heading_rmse_deg'] for r in controls)))
 csvout('RF_COMPARISON.csv',rfcompare);csvout('SENSITIVITY_RUNS.csv',sens);csvout('SENSITIVITY_AGGREGATE.csv',aggregated);csvout('COVARIANCE_SUMMARY.csv',cov);csvout('REACCEPTANCE_EVENTS.csv',events)
 save('VERIFY_RECEIPT.json',dict(status='SELF_CHECK_PASS',trajectories=636,max_metric_difference=maxerr,all_selected_state_covariance_exact=True,matched_count_controls=80,reaccept_events=len(events),independent_audit=False))
 report=['# PALO-GAP-002 실험 결과','', '질문: 완벽한 즉시 Heading 손익 오라클과 온라인 정보만 쓰는 신뢰도 판정기 사이의 간격. 기존 입력·운영 코드 변경 없음. 이 결과는 R2/anchor B/seed0 개발용 진단이며 독립 일반화 검증이 아니다.', '', '총 636개 저장 궤적(각 979시점): 기준 12, RF 정책 32, 횟수 일치 무작위 대조 80, 오류 주입 480, 시간 분할 개발 대조 32. 추가로 24개 zero-error limit 및 truth perturbation을 검사했다. 오류 반복 seed는 독립 RF 표본이 아니다.', '', '## 1. RF 오염 오라클','|수준|tau|gate Heading RMSE°|ungated Heading RMSE°|ungated 수용수|동일 횟수 random 중앙값°|','|---|---:|---:|---:|---:|---:|']
 for r in rfcompare:report.append(f"|{r['level']}|{r['tau']}|{r['gated_heading']:.4f}|{r['ungated_heading']:.4f}|{r['rf_count']}|{r['random_heading_median']:.4f}|")
 report+=['','임계값은 결과 전에 고정했다. 가장 좋은 tau만 일반 최적 임계값으로 주장하지 않는다. 무작위 대조는 전체 수용 횟수만 같고 시점·연속성은 다르다. RF 정책은 Full 측정값을 그대로 사용한다.','', '## 2. 온라인 특징과 손익','FEATURE_ASSOCIATIONS.json, FEATURE_QUARTILES.json, FEATURE_COUNTEREXAMPLES.json에 S4/DR/Heading 각 prior의 전체 관측을 기록했다. AUC는 큰 특징값이 유익함을 뜻하는 방향으로 계산했다. 0.5 미만이면 반대 방향 관련성이다. 시점·수준·prior의 의존성 때문에 p-value나 일반화 정확도를 주장하지 않는다. Hpsi는 민감도이며 정보량과 동일하지 않다.','', '## 3. 오류 민감도','|수준|패턴|오류|1% 중앙 RMSE°|5%|10%|20%|','|---|---|---|---:|---:|---:|---:|']
 for lv,pattern,kind in itertools.product(('B0','L0','L1','L2'),('iid','burst'),('fn','fp','both')):
  q=[next(r for r in aggregated if (r['level'],r['pattern'],r['kind'],r['rate'])==(lv,pattern,kind,rate)) for rate in (.01,.05,.1,.2)]
  report.append('|'+ '|'.join([lv,pattern,kind]+[f"{r['heading_median']:.4f}" for r in q])+'|')
 report+=['','FN=유익한 갱신 거부, FP=해로운 갱신 수용. 현재 궤적의 prior에서 매번 손익을 다시 계산하고 NIS gate는 유지했다. 오류율은 조건부 기회에 대한 주입 확률로 실제 발생률은 SENSITIVITY_RUNS.csv에 별도 기록한다. 80% Heading 이득 보존 및 XY<=1.05*S4 기준은 사전 지정한 진단 기준이며 알고리즘 채택/안전 기준이 아니다. 5개 반복의 범위는 신뢰구간이 아니다.','', '## 4. 공분산','거부 시 predicted P를 그대로 유지하고 수용 시 원래 갱신식을 사용하는지 확인했다. COVARIANCE_SUMMARY.csv와 REACCEPTANCE_EVENTS.csv에 5프레임 이상 거부 후 재수용 사건의 오차·P·NEES를 기록했다. 95% 임계 초과는 해당 사건의 기술적 지표이며 보정 여부의 통계적 검정이 아니다. 공분산 감소와 오차 증가를 분리해서 집계했다.','', '## 5. 개발용 온라인 판정기','학습은 40<=t<120의 S4/DR prior에서만 수행; 20초 공백 후 t>=140에서 공통 S4 이력을 출발점으로 폐루프 비교. 전체 R2가 이전에 공개되어 진정한 미사용 평가가 아니다. 규칙 선택에는 평가구간 라벨을 사용하지 않았다. 모델 동결 파일: FROZEN_DEVELOPMENT_MODEL.json.','', '|수준|정책|후반 Heading RMSE°|후반 XY RMSE m|Heading NEES|','|---|---|---:|---:|---:|']
 for r in rows:
  if r['group']=='development':report.append(f"|{r['level']}|{r['name']}|{r['heading_rmse_deg']:.4f}|{r['xy_rmse_m']:.4f}|{r['heading_nees']:.4f}|")
 report+=['','독립 환경·미사용 경로/seed에서 판정기 성능과 공분산 보정은 NOT_ESTABLISHED. 현재 공개 입력에는 이를 입증할 별도 동결 평가 세트가 없다. 따라서 본 실험을 최종 검출기 정확도 인증으로 보고하지 않는다.','', '## 검증·재현','CONTRACT.md 사전 기준, results/EXECUTION_PROVENANCE.json 코드/입력 해시, results/CHECKS.json 기준 재현·수식/진리표/참값 교란 검사, analysis/VERIFY_RECEIPT.json 저장 궤적 재집계 검사. 원본 입력 86개 해시 재검사. 모든 결과는 자체검증이며 이번 추가 실험의 독립 감사는 미실행.','실행: python -B campaign.py; 완료 후 python -B analyze.py. 결과 폴더가 이미 있으면 덮어쓰기를 거부한다. engine.py의 PRIOR는 보존된 이전 패키지 경로를 참조한다. 원본 입력을 복제하거나 수정하지 않았다.']
 (B/'REPORT_KO.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
 print('ANALYSIS_PASS',len(rows),'max_error',maxerr,'events',len(events),flush=True)
 print('MODEL',json.loads((O/'FROZEN_DEVELOPMENT_MODEL.json').read_bytes()),flush=True)
 print('RF',rfcompare,flush=True)
 print('DEV',[(r['level'],r['name'],r['heading_rmse_deg'],r['xy_rmse_m']) for r in rows if r['group']=='development' and r['name'] in ('s4','dr','heading','learned')],flush=True)
if __name__=='__main__':main()
