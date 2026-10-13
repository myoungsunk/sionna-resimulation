from pathlib import Path
import json,math,hashlib,csv,io
root=Path(__file__).parent;out=root/'development_20261013'
def read(p):return json.loads(p.read_text())
v3=read(out/'V3/V3_SECOND_ORDER_ABLATION.json')['rows']
v4=read(out/'V4/V4_CALIBRATION_ABLATION.json')['rows']
for stage in ['V3','V4']:
 done=read(out/stage/'COMPLETION.json')
 assert done['status']=='EXECUTION_COMPLETE' and done['inputs_unchanged']
 for path,h in done['output_sha256'].items():assert hashlib.sha256((out/stage/path).read_bytes()).hexdigest()==h
methods=['BASE','MEAN2','COV2','BOTH2']
masks=['none','bg','sf','eps','bg+sf','bg+eps','sf+eps','bg+sf+eps']
cells=[(r,l) for r in ['R2','R4','R5'] for l in [0,1,2]]
lookup3={(r['route'],r['drift'],r['method']):r for r in v3}
lookup4={(r['route'],r['drift'],r['mask']):r for r in v4}
assert len(lookup3)==len(v3)==36 and len(lookup4)==len(v4)==72
metrics=['anees','anees_late25','coverage95','heading_contribution','conditional_xy_contribution','pos_rmse_m','heading_rmse_deg']
def gate(r):return 2.4<=r['anees']<=3.6 and 2.4<=r['anees_late25']<=3.6 and .92<=r['coverage95']<=.98
diffs=[]
for route,lv in cells:
 for metric in metrics:
  a=lookup3[route,lv,'BASE'][metric];b=lookup4[route,lv,'none'][metric]
  if not math.isclose(a,b,rel_tol=1e-7,abs_tol=1e-8):diffs.append(dict(route=route,drift=lv,metric=metric,joint_base=a,frozen_none=b))
for row in v3+v4:
 assert all(isinstance(row[k],(int,float)) and math.isfinite(row[k]) for k in metrics)
 assert math.isclose(row['anees'],row['heading_contribution']+row['conditional_xy_contribution'],rel_tol=1e-6,abs_tol=1e-7)
for row in v3:assert row['n_steps']=={'R2':979,'R4':742,'R5':1415}[row['route']] and row['n_seeds']==32
for row in v4:assert row['within_r22_band']==gate(row)
result=dict(status='VERIFIED' if not diffs else 'BASE_MISMATCH',source_revision=read(out/'V3/RUN_PLAN.json')['source_revision'],
            development_only=True,v3_episodes=1152,v4_episodes=2304,base_vs_frozen_differences=diffs,
            consistency_counts_v3={m:sum(gate(r) for r in v3 if r['method']==m) for m in methods},
            consistency_counts_v4={m:sum(gate(r) for r in v4 if r['mask']==m) for m in masks},
            scope='gauss_level; 9 cells; seeds 8000-8031; full trajectories',
            caveats=['Development seeds, not independent confirmation','Oracle truth information is not a deployable estimator','Fisher proxy ignores shared-input C','V5 NOT_RUN; D6 UNRESOLVED unchanged'])
(out/'VERIFICATION.json').write_text(json.dumps(result,indent=2))
assert not diffs,diffs
# Descriptive comparisons only; no post-result gate selection or causal promotion.
comparisons=[]
for route,lv in cells:
 b=lookup3[route,lv,'BASE']
 for method in methods:
  r=lookup3[route,lv,method]
  comparisons.append(dict(route=route,drift=lv,method=method,anees=r['anees'],late=r['anees_late25'],coverage=r['coverage95'],
    pos_rmse_m=r['pos_rmse_m'],anees_ratio_to_base=r['anees']/b['anees'],rmse_ratio_to_base=r['pos_rmse_m']/b['pos_rmse_m'],strict_consistent=gate(r)))
