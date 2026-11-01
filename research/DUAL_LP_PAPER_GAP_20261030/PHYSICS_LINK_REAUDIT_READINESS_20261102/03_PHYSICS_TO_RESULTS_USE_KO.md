# 유효 데이터에 근거한 물리적 관측구조–EKF 갱신–성능 연결 (V3 재감사 반영)

**갱신일:** 2026-11-02. **논문 범위:** 기존 R2-B/R4-B/R5-B × B0/L0/L1/L2 = 12조건, C0 Corridor Anchor B, Mount 0°, 기존 4상태·정수 first-path 거리·signed 편파비·EXDS 평균 교체·편파 거리 lookup·각 arm self-gate를 보존한다.

**판정 갱신:** 2026-11-02 R4 QA V3의 별도 AI 재감사 결과는 [ACCEPT_WITH_BOUNDARIES](https://github.com/myoungsunk/sionna-resimulation/blob/a0ce36e8bb2a3f331b07775d9454bfb743030437/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_R4_QA_V3_INDEPENDENT_REAUDIT_20261102/FINAL_AUDIT_VERDICT.json)이다. 이전 R4-OPEN-01/02/03 결함은 해당 변경에 대해 종료되었다. 원본 15503350… 커밋 MISSING, 외부 사람의 감사 서명 없음, 독립 신규 물리장면 미검증, V4 누적인과 미실행, V5 fresh ML inference BLOCKED, 전체 과학적 결과 MIXED는 **그대로**다. V3 수정은 QA 코드만이며 기존 EKF·관측·성능 결과를 변경하지 않았다.

## 1. 데이터 유효성 및 계보

| 자료 | 인정할 수 있는 용도 | 금지할 확대 해석 |
|---|---|---|
| 기존 Full/LoS·SourceFFD 및 3,136개의 고유 물리 packet | 복소 FFD, 두 포트 power, ratio, signed error, 특정 pose의 Jacobian | 실제 하드웨어 교정 또는 특정 반사체의 단일 원인 확인 |
| 9,408개의 유한차분 검사 | branch-stable 9,356건의 수치 미분 PASS, 전환 52건 별도 분류 | 전환점에서 전역 미분가능성 또는 확률 우도 정합 |
| 50,176개의 동일 BB prior 갱신 후보 | 평균×분산 2×2, signed Kε/Kδh와 국소 MSE | 다른 arm의 변화한 prior 또는 전체 재귀의 누적 인과기여율 |
| 132개 실제 trace / 144개 논리 비교 | 선택 12조건의 fixed/self 재귀·점수 재계산 | 144개 독립 RF 실험 또는 신규 scene 일반화 |
| R6 896개 구간 집계 및 384개 공통표본 구간 | 기하·tap별 탐색적 signed 갱신/국소손실 정렬 | 다른 분모 통계를 원인 기여율로 계산 |

V3 별도 AI 검증 기록: 필수 5,729/5,729, 선택 2/2, 음성·메타시험 76/76, pytest 8/8, 이전 V2 검사 5,290행 전 필드 동일, 추가 441행. 독립 scratch 계산 122건, 원 데이터 반례 96건, timestamp/분모 guard 720건이 제시되어 있다. 이 승인 범위는 **R4 QA 오류 수정 및 기존 회고적 계산의 조건부 이용**이다.

## 2. 물리적 관측구조: 무엇을 주장할 수 있는가?

두 수신 직교 편파의 **공통 첫 경로 tap** 전력으로
\[
s(\mathbf x)=\frac{P_+(\mathbf x)-P_-(\mathbf x)}{P_+(\mathbf x)+P_-(\mathbf x)},\qquad
\partial_u s=\frac{2(P_-\partial_u P_+-P_+\partial_u P_-)}{(P_++P_-)^2}.
\]
실제 복소 FFD, 송수신 좌표계 변환, 동일 CIR/strongest-port 30% leading-edge 검출로 정의한 \(h_s,\mathbf H\)를 **물리 기반 관측모델**로 기술한다. 두 포트에 공통인 복소 스칼라는 이상적인 ratio에서 사라질 수 있지만, 차등 편파 응답·반사 중첩·검출 선택은 ratio 오차로 남는다. 거리 예측은 원래 continuous bridge이며, 정수 first-edge 거리의 정확한 likelihood를 새로 검증한 결과로 해석하지 않는다.

서로 다른 두 표본집합을 혼합하지 않는다.

| 물리·기하 진단 (t≥30 s, gate 비선택) | R2-B | R4-B | R5-B |
|---|---:|---:|---:|
| packet 수 | 829 | 592 | 1265 |
| 기록된 \(\lvert H_{s\psi}\rvert\) 중앙값 (rad\(^{-1}\)) | 0.461 | 1.775 | 0.405 |
| 평균 교체 후 편파 잔차 RMS | 0.107 | 0.123 | 0.093 |
| Full–LoS signed s 차이 RMS | 0.113 | 0.117 | 0.095 |

이는 **true-pose, active-branch 수치진단**이다. 실제 필터 prior의 정보량, 물리 ray별 독립 인과 기여, 전체 4상태 관측가능성을 의미하지 않는다. R4-B에서 Heading 민감도가 작아서 효과가 작았다는 설명은 지지되지 않는다. 별도 동일 BB BASE-accepted \(t≥30\) B0 잔차 자료에서는 거리 RMS가 R2 8.19→5.16 cm, R5 8.41→4.63 cm, R4 7.97→5.58 cm로 줄지만, 이것을 위치오차의 동일한 감소로 읽을 수 없다.

기존 B0 전체 시간축의 lag-1 편파 잔차 자기상관은 R2-B 0.8620, R4-B 0.7280, R5-B 0.7623이다. 정적 공간 field를 따라 이동하며 얻은 **시간순 잔차의 지속성**으로 기술하고, 독립적인 실제 시간 변화나 joint temporal covariance가 완성됐다고 쓰지 않는다.

## 3. 물리 관측에 근거한 모델 가정과 직접 갱신

유지할 EKF 상태는 \(\mathbf x=[x,y,\psi,b_g]^T\)이고, 거리 평균 \(\hat\mu_r^{EXDS}\)와 편파 추가분산 \(\sigma_b^2(\rho)\)의 조합은
\[
\boldsymbol\mu^M=[\hat\mu_r^{EXDS},\hat\mu_s^B]^T,\quad
R^M=R^B+\mathrm{diag}(0,\sigma_b^2(\rho_{\mathrm{lookup}})).
\]
\(\rho_{\mathrm{lookup}}\)은 원 구현과 동일하게 **motion prediction 직전 저장된 posterior 상태**로 계산한다. 이 추가분산은 실제 FFD로부터 유도한 noise covariance가 아니라 기존 자료에서 정의한 거리 조건별 **경험적 관측 신뢰도 조절**이다. 첫 tap 인접 \(\Delta s\)는 EXDS 거리 평균 회귀의 특징이지 신규 독립 EKF 관측이 아니다.

\[
\nu=z-h(x^-)-\mu
=\underbrace{z-h(x^{GT})-\mu}_{\epsilon}
+\underbrace{h(x^{GT})-h(x^-)}_{\delta h},
\quad \Delta x=K\epsilon+K\delta h.
\]
별도 재계산한 power→ratio 항등식 최대차 4.22e−13, innovation 분해 7.16e−16, signed K 투영 2.37e−16은 연산 연결이 맞다는 근거다. 그러나 \(K\epsilon\)과 \(K\delta h\)가 **서로 상반된 갱신**일 수 있으므로 같은 prior에서 gain 감소가 항상 즉시 오차 감소를 뜻하지는 않는다.

R2/R5의 8조건에서는 동일 BB prior의 **조건별 평균 즉시 Heading MSE**가 평균-only보다 결합모델에서 더 컸지만, 실제 full recursion Heading RMSE는 결합모델에서 작았다. “추가분산이 매 packet마다 Heading 오차를 감소시켰다”는 주장은 **금지**한다. V4가 없어 특정 공간 구간의 최종 누적 기여율도 확정하지 않는다.

## 4. 최종 재귀 성능의 사용 범위

| B0 / self | BB_ORIG Heading/XY | MB_VAR Heading/XY | 사전 지정 MB_CONST Heading/XY |
|---|---|---|---|
| R2-B | 1.2047° / 6.8269 cm | 1.0847° / 5.3303 cm | 1.6253° / 10.7688 cm |
| R4-B | 1.4418° / 8.5363 cm | 1.4312° / 9.4325 cm | 1.1369° / 5.4898 cm |
| R5-B | 1.0731° / 8.6882 cm | 0.6434° / 4.4551 cm | 1.4293° / 12.5319 cm |

총 12조건에서 결합모델 Heading 감소 12/12, XY 감소 8/12. 반면 **분산만 추가한 BB_VAR도 Heading 12/12 감소**이며, R2/R5의 8조건에서는 MB_VAR가 각각의 단독 개입보다 Heading·XY 모두 낫지만 R4의 4조건에서는 BB_VAR가 MB_VAR보다 두 지표 모두 낫다. 결합의 고유 필요성을 전체 Heading 감소 개수 하나로 주장하지 않는다.

상수 대비 거리 lookup은 R2/R5의 8조건에서 우수, R4의 4조건에서 열세다. fixed에서도 같은 우열이 남아 gate 수용집합만의 효과는 아니지만, 이후 재귀 prior 변화까지 완전히 인과적으로 분해한 것은 아니다. 단일 실험 장면과 후향적으로 선정된 12조건임을 보존한다.

## 5. R6 구간 집계와 논문 반영 규칙

원 R6 896개 구간에서 signed \(K\epsilon, K\delta h\)는 전체시간 fixed-accepted 표본, local loss는 \(t\ge30\) 전체후보를 사용하며 **544구간은 분모부터 다르다**. 이 평균들을 동일 집합의 인과 효과처럼 나란히 쓰지 않는다. 보완된 384구간 표는 \(t\ge30\cap\) fixed accepted \(\cap\) true-pose FD stable의 공통 표본이다. group_type끼리 표본 중복이 있으므로 합쳐 하나의 유효 표본수로 세지 않는다. true-pose stable은 필터 current-prior stable과 같지 않다.

**논문 배치:** 
1. **물리 관측:** FFD→포트→공통 tap→편파비·Jacobian, 오차·상관의 조건부 관찰.
2. **물리 관측에 근거한 모델:** 기존 4-state, EXDS Range 평균 교체, 편파 추가분산, NIS/ Joseph 갱신, 동일-prior의 \(K\epsilon/K\delta h\) 기전.
3. **결과:** 12조건 표, 2×2 단독/결합, 사전 지정 상수 대 lookup, R4의 반례, 불확실성·출처 제한.

**완성된 논문 초안:** [PAPER_DRAFT_PHYSICAL_MODEL_RESULTS_KO.md](../PHYSICS_LINK_PAPER_3PART_20261102/PAPER_DRAFT_PHYSICAL_MODEL_RESULTS_KO.md).

## 6. 허용 주장과 금지 주장

**허용:** 실제 복소 FFD와 signed 비율 관측함수의 수치정합성, 안정구간 Jacobian, 조건별 거리·편파 잔차, 동일-prior signed 갱신, 지정된 12조건의 재귀 Heading 감소 및 XY의 경로별 상반된 결과, 사전 지정 상수 대비 lookup의 조건부 효과.

**금지:** 편파 추가분산이 정확한 시공간 covariance를 복원함, 모든 packet의 즉시 Heading 오차가 감소함, R4의 특정 ray가 유일 원인임, 12조건이 독립 물리장면임, 거리 lookup이 보편적으로 최적임, 새 환경에서 fresh inference 검증 완료, 원본 15503350… 실행 복원 또는 외부 사람 독립 감사 서명.

**자료 및 출처:** [기준 원고 v4](https://github.com/myoungsunk/sionna-resimulation/blob/1aac4d38/research/DUAL_LP_PAPER_GAP_20261030/PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md) · [R4 QA V3 AI 재감사](https://github.com/myoungsunk/sionna-resimulation/blob/a0ce36e8bb2a3f331b07775d9454bfb743030437/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_R4_QA_V3_INDEPENDENT_REAUDIT_20261102/README_KO.md) · [R1–R5 claim ledger](https://github.com/myoungsunk/sionna-resimulation/blob/ca8cb43777100a0f5fae53978c0e4096d49701ff/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_REPAIR_V2_20261102/CLAIM_LEDGER_V2.md).
