# G2/G3 B 독립 RF 장면 보정 및 C 검증 — 최종 실행·감사 브리핑

## 0. 범위와 증빙

실행: [GitHub Actions 38556968635](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38556968635), 클라우드 SUCCESS.
원본 실행 증빙: [Artifact 11890043556](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38556968635/artifacts/11890043556).
실험 코드: run.py, 출처/해시 사전 감사: gate.py 및 SOURCE_REVIEW_KO.md, 고정 수식·임계값: CONTRACT.json.
원본 외부 RF 장면: [claude/office-e-layout at b05af070](https://github.com/myoungsunk/sionna-resimulation/tree/b05af070a87981f8712fdd41eac4c1bbb882e9c7/results), Office Sionna 35위치 및 변경 Anchor A2(15), A2B(14).
B prior 평가: [3c9d8f826f](https://github.com/myoungsunk/sionna-resimulation/commit/3c9d8f826f5cc41f43ddcf20d754f791cce19f8a).
이 실험은 B signed RF 보정/장면 전이와 C synthetic controls만 수행했다. Full nonlinear G2/G3, recurrent pose, 독립 gyro fault calibration은 실행하지 않았다.

## 1. 네 가지 분리 판정

| 항목 | 실행 가능한가 | 계산 유효성 | 가설의 지지 | 과학적 주장 |
|---|---|---|---|---|
| Office H + Anchor source | PASS | 35 + 15 + 14 H 추출, 원본 max4 detector parity 최대 1.03e-15m | 물리적/디지털 소스 매칭 확인 | Sionna 모델 장면·고정 detector에 한정 |
| B signed likelihood | PASS | 정규화된 2-component likelihood 및 signed error/coverage 계산 유효 | **Office→A2/A2B 95% tail transfer 반증** | 95/99% calibrated RF posterior/generalization CLAIM_BLOCK |
| B DR fault prior | DR-only 실제 독립 자료 없음 | 기존 synthetic prior로 C 수식 계산 가능 | 독립 gyro/wheel calibration 미검증 | CLAIM_BLOCK |
| C1–C4 guarded action | PASS | adaptive quad/independent Simpson 확률값 일치 | **guarded radial action** 사전 합성 조건 지지, 직접 확률 보정은 반례 | 실제 G2/G3 trajectory accuracy CLAIM_BLOCK |
| C alternate-anchor real RF + synthetic DR | PASS | 위치단위 스코어링 유효 | 외부 RF perturbation에 대해 synthetic DR normal/drift 대조 지지 | 독립 Gyro/odometry, actual 3D pose CLAIM_BLOCK |

B calibration hypothesis was contradicted; model was NOT refitted to heldout A2/A2B. C used valid normalized B density as exploratory trial, not calibrated scientific posterior.

## 2. 감사: 관측기 정의·중복과 진실값 누수

- Office 원본 archived max4 receiver: 각 yaw에서 4개 수신/송신 branch 중 가장 큰 branch, Hann + 4N IFFT + 30% first-path threshold.
- run.py 독립 max4 재현: Office 35개 위치의 first-path raw range mean 최대 차이 1.0269563e-15 m.
- 실제 B/C signed observation은 이전 P3 계약처럼 **TX0 fixed + strongest RX**로 선택. Office archived max4의 TX0 선택 비율은 평균 44.96%라 두 detector는 혼동 금지.
- Office archived 내부 self-fitted offset -0.5234322359m는 사용하지 않음. 기존 frozen B_OLD=-0.5315983906m 적용.
- 35개 Office 위치 × yaw19를 665개 독립 RF 환경으로 오인하지 않음; **35개 위치만 calibration unit**. A2/A2B 15+14 위치는 같은 복도 기하에서 Anchor가 달라진 correlated configurations.
- LoS-clear/blocked 판정은 합성 장면 기하의 calibration grouping으로만 사용; C decision에는 LoS oracle label이나 true gyro bias가 들어가지 않음.
- Office/A2 데이터는 실제 로봇 주행 gyro+wheel odometry를 포함하지 않으므로 DR Fault prior 독립 학습은 이 실험에서 물리적으로 불가능; 이전 synthetic p_fault=.05, sigma_fault=2.0m만 C 대조용으로 사용.
- Full/E1은 mount/receiver/feature 동등성을 외부 소스와 검산할 수 없으므로 Office에 임의 적용하지 않았음. 이번 외부 calibrated transfer 결과는 **TX0 Full/B_OLD**에만 해당.

## 3. B: 독립 장면 모델과 결과

학습할 signed RF 오차 epsilon_R=z_corrected-r_true.

Office LoS-clear 25개 독립 위치: Gaussian(μ=0.0110268056m, σ=0.0338633747m).
Office blocked 10개 독립 위치: Student-t(df=3, loc=0.1585081341m, scale=0.1186660382m).
무조건 혼합 가중치 25/35과 10/35; 외부 Anchor 시험 결과를 본 뒤 어떠한 모수/분포를 수정하지 않음. 이는 관측품질 Q에 조건부인 온라인 모델이 아니라 **Office 환경 발생비율의 unconditional mixture**.

| 자료 | n 위치 | signed mean(m) | signed RMSE(m) | 95% one-sided coverage | 99% one-sided coverage |
|---|---:|---:|---:|---:|---:|
| Office fit total | 35 | +0.11497 | 0.31791 | 97.14% (34/35) | 100% |
| Office LoS clear fit | 25 | +0.01103 | 0.03496 | 96% | 100% |
| Office blocked fit | 10 | +0.37482 | 0.59218 | 100% | 100% |
| **A2 independent scene/config** | 15 | +0.03324 | 0.13641 | **80.0% (12/15)** | 100% |
| **A2B independent configuration** | 14 | +0.04785 | 0.11399 | **85.71% (12/14)** | 100% |

모델 95% 왼쪽 꼬리 기준: signed epsilon >= -0.0504593m.
이를 벗어난 외부 위치 5개:
- A2 (3.5,-0.4) r_true=2.256m, signed=-0.071558m
- A2 (4.5,-0.4) r_true=2.256m, signed=-0.079430m
- A2 (9,-0.4) r_true=5.463m, signed=-0.074489m
- A2B (4.3,0) r_true=2.256m, signed=-0.055816m
- A2B (4.917,0) r_true=2.417m, signed=-0.051212m

원인은 계산 오류가 아니라 **기존 Office 학습 음수 꼬리보다 Anchor2 복도 장면의 under-ranging tail이 두꺼운 분포 이동**임이 관측된다. 이것이 receiver port, reflection geometry, radial bins 중 어느 변수 때문인지는 현재 데이터만으로 인과 확정하지 않는다. 내부 Office fit 35개에서 95% coverage는 일반화 증거가 아니다. A2/A2B 99% coverage 관찰 100%도 29개 상호 의존 표본만으로 보증 불가.

CIR first/peak, peak gap, FP energy fraction을 원본 H에서 산출. 각 장면 n=14–35의 Spearman(|signed error|) 상관 진단은 통계적으로 뚜렷한 일관된 고품질 predictor라는 근거 부족:
- Office peak gap rho=+0.224, first/peak rho=+0.046, FP energy rho=-0.319.
- A2 peak gap rho=+0.173, first/peak rho=+0.261.
- A2B peak gap rho=+0.219, first/peak rho=+0.220.
사전 다중검정 보정/추가 독립 test 부족; Q-conditioned signed density를 확정할 수 없음.

## 4. C: 네 가지 기존 반례 검증 (same frozen controls)

오차 관계: delta = d_DR - z_RF = e_D - e_R.
p(e_R | delta) proportional to f_R(e_R)*f_D(e_R + delta).
여기서 f_D는 이전의 미보정 DR Fault 5%, extra 2m synthetic prior다.
목표 사건은 |e_R|<|e_D|. delta>0이면 e_R> -delta/2. delta<0이면 e_R< -delta/2.
적응형 구간별 quad와 독립 fixed Simpson numeric 경로 비교가 모두 계산 정합성을 통과.

Action only:
if delta>0 AND (delta²/(sigma_DR²+sigma_inlier_RF²))>6.634896601 AND P(RF distance better)>=0.95:
    corrected radial estimate = z_RF - mu_clean.
else:
    corrected radial estimate = d_DR.
이것은 posterior 평균을 그대로 출력하는 새 필터가 아니라 synthetic guarded radial action이다.

| Fixture | DR abs error(m) | RF abs error(m) | Unguarded posterior mean abs error(m) | Guarded abs error(m) | P_RFbetter from *uncalibrated* mixture |
|---|---:|---:|---:|---:|---:|
| C1 nominal DR | 0 | 0.04000 | 0.01432 | **0** | 0.51386 |
| C2 DR drift | 2.80592 | 0.06347 | 0.03699 | **0.05244** | 0.99375 |
| C3 RF overcorrected short | 0.03000 | 0.50000 | 0.33279 | **0.03000** | 0.58992 |
| C4 RF too-long path | 0.03000 | 2.00000 | **1.89834** | **0.03000** | **0.97702** |

**중요한 추가 반증 C4:** RF가 2m 틀렸는데도 모델의 P_RFbetter=.9770이다. Guarded action이 C4를 보호한 것은 이 모델 확률을 잘 보정했기 때문이 아니라 RF가 DR보다 긴 경우 delta<=0의 **별도 부호 제약**으로 갱신을 막았기 때문이다. 따라서 C synthetic **action guard fixture PASS**와 C probability **confidence calibration FAIL**을 구별해야 함. 모델의 오른쪽 양의 오차 tail 또는 DR Fault prior 5%/2m가 잘못될 가능성이 있지만 원인은 독립 확률 보정 전 확정 불가.

## 5. C external RF + synthetic DR 검증

A2와 A2B의 실제 RF-error를 합성 DR 거리 d=r_true+0.03m 또는 d=r_true+2.8m에 결합한 대조임. 동적 DR 실제 시험 아님.

| Scenario | A2 n | A2 selected | A2 mean action MAE | A2B n | A2B selected | A2B mean action MAE |
|---|---:|---:|---:|---:|---:|---:|
| DR close (+0.03m) | 15 | 0 | 0.0300m | 14 | 0 | 0.0300m |
| DR drift (+2.8m) | 15 | 15 | 0.08829m | 14 | 14 | 0.07532m |

모든 조작 시점은 no_truth-leak formula로 선택한 후 scoring truth 비교. 그러나 d는 정답으로부터 합성된 것이므로 실물 gyro/wheel sequence 입증은 절대 아님.
**우위 확률 C4 오판**과 **외부 signed-tail 95% coverage 불일치**는 여전히 존재한다. 알고리즘을 임의 retune하지 않음.

## 6. 감사 등급별 결론과 향후 방향 (승인받기 전 실행하지 않음)

HARD_EXECUTION_BLOCK: 없음. Source/Office legacy detector parity and finite H pass.
CASE_RESULT_INVALID: 계산 실패 없음 (적분 일치, B density normalization algebra, raw source parity success).
CLAIM_BLOCK:
(1) Office→A2/A2B 95% one-sided RF bound calibration generalization;
(2) C4 에서 uncalibrated pwin 97.70% RF-superiority misprediction;
(3) external E1 and online CIR-quality calibration;
(4) independent DR Fault prior with real gyro/odom;
(5) entire 3-state G2/G3 and recursive fusion generalization.
DIAGNOSTIC_DEFECT_OR_WARNING: 필수 결과를 무효화할 진단 오류는 이 실행에서 발견되지 않음.

**Next hypothesis before adoption**: freeze externally determined RF signed tail/error model conditioned on deployable CIR Q, and calibrate DR Fault prior using genuinely independent dynamic gyro/odom sequences. Then hold out distinct scene and anchor family, assess pwin (both positive and negative delta), probability reliability (PIT/Brier/ECE), and C1–C4 plus long-path C4 false-confidence. This is a NEW model hypothesis; no opportunistic parameter fitting on A2/A2B test labels.
No Stage D/E/F executed, scientific_PASS=false.

## Machine-readable evidence
- outputs/BC_CROSSSCENE/PRE_RUN_{BOOTSTRAP,EXTRACT,B,C}.json
- outputs/BC_CROSSSCENE/H_EXTRACTION.json
- outputs/BC_CROSSSCENE/INDEPENDENT_SCENE_RF_POSITIONS.csv
- outputs/BC_CROSSSCENE/B_INDEPENDENT_SCENE_TRANSFER.csv
- outputs/BC_CROSSSCENE/B_Q_DESCRIPTIVE_SPEARMAN.csv
- outputs/BC_CROSSSCENE/B_REPORT.json
- outputs/BC_CROSSSCENE/C_REPORT.json
- outputs/BC_CROSSSCENE/C_EXTERNAL_STATIC_RF_SYNTHETIC_DR.csv
