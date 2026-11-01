# 구현·실행 뒤 결과를 어떻게 사용할 것인가

`DLP-PHYS-BRIDGE-012-001` · PROPOSER · 2026-11-01

목적은 결과를 본 뒤 유리한 서사를 고르는 것이 아니라, **무엇이 관측되면 어느 문장까지 쓸 수 있는지 먼저 정하는 것**이다. 아래 조건문은 신규 결과가 아니다. 모든 새 결과란은 `NOT_RUN`이다.

## 1. 사실·해석·가설의 세 층

1. **기존 관찰 E:** 업로드한 검토 자료와 원고 v4에서 확인한 역사적 수치. 재현성 범위는 seed0·동일 Corridor·선택12조건으로 제한한다.
2. **검증 대상 M:** 물리 민감도, 같은-prior 갱신, 거리 조건의 고유 기여, 시간적 누적의 메커니즘 가설.
3. **향후 주장 C:** 새 실행 raw/trace와 독립 검토가 지지한 만큼만 원고에 반영한다.

기존 12/12 Heading 감소를 사후에 preregistered success라고 부르지 않는다. 새 분석도 이미 선택된 자료의 메커니즘 설명이며 unseen-environment 확증은 아니다.

## 2. 유지할 기존 사실과 현재 금지할 확대해석

| 기존 사실 | 지금 쓸 수 있는 문장 | 아직 쓸 수 없는 문장 |
|---|---|---|
| MB_VAR/self는 선택12조건 Heading 감소, XY8/12 감소 | 같은 구조·하이퍼파라미터의 선택조건 Heading 개선 | 모든 route·초기값·환경에서 우수 |
| BB_VAR/self도 Heading12/12, XY8/12 개선 | 성공 개수만으로 결합 필요성을 증명할 수 없다 | 12/12이므로 두 요소 모두 반드시 필요 |
| R2-B/R5-B 8조건에서는 결합이 각 단독보다 두 지표 낮음 | 그 두 경로에서 평균·분산 처리가 상보적 결과를 보였다 | 상보성의 물리적 원인이 이미 유일하게 확정 |
| R4-B는 variance-only가 결합보다 두 지표 우수 | Range 평균 교체의 추가 효과는 경로별로 다르다 | 편파 mean 부호만으로 XY 악화 원인 확정 |
| Range RMS는 세 경로 모두 감소 | 전체 Range 오차의 조건부 평균 교체가 잔차 제곱오차를 줄였다 | 세 경로 모두 signed bias를 제거했다 |
| 일부 편파 E[ε²]가 기존 Rss보다 작음 | 추가 σ²는 현재 effective reliability 조절이다 | 누락된 참 thermal variance를 정확히 복원했다 |
| 잔차 ACF와 거리-bin 차이 | 순차/기하 의존 잔차가 존재한다 | 독립 시간 drift와 공간 kernel을 각각 식별했다 |

기존 값은 `reference_review`의 원문/CSV/QA 및 `SOURCE_REFERENCE_LOCK.json`의 immutable refs로 추적한다. 전사 subset은 원 CSV 전체와 동일 바이트라고 주장하지 않는다.

## 3. 새 분석 결과별 claim 판정

### C-PHYS — 물리 관측구조

- PB1 source chain·native ratio·branch별 J 검증 PASS: “실제 복소 FFD와 관측 연산으로 위치·Heading 민감도를 반영했다.”
- 선택 route의 J·signed residual 정렬이 일관적: 어떤 기하/branch 층에서 나타났는지 명시하여 물리적 설명을 보강한다.
- 정렬이 약하거나 상반됨: “FFD h/J 구현은 검증했으나 해당 잔차의 주요 원인은 특정하지 못했다.” 기존 성능표는 유지한다.
- branch J 검사 실패: 물리적 민감도 그림과 그로부터 계산한 state information의 claim을 BLOCKED. 실패 자료를 부록·개선 과제로 보존한다.
- Hsψ≠0만으로 전역 4-state observability나 Dual-LP 인과적 우월성을 승인하지 않는다.

### C-MECH — 평균·분산의 개선 경로

- 동일 prior gain 항등식·mean shift 대수 PASS는 수학적 구현 검증이다. 그것만으로 미래 RMSE 개선 원인 입증은 아니다.
- shadow에서 signed correction 개선 + fixed-mask 재귀에서도 개선 + self에서도 유지: 해당 범위에서 local→recursive 연결을 제시할 수 있다. 각 단계의 effect size와 denominator를 모두 제시한다.
- shadow 개선, fixed 재귀 악화: 상태전이·비선형 작동점·잔차 순서를 원인 후보로 남긴다. one-step benefit을 전체 시스템 benefit으로 확대하지 않는다.
- fixed 개선, self 악화: 정책 선택과 prior feedback 효과를 별도 기전으로 설명한다. “분산 효과” 하나로 합치지 않는다.
- R4-B 결과가 mixed: R4-B는 삭제하지 않는다. 작은 Heading 개선, XY 손실, variance-only 우위가 나타나는 조건을 같은 본문 12조건 표에 남긴다.

### C-DIST — 거리 조건 lookup의 고유 기여

