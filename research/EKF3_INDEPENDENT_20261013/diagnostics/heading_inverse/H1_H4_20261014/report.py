from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parent;A=ROOT/'ANALYSIS';D=ROOT/'OPT/FULL'
def link(p,label):return f'[{label}](<{p.as_posix()}>)'
def table(headers,rows):
 esc=lambda v:str(v).replace('|','\\|')
 return '\n'.join(['| '+' | '.join(map(esc,headers))+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(esc,row))+' |' for row in rows])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 h=pd.read_csv(A/'H12_POOLED.csv').set_index('channel');b=pd.read_csv(A/'H3_POOLED.csv').set_index('stage');c=pd.read_csv(A/'H4_POOLED.csv');units=pd.read_csv(A/'H3_UNIT_EFFECTS.csv');br=pd.read_csv(A/'H3_BAND_COMPONENT_DIAGNOSTIC.csv')
 receipt=json.loads((D/'RECEIPT.json').read_text());agg=json.loads((A/'AGGREGATION_RECEIPT.json').read_text());test=json.loads((ROOT/'OPT/TEST_RECEIPT.json').read_text());opt=json.loads((ROOT/'OPTIMIZATION_PARITY.json').read_text())
 assert receipt['status']==agg['status']==test['status']==opt['status']=='PASS'
 names={'M0':'M0','RF_HUBER_ONLY':'Huber','RF_CAUCHY':'Cauchy'}
 rows=[]
 for ch in ['los','full']:
  r=h.loc[ch];rows.append([ch.upper(),int(r.n),f'{r.multiple_pct:.2f}%',f'{r.no_root_pct:.2f}%',int(r.unique_n),f'{r.nominal_band_truth_pct:.2f}%',f'{r.nominal_band_width_median_deg:.2f}°'])
 t1=table(['RF','관측 수','복수해','정확한 해 없음','유일해 수','명목 구간 정답 포함률','총 구간 폭 중앙값'],rows)
 rows=[]
 for ch in ['los','full']:
  r=h.loc[ch];rows.append([ch.upper(),int(r.oracle_n),f'{r.oracle_error_median_deg:.3f}°',f'{r.oracle_error_p95_deg:.3f}°',f'{r.oracle_lower_bound_RMSE_deg:.3f}°',int(r.oracle_error_over90_n)])
 toracle=table(['RF','정확한 해가 있는 관측 수','오차 중앙값','오차 P95','RMSE','오차 >90° 수'],rows)
 rows=[]
 for st in ['NOISE','L0','L1','L2']:
  r=b.loc[st];rows.append([st,f'{int(r.paired_n)}/{int(r.n)}',f'{r.paired_DR_RMSE_deg:.3f}',f'{r.paired_H1_RMSE_deg:.3f}',f'{r.paired_H2_RMSE_deg:.3f}',f'{r.paired_H3_RMSE_deg:.3f}',f'{r.paired_H2_nominal_band_truth_pct:.2f}%',f'{r.paired_H3_nominal_band_truth_pct:.2f}%'])
 t3=table(['조건','공통 유효/전체','DR RMSE°','H1 RMSE°','H2 RMSE°','H3 RMSE°','H2 명목 포함률','H3 명목 포함률'],rows)
 rows=[]
 for st in ['NOISE','L0','L1','L2']:
  r=b.loc[st];rows.append([st,f'{r.rf_linear_term_abs_median_deg:.3f} / {r.rf_linear_term_abs_p95_deg:.3f}',f'{r.position_linear_term_abs_median_deg:.3f} / {r.position_linear_term_abs_p95_deg:.3f}',f'{r.linear_remainder_abs_median_deg:.3f} / {r.linear_remainder_abs_p95_deg:.3f}'])
 tl=table(['조건','RF 항 |오차| 중앙값 / P95°','위치 항 |오차| 중앙값 / P95°','실제 역변환−1차식 |차이| 중앙값 / P95°'],rows)
 def h4table(arm):
  rows=[]
  for st in ['NOISE','L2']:
   for ch in ['los','full']:
    for model in names:
     r=c[(c.stage==st)&(c.channel==ch)&(c.range_model=='B_OLD')&(c.arm==arm)&(c.model==model)].iloc[0]
     rows.append([st,ch.upper(),names[model],f'{r.heading_RMSE_deg:.3f}',f'{r.post_std_median_deg:.3f}',f'{r.heading_NEES_mean:.2f}',f'{r.heading95_pct:.1f}%',f'{r.applied_pct:.1f}%'])
  return table(['조건','RF','모델','Heading RMSE°','사후 σ 중앙값°','평균 Heading NEES','실제 95% 포함률','수용률'],rows)
 def cell(stage,channel,arm='A',model='M0'):
  return c[(c.stage==stage)&(c.channel==channel)&(c.range_model=='B_OLD')&(c.arm==arm)&(c.model==model)].iloc[0]
 nl=cell('NOISE','los');nf=cell('NOISE','full');bf=cell('L2','full')
 body=f'''# RF Heading 직접 역변환 H1–H4 실행 결과

실행·재현성 검사 **PASS**. 새로운 Heading 추출기나 융합 알고리즘의 채택을 검증한 실험은 아니며, `scientific_PASS=false`를 유지한다.

핵심 발견은 원본 `s`를 하나의 전역 Heading으로 역변환할 수 없다는 점이다. 이번 평가에서는 위치 정답을 제공해도 유일한 정확한 해가 없었다. 작은 LoS 잔차에서도 가까운 해가 사라질 수 있으므로 정확한 등식 역해의 RMSE를 RF의 사용 가능한 Heading 정확도로 해석하면 안 된다. Full RF의 모델 불일치와 DR 위치 오차는 별도로 확인된다.

## 실행 범위와 검증

- 기존 7 RF 조건, 평가 시작 30초, 원본 FP `s`, 동결 LoS LUT와 `R_s` 유지.
- H1–H2: LoS/Full 각각 {int(h.loc['los'].n):,}개 대응 관측. 동일 RF를 센서 seed별 독립 표본으로 중복 집계하지 않았다.
- H3: `noise_pair` Level 1, `gyro_bias` Level 0/1/2 × 7조건 × seed 0/1/2. RF 업데이트 없는 D0의 위치·Heading prior 사용. {receipt['H3_rows']:,}개 관측.
- H4: 기존 M0/Huber/Cauchy의 A/C trace, LoS B_OLD 및 Full B_OLD/E1. {receipt['H4_rows']:,}개 업데이트를 재분석했다. 필터 자체의 재귀 실행은 보존된 trace를 사용하며, 매 시점 운동 예측·NIS·gate·Joseph 공분산은 다시 계산했다.
- H4 각 trace의 첫 저장 표본은 직전 공분산이 없어 제외했다. H1–H3보다 그룹당 1표본 적다.
- 합성 시나리오 {test['synthetic_cases']}개 및 원본 모델 70개 위치 검사 PASS. 원본 `s_model` 대비 최대 차이 {test['native_max_abs_s']:.3e}.
- H4 {agg['parity_groups']:,}개 그룹, 허용치 `1e-8` 유지. 최대 NIS 차이 {agg['parity_max']['NIS_max']:.3e}, 사후 공분산 차이 {agg['parity_max']['posterior_cov_max']:.3e}. gate 수용/거부 일치.
- 실행 시간 단축은 표 변환과 압축에만 적용했다. 최적화 전후 smoke CSV는 압축 해제 시 바이트 단위 동일했다.
- checkout과 부모 작업 산출물은 읽기만 했다. 이 실험의 신규 코드·결과는 별도 폴더에 보존했으며 GitHub 게시는 수행하지 않았다.

## H1–H2: RF 자체의 각도 정보와 Multipath

고정 XY에서 동결 LUT가 Heading에 대해 구간 선형임을 원본 구현과 대조했다. 모든 구간의 역해를 열거했으며 접점·주기 경계·평탄 구간·무해를 처리했다. 이는 동결 보간 모델의 정확한 역변환이며 실제 안테나 응답의 무한 해상도 복원을 의미하지 않는다.

명목 각도 구간은 `|s_obs-h(ψ)| ≤ 1.96√R_s`이다. 아래 포함률은 관측된 경험적 비율이며 이 구간을 보정된 확률적 95% 신뢰구간으로 주장하지 않는다.

{t1}

두 채널 모두 해 개수 중앙값은 4개였다. Full–LoS 비교에서 구간 정답 포함률은 {h.loc['los'].nominal_band_truth_pct:.2f}% → {h.loc['full'].nominal_band_truth_pct:.2f}%로 감소했다. 같은 위치·Heading과 같은 LoS 관측모델에서 Full RF 잔차가 더 커진다는 증거다. LoS 무해 비율이 더 높다는 사실은 Full이 더 정확하다는 뜻이 아니다. 관측값이 국소 극값을 조금 벗어나거나 반대 방향 lobe에만 해가 남는 현상을 함께 봐야 한다.

다음은 **정답과 가장 가까운 정확한 해를 사후 선택한 ORACLE 진단**이다. 선택 알고리즘의 실제 정확도도, 잡음이 있는 각도 추정기의 달성 가능한 오차 하한도 아니다. 정확한 등식 해 집합 안에서만 계산한 최소 각도 거리다. 두 채널의 조건부 표본 수가 달라 채널 효과의 동일 표본 비교에는 별도 `H12_PAIRED_CASES.csv`를 사용한다.

{toracle}

LoS에서 oracle 오차가 90°를 넘는 {int(h.loc['los'].oracle_error_over90_n)}개 관측은 모두 명목 각도 구간 안에 정답이 있었다. 따라서 큰 정확한 역해 오차와 큰 관측 likelihood 오차를 혼동해서는 안 된다. 예시 `R5_aB_m0`, sample 1183은 결과를 설명하기 위한 사후 사례이며 임계값·모델 선택에는 사용하지 않았다.

![역해 분포](<{(A/'H12_INVERSE.png').as_posix()}>)

![가까운 정확한 해가 사라지는 예시](<{(A/'EXACT_ROOT_DISAPPEARANCE.png').as_posix()}>)

## H3: 위치 오차의 추가 영향

아래 H1/H2/H3는 **동일 DR Heading prior에 가장 가까운 정확한 해**를 선택한다. 정답 Heading은 해 선택에 사용하지 않았다. H1은 정답 XY+LoS, H2는 정답 XY+Full, H3는 D0 XY+Full이다. 세 경우 모두 선택 가능한 공통 표본으로 비교했다. 무해 표본은 원시 결과와 전체 집계에 남겼으며 RMSE 분모에서 제외한 수를 명시했다.

{t3}

이 RMSE에는 국소 정확한 해가 사라질 때의 약 180° 점프가 포함된다. 따라서 이 표는 단순 역해 선택기의 실패 진단이며 EKF에 투입할 새로운 Heading 측정값의 성능표가 아니다. 사용자가 요청한 위치 효과는 H2와 H3를 같은 표본·같은 prior에서 비교해야 한다. 작은 오차 조건에서 개별 잔차가 상쇄되어 MSE가 감소하는 경우도 있으므로 위치 오차가 항상 성능을 악화시킨다고 주장하지 않는다.

큰 bias Level 2에서는 명목 포함률이 {b.loc['L2'].paired_H2_nominal_band_truth_pct:.2f}% → {b.loc['L2'].paired_H3_nominal_band_truth_pct:.2f}%로 낮아졌다. DR 위치 사용이 RF 각도 해석에 추가 오차를 만든다는 직접적인 관측이다. 이 H3 구간은 DR 위치를 한 점으로 대입한 조건부 구간으로, 위치 공분산까지 적분한 예측구간이 아니다. 위치 불확실성까지 보정된 새 관측 공분산을 검증한 결과로 해석하지 않는다.

1차 분해는 정답에서의 Jacobian을 쓰는 `ORACLE_DIAGNOSTIC_ONLY`로 계산했다. 실제 입력용 Jacobian과 구분해 저장했다. RF 항과 위치 항의 교차항도 저장했으며 제곱 합 항등식을 검증했다. RF 항은 동일한 동결 관측을 사용하므로 조건별 값이 같다.

{tl}

미분값이 작은 구간과 다른 해로 넘어가는 경우에는 1차식의 큰 값 또는 큰 근사 오차를 숨기지 않았다. 사후 설명용으로 이미 동결된 명목 구간의 연결 성분을 이용해 같은/다른 구간을 분류한 결과는 `H3_BAND_COMPONENT_DIAGNOSTIC.csv`에 있다. 정답으로 분류한 이 조건부 결과 역시 온라인 성능으로 사용하지 않는다.

## H4: 각도 정보와 EKF 공분산

원본 `s`를 직접 업데이트하는 기존 필터를 대조했다. 아래는 B_OLD의 대표 조건이며 전체 Level 0/1 및 E1은 CSV에 포함되어 있다. Heading 95% 포함률은 `Heading NEES ≤ 3.841458820694124`인 실제 비율이다.

### A — Heading-only

{h4table('A')}

### C — Joint s + Range

{h4table('C')}

무편향 M0의 A에서는 LoS → Full로 바뀔 때 Heading RMSE가 {nl.heading_RMSE_deg:.3f}° → {nf.heading_RMSE_deg:.3f}°로 증가했지만 사후 표준편차 중앙값은 {nl.post_std_median_deg:.3f}° → {nf.post_std_median_deg:.3f}°였다. 실제 포함률은 {nl.heading95_pct:.2f}% → {nf.heading95_pct:.2f}%로 감소했다. Full RF에서는 오차 증가에 비해 보고된 불확실성이 충분히 커지지 않은 결과다. 큰 bias의 Full M0 A에서는 RMSE {bf.heading_RMSE_deg:.3f}°에 사후 표준편차 중앙값 {bf.post_std_median_deg:.3f}°, 포함률 {bf.heading95_pct:.2f}%였다. 강건화의 일부 조건 개선을 전체 조건의 통계적 일관성 확보로 일반화할 수 없다.

![Heading 포함률](<{(A/'H4_HEADING_COVERAGE.png').as_posix()}>)

공분산 감소가 저장된 수학식과 일치하는지와 실제 오차를 충분히 포함하는지는 별개의 판정이다. 전역 복수해가 존재하더라도 좁은 prior가 한 구간을 선택할 수 있으므로 복수해 개수만으로 EKF 공분산이 틀렸다고 판단하지 않았다. 반대로 반복 관측 후 작은 공분산을 얻었다는 사실만으로 실제 각도 정확도를 보장하지 않는다.

H4 원시 자료에는 전체 `H,S,K,R_effective,P_prior,P_post`, 수용 여부, 가중치, 업데이트 전후 각도 오차를 저장했다. 거부 표본의 `K`는 적용되지 않은 비교용 계산값이다. `heading_squared_error_change` 원시 단위는 rad²이며 집계의 `_deg2` 항목에서는 deg²로 변환·대조했다. `scalar_s_nominal_post_std_deg`는 원본 R0의 s-only 참고 계산으로 Joint/강건 사후 공분산과 동일한 값으로 간주하지 않는다.

## 해석과 다음 단계

1. **전역 단일 Heading 역변환은 성립하지 않는다.** 해 전체와 명목 허용 구간을 유지해야 한다. 정답으로 해를 고른 값을 센서 성능으로 제시할 수 없다.
2. **Full RF의 LoS 모델 불일치는 확인된다.** 정답 XY에서도 명목 구간 정답 포함률이 감소한다.
3. **위치 오차의 전파는 확인되며 큰 bias에서 중요하다.** 1차식은 국소 진단으로 사용하고 해 분기·작은 민감도 구간의 실제 역변환과 함께 판단해야 한다.
4. **이번 결과만으로 EKF 과신의 단일 원인을 확정하지 않는다.** H4는 수학적 재현과 경험적 일관성을 분리했다. RF 시간 상관·잔여 편향·운동 오차의 기여 비율은 이번 실험으로 분리하지 않았다.
5. 후속 실험은 정확한 등식 해로 강제 치환하기 전에, 원본 s likelihood와 DR prior를 각도 전 범위에서 결합한 다봉 사후분포를 기준으로 국소 EKF 근사의 적합성을 비교하는 것이 적절하다. 이번에는 그러한 추정기 변경이나 파라미터 조정을 하지 않았다.

통계는 시점별 독립 반복으로 검정하지 않았다. 경로/seed 단위 기술 통계를 별도로 저장했으며, 같은 RF 장면·같은 위치를 공유하는 seed와 안테나 조건도 완전 독립 환경으로 간주하지 않는다. 별도 RF scene 확증은 미실행이다.

## 증빙

- {link(ROOT/'PLAN.md','동결 실행 계약')}
- {link(ROOT/'OPT/TEST_RECEIPT.json','합성·관측모델 검사')}
- {link(ROOT/'OPTIMIZATION_PARITY.json','최적화 전후 동일성')}
- {link(D/'RECEIPT.json','전체 실행·입력·출력 해시')}
- {link(D/'H4_PARITY.csv','H4 재현 오차 전체')}
- {link(A/'AGGREGATION_RECEIPT.json','집계 검증과 해시')}
- {link(A/'H12_CASES.csv','H1–H2 조건별 결과')} / {link(A/'H12_PAIRED_CASES.csv','동일 표본 oracle 진단')}
- {link(A/'H3_CASE_SEED.csv','H3 경로·seed 결과')} / {link(A/'H3_UNIT_EFFECTS.csv','H3 단위별 효과')}
- {link(A/'H4_CASE_SEED.csv','H4 경로·seed 결과')} / {link(A/'H4_PAIRED_UNITS.csv','M0와 대응 표본 비교')}

최종 상태: `execution=PASS`, `native_model_parity=PASS`, `archived_EKF_parity=PASS`, `new_estimator_adoption=NOT_EVALUATED`, `independent_scene_validation=NOT_RUN`, `scientific_PASS=false`.
'''
 (ROOT/'SUMMARY_KO.md').write_text(body,encoding='utf-8')
 print('Report written',ROOT/'SUMMARY_KO.md')
if __name__=='__main__':main()
