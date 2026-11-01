# 유효한 데이터에 근거한 물리적 관측구조–EKF 갱신–성능 연결

## 1. 사용 범위

R2-B/R4-B/R5-B × B0/L0/L1/L2, 기존 signed 편파비·정수 first-path 거리·4상태·기존 평균교체/분산lookup을 유지한다. 독립 물리 장면은 하나다. R4 음성시험 결함은 QA 선언의 미완결성이며, 현재 원 수치가 바뀌었다는 증거가 아니다. 기존 성능표·132 trace·physics/shadow 기록이 이전 감사자료와 동일하고 이번 핵심 재계산도 일치했다.

|자료|현재 유효한 사용|확대하면 안 되는 주장|
|---|---|---|
|3,136 물리 packet/원 FFD|두 포트 power, signed ratio, Full/LoS/source 차이, local Jacobian|하드웨어 교정·특정 반사체 단일 원인|
|9,408 FD 기록|stable9,356/transition52의 수치검사 이력|모든 상태에서 전역 미분가능|
|50,176 BB-prior shadow 후보|평균×분산 개입, signed Kε/Kδh, local loss|모든 MB-prior의 반사실 또는 전체 누적 인과|
|132 trace/144 논리 비교|선택12조건의 end-to-end 성능|144독립 실험·새 scene 일반화|
|R6 896구간|기하별 탐색 진단|서로 다른 분모의 평균을 곧바로 인과 연결|

## 2. 관측 현상 → 모델 가정

두 직교 LP 포트의 공통 첫 경로 power에서

\[
s(x)=\frac{P_+(x)-P_-(x)}{P_+(x)+P_-(x)},\qquad
\partial_u s=\frac{2(P_-\partial_u P_+-P_+\partial_u P_-)}{(P_++P_-)^2}.
\]

물리 기반 부분은 실제 복소 FFD, 좌표 변환, 공통 detector 연산, 그 h_s와 J이다. 공통 복소 스칼라는 이상적인 normalized ratio에서 상쇄되지만 차등 편파 응답·간섭·검출 선택은 남을 수 있다. 거리 lookup은 이 물리 전체로부터 유도된 exact covariance가 아니라 경험적 신뢰도 설정이다.

이번 t>=30·gate 비선택 구간 재집계:

|경로|평가 packet|기록된 |J_sψ| 중앙값, /rad|잔여 편파 RMS|Full–LoS s 차이 RMS|
|---|---:|---:|---:|---:|
|R2-B|829|0.461|0.107|0.113|
|R4-B|592|1.775|0.123|0.117|
|R5-B|1265|0.405|0.093|0.095|

이 표는 true-pose 관측모형의 진단값이며 실제 filter prior의 Fisher 정보나 오차 기여율이 아니다. active branch 미분값의 집계이며 transition 구간을 포함한 전역미분 가능성을 뜻하지 않는다. R4에서 Heading 민감도가 없어서 개선이 작았다고 설명할 근거는 없다. 실제 gain은 H뿐 아니라 prior covariance와 R에 의존한다.

별도 재계산한 원 power→ratio 항등식 최대차는 4.22e-13, innovation 분해는 7.16e-16, signed K 투영은 2.37e-16이다. 수치 연결의 정합성을 확인했으며 독립 물리 진실을 증명한 것은 아니다.

## 3. 모델 가정 → 직접 갱신 효과

\[
\nu=z-h(x^-)-\mu=\epsilon+[h(x^*)-h(x^-)],\qquad
\Delta x=K\epsilon+K\delta h.
\]

동일 prior/J/lookup 상태에서 편파 추가분산은 해당 gain column을 줄인다. 이때 관측 model-error에 의한 갱신뿐 아니라 prior 상태오차를 바로잡는 성분도 줄어들 수 있다. 따라서 매 packet의 즉시 오차가 줄어야 하는 것은 아니다.