- 현재 lookup이 CONST보다 명확한 per-case 이득을 보이면: “단순 일괄 down-weighting에 더해 거리 조건을 사용한 신뢰도 조절이 이 사례에서 유효했다.”
- 상수와 같거나 방향이 mixed: “편파 신뢰도 조절이 유효했고 거리 lookup은 한 경험적 구현이다.” 최적거리함수·물리 유도 covariance 문구를 쓰지 않는다.
- 상수가 더 좋으면: 현재 MB_VAR의 12조건 역사적 개선은 유지하되, 거리 표의 고유 우월성 가설은 `NOT_SUPPORTED`. 새 상수를 본문 주모델로 자동 교체하지 않는다. 모델 변경은 별도 제안·실험이다.
- source fold에서 상수를 계산할 수 없으면: 결과를 만들지 않고 `BLOCKED_CONST_SOURCE`.

### C-CORR — 시간·공간 상관

- mean/기하 제거 후에도 stable branch에서 잔차 또는 gain-projected 오차가 지속: “평균·기하만으로 설명되지 않는 경로상 지속성을 관측했다.”
- 기하 제거 후 상관 감소: “관측된 시간 ACF의 상당 부분은 위치·자세에 따른 정적 field와 일관된다.” temporal process가 없다는 단정은 금지.
- 같은 pose 재방문/독립 시간 realization 부족: `TIME_VS_SPACE_NOT_IDENTIFIED`; 현재 논문은 static field를 주행하며 얻은 상관으로 제한한다.
- 어떤 결과든 기존 MB_VAR가 full spatiotemporal joint covariance를 처리했다고 표현하지 않는다.

### C-REPRO — 재현 범위

- 예측file과 원래 μ/전체 재귀까지 일치: “저장된 예측과 원본 입력에서12조건 결과를 재현했다.”
- scaler/weights/feature까지 재구성하여 inference도 일치: 위 문장에 “학습된 회귀 추론 경로”를 추가한다.
- 저장예측만 있고 원 model이 없으면: archived-prediction reproducibility만 승인. 온라인 회귀 일반화는 미확인.
- 새 seed/새 scene 없음: 강건성·통계적 유의·외부 일반화 문구를 추가하지 않는다. 새 seed 실험이 현재 seed0 관찰의 존재 조건은 아니다.

## 4. 결과를 넣을 위치

| Artifact | 주 용도 | 본문 위치 |
|---|---|---|
| PB1 물리 response/J/residual map | 정보 경로와 distortion 경로를 같은 기하에서 보여줌 | §1.1–1.2, 새 Figure A |
| PB1 full/direct/model error 분해 | 다중경로와 surrogate/관측정의 오차 분리 | §1.2, 보조 Figure B |
| PB2 shadow signed yaw/XY update | 두 보정요소의 상태 갱신 기전 | §2.2–§3.2, Figure C |
| PB2 fixed/self recursive traces | 국소 효과와 실제 policy 효과 구분 | §3.2, Table D |
| PB3 ZERO/CONST/LOOKUP | 거리 조건의 추가 가치 | §3.3, Table E |
| PB4 raw/cross-fit/투영 ACF | 상관의 위치와 주장 한계 | §1.3 또는 부록 |
| source/parity/failure ledger | 재현성·변경 없음 증거 | 방법·부록 |
| 기존 12조건 self score | 주 성능 사실 | 기존 Table 3 유지 |

Figure 수를 과도하게 늘리지 않는다. 기본은 물리 map 1개, signed update/recursion 1개, variance-policy 비교 1개이며 case별 세부 그림은 부록으로 이동한다. 분석에서 확인하지 않은 물리 ray 식별·반사면 attribution 그림을 장식용으로 넣지 않는다.

## 5. 필수 결과 표와 claim ledger

`CLAIM_EVIDENCE.csv` 필드:
`claim_id,existing_or_new,manuscript_section,claim_sentence,design_id,run_id,code_sha,input_lock_sha,artifact_path,case_set,bias_set,gate,reference_prior,denominator,observed_effect,mechanical_status,scientific_verdict,limitations,auditor_verdict`.

각 메커니즘 문장은 raw packet/trace 또는 figure source까지 연결한다. “원인”이라는 단어는 어떤 개입을 고정하고 무엇만 바꾸었는지 함께 써야 한다. 수치 계산 PASS와 가설 SUPPORTED를 혼용하지 않는다.

최종 보고는 route별12조건 원 단위·상대변화, 두 단독과 결합 비교, 모든 무효/제외 packet, source/lookup/gate parity, 불확실성 지표를 함께 제공한다. covariance calibration이 좋지 않아도 Heading 점추정 개선의 관찰은 유지하며, 신뢰성 향상까지 덧붙이지 않는다.

## 6. 성공·실패 모두 허용하는 논문 정책

이 논문은 모든 case의 동시 성공을 요구하지 않는다. R2-B/R5-B를 중심 설명군으로 두고 R4-B를 동일 모델의 경계 사례로 유지한다. 분석이 mixed라고 연구를 새 5-state·SUB3·모든 환경 해법으로 확대하지 않는다. 목적은 **선택한12조건의 일관된 Heading 관찰과 그 조건부 설명을 검증하는 것**이다.
