# 12 — 기존 7케이스 First-arrival LP 비와 Sensor-v2 heading 신뢰도: 실제 실행 결과

실행일: 2026-10-10  
실행 소스: codex/closed-loop-probe-fpcluster-20261010, run_first_arrival_cluster_association.py  
GitHub Actions run: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38051518352  
실행 상태: **FIRST_CLUSTER_ASSOCIATION_COMPLETED** / **ONLINE_TRIGGER_STOP_PROBE_RESUME_NOT_RUN**. 기존 H/LUT/센서 소스는 수정하지 않음.

## 1. 설계 오류 정정

사용자가 요구한 시스템은 **매 0.2초 정상적인 6상태 Sensor-v2 EKF 주행 중 낮은 RF heading 신뢰도 감지 시 제자리 정지, 추가 1–2각(최초 관측 포함 총2–3점) RF 측정, 모든 관측의 공동 가중 업데이트, 헤딩 복귀 후 매시점 EKF를 계속 운영하는 closed-loop** 이다. 기존 7.030°은 16개 유일 물리 위치의 RF-off prior에 대해 오프라인으로 3점만 적용한 결과이므로 요구 시스템의 성능이 아니다. 위 설계를 10번 사양서, 06/08/10 통합한 11번 실행 전달본에 명시했다.

본 보고서의 **실행**은 first-arrival 특징의 heading 분별력에 국한한다. 새 주행 이벤트, 정지/회전 시간, yaw noisy control, full P6 EKF posterior-to-future 갱신은 미실행이다.

## 2. 채널/안테나 및 관측 parity

전체 7 케이스: R2_aA_m0, R2_aA_m45, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0. 한 개의 TX +45° LP, RX ±45° LP, 단일 앵커 A 또는 B, 6.2504–6.7496GHz 257 bins. 동일 corridor geometry. 총 9,519 pose-case full H + 9,519 pose-case clean LoS H.

동결 기존 first-path receiver 관측 체인: Hann → 4N zero-padding → complex IFFT×N → stronger RX의 30%-leading-edge 정수 tap → 양 RX 포트 동일 tap의 P1/P2 → s=(P1−P2)/(P1+P2).
독립 재계산한 FP s와 원본 feature의 최대 절댓값 차이는 1.11e−16, matched LoS s도 1.11e−16, e_MP 차이 2.22e−16이며 FP tap 인덱스는 정확히 일치하여 관측 parity가 PASS했다. 이는 파형 처리 검산이지 원 모델 F01/L1/L2가 해결됐다는 의미가 아니다.

## 3. First-arrival 공통 창

FP 선택 tap k에서 시작해 [k,k+L) zero-padded CIR를 양 RX에서 정확히 같은 window로 적분한다. L=4,8,16 taps는 각각 약 1.9956/3.9908/7.9816ns; sample grid step 0.49885264ns. 4× zero-padding은 물리 경로 분해능을 4배 높이지 않음. 원 channel noise-free이며 noise-floor correction=0.

| 창 폭 | 실제 s_L과 s_FP의 절댓값 차이 중앙값 | p90 |
| --- | ---: | ---: |
| 약 2ns (L4) | 0.03948 | 0.17300 |
| 약 4ns (L8) | 0.09826 | 0.37413 |
| 약 8ns (L16) | 0.14525 | 0.48583 |

Clean LoS와 full-multipath를 모두 동일 규칙으로 처리한 **oracle** e_MP,s 의 전체 RMS: 단일 FP=0.17011, 2ns 창=0.25068, 4ns 창=0.32865, 8ns 창=0.36437. 이는 **각각 다른 관측정의를 가진 정규화 전력비**에서의 LoS 대비 오류 크기이며 cluster 폭이 길수록 물리적으로 "더 오염됐다"는 주장으로 사용하지 않는다. 물리적 clean-polarization baseline과 창 효과를 반드시 구분할 것.
FP oracle |e_MP|<0.05 이면서 2ns oracle |e_MP,L4|>0.1인 경우는 6.85%였으며 4ns 22.44%, 8ns 33.27%였다. FP 단일 tap에서 놓칠 수 있는 편파응답 변화를 wider early gate가 보이지만, 이것은 **직접 LoS 채널을 아는 oracle 진단**일 뿐 online trigger로 그대로 계산할 수 없는 값이다.

## 4. 실제 RF heading 정확도와의 association

기존 sensor-v2 RF-off prior 기반 LUT inverse heading label: 같은 RF를 여러 gyro/wheel seed로 반복하므로 (case,pose_id)로 집계한 **6,201개 서로 다른 case-pose**에서 모델을 fitting/평가한다. 전체 available v2 heading label은 R2 281,894, R4 172,529, R5 204,216개이며 **서로 다른 RF 환경 658,639개가 아님**. 모든 실제 label은 역 LUT 후보를 RF-off prior 기준으로 선택했으며 truth yaw로 root를 선택하지 않았다. No-match/ambiguous sample은 original label evaluation에서 제외, 결과에 denominator/availability와 no-match 별도 처리할 것.