실제로 R2/R5의 8조건 모두 동일 BB-prior 집합의 평균 즉시 Heading MSE는 MB_ORIG보다 MB_VAR에서 더 크지만, 전체 재귀 Heading RMSE는 MB_VAR가 더 작다. 이는 '추가분산이 매 순간 오차를 줄여 최종 성능이 좋아졌다'는 단일 설명을 배제한다. 이후 prior·가중치 이력이 중요하지만 특정 구간의 누적 기여율까지 확정하려면 별도의 V4 성격 분석이 필요하다. 현재 회고적 결과 수용을 위해 V4를 의무화하지 않는다.

## 4. 재현 가능한 성능 주장

|B0/self|BB_ORIG Heading/XY|MB_VAR Heading/XY|MB_CONST Heading/XY|
|---|---|---|---|
|R2-B|1.2047° / 6.8269cm|1.0847° / 5.3303cm|1.6253° / 10.7688cm|
|R4-B|1.4418° / 8.5363cm|1.4312° / 9.4325cm|1.1369° / 5.4898cm|
|R5-B|1.0731° / 8.6882cm|0.6434° / 4.4551cm|1.4293° / 12.5319cm|

네 gyro 조건 전체에서는 MB_VAR가 BB_ORIG 대비 Heading12/12, XY8/12 개선이다. 지정 상수와 비교하면 lookup은 R2/R5의8조건에서 두 지표 우수하고, R4의4조건에서는 두 지표 열세다. 최적 상수를 탐색한 결과가 아니다. R4의 작은 Heading 차이를 통계적 유의성이나 보편적 우월성으로 쓰지 않는다.

fixed에서도 lookup/constant의 같은 우열이 남는다. 따라서 self-gate에서 수용집합이 바뀌는 것만으로 결과를 설명할 수 없다. 그러나 fixed에서도 재귀 prior/P는 달라지므로 전체 인과관계가 확정된 것은 아니다.

## 5. 물리–갱신 그림의 분모를 일치시킨다

기존 R6 signed 평균은 전체시간 fixed-accepted, loss 평균은 t>=30 전체후보다. 896구간 중544구간은 분모 수부터 다르다. 값 자체의 계산오류와 해석오류를 구분한다.

별도 `PHYSICS_TO_UPDATE_COMMON_POPULATION.csv`는 t>=30, BB fixed-accepted, true-pose all-axis FD-stable을 모두 만족하는 같은 표본에서 signed 항과 local loss를 계산한384구간이다. 빈/희소 구간을 명시하고 원표는 보존한다. true-pose stability와 실제 prior active branch의 안정성은 다른 조건이다. 거리·방위·tap별 겹친 집계를 새로운 독립 표본으로 합산하지 않는다.

## 6. 원고에 사용할 수 있는 문단

본 연구는 두 직교 선형편파 수신 포트의 공통 첫 경로 power에서 계산한 signed 정규화 편파비를 사용하고, 실제 복소 FFD와 송수신 좌표계를 통해 위치·Heading 민감도를4상태 Joint EKF에 반영한다. 선택한 세 경로에서는 평균 보정 이후에도 기하와 detector 선택에 따른 편파 잔차가 남으며, 그 영향은 관측 민감도뿐 아니라 prior covariance와 관측 가중치에 의해 결정된다. 동일 prior에서 평균과 추가분산을 분리한 계산은 잔여 관측오차와 예측 상태차이의 signed 갱신을 구분했고, 순간 손실과 최종 재귀 성능의 우열이 다를 수 있음을 보였다. 기존12조건에서 결합 설정은 Heading RMSE를 모두 감소시켰으나 R4에서는 XY가 악화했고 거리 lookup보다 사전 지정 상수가 더 나았다. 이 결과는 물리 기반 관측구조와 그 사용 강도의 관계를 지지하지만, 거리 lookup의 보편적 최적성이나 정확한 시간 covariance 처리를 입증하지는 않는다.

## 7. 후속 범위

우선 R4 QA guard만 제한 보완한다. 기존 결과·모델·seed·12조건을 바꾸지 않는다. 그림은 물리 민감도/잔차, 동일-prior 갱신, 전체재귀 결과의 세 층으로 나누고 공통 표본을 명시한다. V4 누적인과, physical time process, fresh ML, 외부일반화는 별도 주장으로 남긴다. MIXED 결과를 이유로 case를 재선택하거나 반례를 숨기지 않는다.