s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons)
(out/'V3_COMPARISON.csv').write_text(s.getvalue(),encoding='utf-8')
lines=['# V3 → V4 전체 개발 실행 결과','',
'## 실행 범위 및 검증','',
'- 소스: `'+result['source_revision']+'`. 코드·동결 생성기·motion 입력을 커밋 바이트와 대조하고 실행 전후 SHA256을 확인했다.',
'- gauss_level 세계; R2/R4/R5 × drift 0/1/2; 개발 seed 8000–8031 (32개); 전체 경로.',
'- V3: BASE/MEAN2/COV2/BOTH2, 36개 집계·1,152회. V4: 8개 oracle subset, 72개 집계·2,304회.',
'- V3 완료 및 결과 검사 후 V4 실행. 18개 셀 프로세스 모두 exit 0. 회귀 테스트 19개 통과.',
'- 모든 핵심 요약값 유한, NEES = heading + conditional XY 정합. V3 BASE와 V4의 원본 필터 none이 9셀의 7개 지표에서 허용오차(rel 1e-7, abs 1e-8) 내 일치.',
'- 두 단계는 서로 같은 seed와 world를 사용한다. 실제 수집 데이터 또는 새 seed 300개 확증이 아니다.',
'','## V3 — 2차 평균/공분산 분리','',
'비교용 strict gate는 기존 범위 ANEES 2.4–3.6, 말기 2.4–3.6, coverage 0.92–0.98을 그대로 사용한다. 개발 결과에 대한 서술이며 V5 합격 판정이 아니다.','',
'| 방법 | strict-consistent 셀 / 9 |','|---|---:|']
for m,n in result['consistency_counts_v3'].items():lines.append(f'| {m} | {n} |')
lines+=['','| 셀 | BASE ANEES | MEAN2 | COV2 | BOTH2 |','|---|---:|---:|---:|---:|']
for r,l in cells:lines.append(f'| {r}_d{l} | '+' | '.join(f'{lookup3[r,l,m]["anees"]:.5f}' for m in methods)+' |')
lines+=['','평균 보정 및 공분산 보정이 이후 상태·게이트 결정에 피드백되므로 네 실행의 차이는 독립 오차 항의 선형 합으로 해석하지 않는다. Gaussian 2차 Taylor 근사의 효과를 비교하며 전체 비선형 posterior 기전을 확증하지 않는다.',
'', '핵심 관찰: R2_d2의 BASE→BOTH2 ANEES는 132.92→53.70, R5_d2는 231.93→102.23으로 감소하지만 둘 다 일관성 범위에 크게 미달한다. R5_d2의 MEAN2는 말기 ANEES가 395.08→425.70, coverage가 33.30%→25.00%로 악화했다. BOTH2의 coverage도 29.57%로 BASE보다 낮다. 평균 NEES 감소만으로 평균 보정이나 결합 보정의 우월성을 주장할 수 없다.',
'','## V4 — Calibration oracle','',
'| Oracle subset | strict-consistent 셀 / 9 |','|---|---:|']
for m,n in result['consistency_counts_v4'].items():lines.append(f'| {m} | {n} |')
lines+=['','| 셀 | none | bg | sf | eps | bg+sf | bg+eps | sf+eps | all |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for r,l in cells:lines.append(f'| {r}_d{l} | '+' | '.join(f'{lookup4[r,l,m]["anees"]:.5f}' for m in masks)+' |')
lines+=['','모든 표의 수치는 ANEES다. Oracle는 초기 상태에 참값을 넣고 해당 prior 분산을 줄이는 진단이다. 배포 가능한 보정 성능으로 해석하지 않는다. known-wheelbase oracle는 실행하지 않았다.',
'', 'bg 또는 eps oracle는 고드리프트 과신을 크게 줄였지만 R5_d2에서 각각 ANEES 5.00, 4.29로 잔여 과신이 있다. 모든 calibration을 아는 oracle의 strict 통과가 0/9인 이유는 악화된 과신이 아니라 보수성이다: ANEES 약 2.30–2.38로 하한 2.4 미만이고 coverage 약 99.0–99.8%로 상한 98%를 초과한다. 통과 셀 수만으로 oracle 개입의 효과를 순위화하지 않는다.',
'','## 속도 변화 식별성 보조 지표','',
'C를 무시한 정적 local Fisher 근사이며 실제 posterior 식별성 보장이 아니다. 각 route의 proxy는 drift별 작업에서 중복 계산되며 9개 독립 route 결과로 세지 않는다.','',
'| Route | speed | 최소 prior-whitened 고유값 | bg–eps 상관 | bias SD (deg/s) |','|---|---|---:|---:|---:|']
info=read(out/'V4/V4_IDENTIFIABILITY_PROXY_ALL.json')['rows'];unique={}
for r in info:
 k=(r['route'],r['speed_profile'])
 if k in unique:assert r==unique[k]
 unique[k]=r
assert len(unique)==6
for (route,profile),r in unique.items():lines.append(f'| {route} | {profile} | {r["weakest_info_eigenvalue"]:.5g} | {r["bg_eps_correlation_proxy"]:.5f} | {r["approximate_bias_posterior_sd_deg_s"]:.5g} |')
lines+=['','## 보존·다음 단계','',
'- D6 cache/out, spec, prereg, harness 및 과거 pilot는 수정하지 않았다. D6 UNRESOLVED 유지.',
'- V5 NOT_RUN. 이 결과를 바탕으로 후보 및 평가 계획을 검토한 뒤 코드·조건·새 seed를 사전등록해야 한다.',
'- 각 셀 폴더: 결과 JSON/manifest. 각 .log: stdout/stderr. *_RECEIPT.json: 명령·시각·종료코드. RUN_PLAN.json: 실행 설정/입력 SHA. COMPLETION.json: 산출물 SHA. VERIFICATION.json: 단계 간 대조 결과.',
'- 출력은 원래 CLI의 집계 형식이다. 개별 episode의 전체 궤적 배열은 별도 저장하지 않는다.']
(out/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
