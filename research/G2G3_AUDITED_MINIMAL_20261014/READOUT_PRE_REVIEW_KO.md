# 사후분포 판단값 진단 수정 — 실행 전 감사

## 결정: GO_WITH_CLAIM_LIMITATION
최초 run 38526264898의 모델 수식·정규화 계산은 통과했다. 그러나 다음 판정 범위 문제가 발견되었다.
1. p(DR fault, RF inlier)는 p(RF 거리 오차 < DR 거리 오차)와 다른 사건이다. 전자를 후자의 필수조건으로 사용하면 필요 이상으로 RF 우선 판단을 막을 수 있다.
2. 223,236개 행에서 RF 우선 분기가 0회였으므로 오선택 0건을 안전성 검증으로 해석할 수 없다. 그 조건부 정밀도는 100%가 아니라 미정의(null)다.
3. C4의 '우선 확률 < 0.95'는 연속 혼합 평균의 보호를 뜻하지 않는다. 저장된 오차는 DR 0.03m, 혼합 평균 1.302069m로 다르다. 최초 C4의 좁은 boolean 검사 PASS는 보존하되 그 이상의 성능 주장만 금지한다.

## 수정 영향 범위
- model.py의 Git blob 1b13e7fa1909168f3f7cb2d35d2d86d4c00cb5b9는 그대로 유지.
- CONTRACT.json의 모형, 사전확률, 편향, 분산, 0.95 임계값을 바꾸지 않음.
- 새로운 CIR/gyro 품질 가설·학습·재귀 G2/G3는 실행하지 않음.
- 동일 사후분포의 두 사건 확률을 비교하는 진단을 1회 실행. 매개변수 선택 없음.
- 이전 정상 수식과 원본 입력 검산은 해시 일치 범위에서 REUSED_VERIFIED. 바뀐 CDF 판단값만 직접 적분과 독립 비교.

## 수식 감리
z=RF 거리, d=DR 거리, r=실제 거리, delta=d-z.
(d-r)^2-(z-r)^2 = delta*(d+z-2r).
따라서 delta>0이면 RF가 더 정확한 사건은 r<(d+z)/2, delta<0이면 r>(d+z)/2. delta=0이면 두 거리 추정은 항상 동일하여 strict win 확률=0.
고정 혼합 사후의 각 성분은 절단 Gaussian으로서 F_k(u)=1-SF((u-m_k)/s_k)/SF((h-m_k)/s_k), u>=h이다. log_ndtr와 expm1으로 계산하며 F(u)=sum w_k F_k(u).
검산은 생산 CDF나 생산 모드 평균을 호출하지 않고, 원래 정규화 prior×likelihood를 [h,(d+z)/2]에서 적분한 값 / [h,infinity]에서 적분한 값으로 비교한다. 허용차 1e-8 유지.

## 실행기·진단 코드 감사
- 추정 함수 입력은 d, sigma_DR, z와 기존 고정 모수. truth는 선택을 계산한 뒤 오차 승패 산출에만 사용.
- old probability 선택과 direct probability 선택은 모두 같은 delta>0, 원본 NIS>6.634896601, 확률>=0.95 조건을 사용. gate/threshold 사후 완화 없음.
- 전체 원본 row count=223236 및 양의 prior variance 확인.
- 각 선택의 분모·오선택 수를 따로 기록. 선택 0건이면 정밀도는 null.
- 수식 검산 실패는 이 readout 결과만 CASE_RESULT_INVALID로 처리하고 replay 전에 중단.
- 원본 artifact SHA256 56276ccb88605382b801f080cb97b58bc465bcff46c78677bcaf14fcd1b62bd5 불일치는 해당 replay HARD_EXECUTION_BLOCK.
- 이 진단의 높은 승률을 독립 보정된 95% 확률, 원인 식별, 전체 위치·Heading·G2/G3 성능으로 확장하지 않음.

작성자: assistant. 별도 외부 reviewer는 없음. 독립 계산 경로: 절단 혼합 CDF vs 원분포 직접 수치 적분. 모든 실행은 승인된 source Git blob 확인 및 PRE_RUN_READOUT_AUDIT.json 기록 후 수행.

다음 온라인 정책 채택이나 물리적 prior/RF 품질 모델 변경은 이번 실행 범위가 아니며, 진단 결과 브리핑 후 방향 확인 대상으로 남긴다.