분류 목표: error(psi_RF,psi_true)<=5°. 실험은 leave-one-ROUTE-out, train-only imputation/scaling, L2 logistic, RF pose 단위 binomial count weights, route station cluster bootstrap seed=20261010 1000회. Brier 작을수록 좋고 모델은 새로운 물리환경에서 calibrated되었다고 주장하지 않는다.

| Heldout route | FP_ONLY Brier | FP + ~2ns gate Brier | FP + ~2/4/8ns gates Brier | FP + 기존 CIR shape Brier |
| --- | ---: | ---: | ---: | ---: |
| R2 | 0.23640 | 0.23439 | **0.23236** | 0.24382 |
| R4 | 0.23937 | **0.21962** | 0.22317 | 0.23920 |
| R5 | 0.24130 | 0.23256 | **0.22914** | 0.24109 |

FP_ONLY 입력: measured range, log firstpath power sum, signed s_FP, |s_FP|.
FP+gates: FP_ONLY + measured s_L4,s_L8,s_L16 및 |s_L−s_FP|. Oracle multipath mismatch, clean LoS model, true pose 등은 training feature가 아니다.

### First-cluster 정보 추가의 bootstrap 검산

기준 FP_ONLY 대비 FP+3 gates의 station-block paired Brier delta와 95% CI:
- R2: **−0.00405** [−0.00754, −0.00064]
- R4: **−0.01621** [−0.02193, −0.01065]
- R5: **−0.01216** [−0.01633, −0.00761]

세 경로 모두 조건부 Brier 개선은 0 아래에 있다. 그러나 이 route가 모두 한 복도여서 **cross-geometry 일반화 불가**, station 위치의 공간적 독립성도 완전하지 않다. R4의 단일 2ns창 Brier가 전체 gates보다 더 작았어도 사후 선택해 main 모델을 바꾸지 않는다.

### Raw 특징과 heading 오류의 직접 상관

같은 case/pose에서 mean absolute heading error와 FP |s|의 Pearson: R2 +0.330, R4 +0.252, R5 +0.142. First-cluster |s_L−s_FP|의 상관은 일관된 양의 방향이 아니므로, "클러스터와 FP 차이가 크면 항상 heading이 나쁘다"는 **선형 단변량 규칙**으로 축소하면 안 된다. 위 개선은 다수 특징을 결합한 로지스틱 모델의 조건부 예측효과이며 직접 탈편파율 측정도 아니다.

## 5. Sensor feasibility와 다음 실제 주행 실험의 미해결 항목

본 first-cluster 자료는 Sionna complex H를 **오프라인 IFFT한 magnitude-CIR**이다. 실제 amplitude-only UWB 모듈이 시간축 전체 CIR magnitude를 외부에 제공하는지 확인되지 않았다. 포트 firstpath P1/P2만 모듈에서 접근 가능한 경우 H2/H3 quality 특성은 사용할 수 없고 FP_ONLY arm만 물리 적용 가능하다.

기존 원본 RF 저장자료는 169 case-station yaw groups이나, Tnone RF-off prior를 매칭해 정량화된 프로브 subset은 **34 case-station groups, 16 고유 물리 위치**뿐이다. 실시간 주행 중 임의의 낮은 신뢰도 trigger 위치에서는 새 yaw의 H가 없으므로 **정지 후 새로운 2/3점 RF를 기존 H에서 최근접 보간하여 진짜 생성됐다고 주장할 수 없다**. New actual station coordinate+yaw H generation or on-demand Sionna required. Mount 45° 신규 5 케이스도 아직 필요하다.

추가적인 closed-loop test에서는:
1. 매시점 x6/P6 prediction→odom→range→RF reliability q. High q good means normal FP s update; low q means RF update **보류 후 정지**.
2. Physical stop/rotation/measurement/return/restart under v2 noise with real elapsed time. FP first cluster ratio measured in a common window for each yaw. Initial low-q s measurement included once, not applied twice.
3. Correlated batch or mixture with q_site/q_i and full pose covariance, avoid independent 2/3 point R and avoid conditional single-yaw-only posterious. If all signals bad, covariance should reflect uncertainty rather than force heading.
4. Additional RF generated at actual triggered x/y/orientation (never truth-select root or nearest full H).
5. Full-route heading/position RMSE + NEES/coverage + added stop time and false positives; mount0/45 paired 12 cases. Completely new scene required for generalization.

**상태:** 1–3의 first-cluster feature extraction, comparison to archived RF-heading correct label done; 4–5 of actual event-driven closed-loop EKF **NOT_RUN**. Original F01/F02 OPEN, scientific_PASS=false.

관련 실행/명세:
- 10_CORRECTED_ONLINE_EKF_TRIGGER_PROBE_FIRST_CLUSTER_KO.md — closed-loop policy.
- 11_COMBINED_CLOSED_LOOP_EKF_ACTIVE_PROBE_AND_FIRST_CLUSTER_HANDOFF_KO.md — 06+08+10 통합.
- 10A_FIRST_ARRIVAL_CLUSTER_ANALYSIS_PREREG_KO.md — 본 분석 사전등록.
- GitHub Action 38051518352 output artifact first-arrival-cluster-analysis-20261010 with 13 files: first cluster features/oracle labels separate, calibration, station cluster CIs, parity and execution status.
