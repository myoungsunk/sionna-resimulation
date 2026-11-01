# Dual-LP Heading 논문 — 성공 모델 중심 데이터 선정본 v3

2026-11-01 | 제안자 문서 개정 | 기존 결과 선정·설명 구조 정리 | 신규 구현·실험 없음

## 이번 논문이 전달할 내용

> **Dual-LP 관측의 오차 특성을 반영한 모델링이 단일 앵커 Heading·위치 추정을 개선한다. 어떤 분석이 각 모델 구성요소를 뒷받침하며, 그 조합이 어떤 일관된 성능 향상으로 이어지는지를 보여준다.**

실패 원인을 규명하는 논문이 아니다. 이전 v2의 ‘A/B에서 왜 이득이 유지되거나 무너지는가’라는 질문은 **한계 분석**으로 이동한다. 본문은 **성공 데이터 선정 → 성공을 설명할 특성 분석 → 모델 구성의 근거 → 성능**으로 연결한다. 연구 수행 순서도 데이터 선정과 설명 검증을 앞에 두며, 이번 문서 개정이 최종 알고리즘 동결을 뜻하지 않는다.

[이전 v2 원문](https://github.com/myoungsunk/sionna-resimulation/blob/2e6431fbed4982f4d02e1bd26bad52baaba200d8/research/DUAL_LP_PAPER_GAP_20261030/PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md)은 Git 이력으로 보존한다. 기존 상세 자료를 모두 다시 서술하지 않고 아래 성공 묶음만 본문의 중심으로 선정한다.

## A. 우선 선정: 하나의 모델, 같은 앵커·장착각, 두 경로

**현재 확인한 기데이터에서 성공을 중심으로 구성할 묶음은 `MB_VAR / self-gate`와 `R2_aB_m0`, `R5_aB_m0`이다.** 같은 모델 구성·분산표를 유지한 채 B0/L0/L1/L2 전체를 사용한다. 성공한 bias 수준만 개별적으로 골라 붙이지 않는다. [S1–S3]

| 고정/변경 요소 | 이번 본문 선정 |
|---|---|
| 공간·안테나 | 동일 C0 Corridor, 동일 Dual-LP 및 SourceFFD 계열 |
| 앵커 | **B=(10,0,2.65) m**, 단일 앵커 |
| 수신 장착각 | **0°** |
| 주행 경로 | **R2와 R5** — 성공이 서로 다른 경로에서 반복되는지 제시 |
| 관측 | 주 성능은 Full RF; 동일 포즈의 Native LoS는 컨셉·정상 조건 대조용 |
| 비교 모델 | 기존 `BB_ORIG` 대 동일 `MB_VAR`, 모두 **self NIS gate** |
| bias 조건 | B0=0, L0=+0.01, L1=+0.05, L2=+0.20 °/s, **전부 포함** |
| 시드·평가 | 기존 sensor/initial seed 0; 재귀 t=0부터, 점수 t≥30 s |
| 성공의 현재 정의 | 기준선보다 **Heading RMSE와 XY RMSE가 모두 감소** |

이 조건에서 **2개 경로 × 4개 bias = 8개 조건 모두 동시 개선**이 확인된다. 같은 RF에 센서 bias를 바꾼 조건들이므로 8개 독립 환경이나 다중 시드 강건성의 증거는 아니다. 아래 숫자는 한 실행 계열의 기존 CSV에서 같은 키로 가져왔다. [S1]

**선정은 ‘Anchor B이면 항상 성공한다’는 가설이 아니다.** 같은 B에서도 R4는 경계 사례로 남는다. 정확한 성공 범위를 먼저 명시한 뒤 그 공통된 물리·통계 특성을 다음 분석에서 확인한다.

## B. 무엇이 성공했는가: 모델의 구성부터 정확히 정의

선정한 `MB_VAR`는 **CIR·Δs 기반 Range 평균 보정과 거리 조건별 편파 추가분산을 결합한 4-State EKF**이다. Δs로 Heading을 직접 보정하거나 편파 평균만 새로 학습한 모델로 바꿔 설명하면 안 된다. [S2–S4]

| 구성요소 | 실제 기존 구현 | 원고에서 설명할 역할 |
|---|---|---|
| Dual-LP 관측 | SourceFFD 기반 h_s와 [r,s] 공동 관측 | 단일 앵커에 Heading-sensitive 정보를 제공 |
| **Range 평균 보정** | 기존 CIR+Δs 특징으로 예측한 전체 Range 오차 평균 `MU_R_EXDS`로 기준선의 Range 평균을 대체. 편파 평균은 기존 값을 유지 | 관측에 포함된 구조적 Range 오차를 줄임 |
| **편파 추가분산** | 기존 R_ss에 거리 조건별 σ_b²를 더함. R_rr 및 나머지 항은 원 설정 유지 | 편파 관측의 잔여 불확실성에 맞춰 업데이트의 신뢰도를 조절 |
| 재귀 융합 | 같은 [x,y,ψ,b_g] 운동모델과 자기 상태 기반 NIS gate | 평균과 불확실성 처리가 실제 누적 추정 성능으로 이어지는지 평가 |

개념적인 모델 표기는 다음 정도로 제한한다.

\[
\boldsymbol\mu_k^M=[\hat\mu_{r,k}^{\mathrm{EXDS}},\hat\mu_{s,k}^{B}]^T,\qquad
R_k^M=R_k^B+\operatorname{diag}\{0,\sigma_b^2(\hat\rho_k^{\mathrm{lookup}})\}.
\]

관측 혁신은 z−h(x⁻)−μᴹ이고, 각 시점의 자체 혁신·공분산으로 공동 NIS gate를 판단한다. **기존 결과의 정확한 실행 의미**는 [S3] 코드를 따른다. 코드에서 거리 기반 σ_b는 motion prediction **이전의 보유 상태**로 조회한다. 이를 현재 시점 predicted prior에서 조회했다고 원고에 바꾸어 적지 않는다. 조회 시점을 변경하면 다른 구현으로 취급한다.

기존 σ_b 표는 거리 [0, 1.5, 3, 6, 10] m에 대해 [0.011, 0.02, 0.05, 0.12, 0.24]의 보간값이다. 이는 해당 연구의 경험적 설정이며 분석에서 유일하게 도출된 최적값이 아니다. 이번에는 이 값을 수정하거나 새 모델을 실행하지 않는다. [S2]

## C. 본문용 성공 데이터: 8개 조건을 하나의 표로

**Full RF·Mount 0°·Anchor B·seed 0·자체 gate.** Heading은 degree, XY는 cm. 감소율은 각 조건에서 100×(1−MB_VAR/BB_ORIG)로 계산했다. 평균 성공률이나 pooled RMSE가 아니다. `BB_ORIG`는 기존 POWER 계열 보정 기준선이며 **고정 R0 Conventional J4와 다르다.** [S1, S4]

| 경로 | Bias | Heading: 기준 → 모델 (°) | 감소율 | XY: 기준 → 모델 (cm) | 감소율 |
|---|---|---:|---:|---:|---:|
| R2-B | B0 | 1.205 → 1.085 | 10.0% | 6.83 → 5.33 | 21.9% |
| R2-B | L0 | 1.184 → 1.057 | 10.7% | 6.75 → 5.22 | 22.7% |
| R2-B | L1 | 1.112 → 0.968 | 13.0% | 6.48 → 4.91 | 24.2% |
| R2-B | L2 | 0.947 → 0.813 | 14.1% | 5.77 → 4.30 | 25.6% |
| R5-B | B0 | 1.073 → 0.643 | 40.0% | 8.69 → 4.46 | 48.7% |
| R5-B | L0 | 1.046 → 0.635 | 39.3% | 8.52 → 4.45 | 47.7% |
| R5-B | L1 | 0.943 → 0.602 | 36.1% | 7.84 → 4.45 | 43.2% |
| R5-B | L2 | 0.716 → 0.615 | 14.0% | 6.09 → 4.65 | 23.7% |

**현재 사용할 수 있는 결과 문장:**

> 동일 Corridor의 Anchor B·Mount 0°에서, Range 평균 보정과 편파 추가분산을 함께 적용한 모델은 R2 및 R5의 네 gyro-bias 수준 모두에서 기존 보정 기준선보다 낮은 Heading 및 XY 오차를 보였다. 조건별 감소율은 Heading 10.0–40.0%, XY 21.9–48.7%였다. 비교에는 고정된 외부 수용집합이 아닌 각 필터의 자체 NIS gate를 사용하였다.

이는 **선정한 조건의 점추정 정확도 개선**에 관한 문장이다. 독립 환경 일반화·다중 시드 성공률·완전한 posterior calibration 또는 DR/3-anchor 대비 우위를 이 숫자로 주장하지 않는다.

### 구성요소를 설명하는 최소 ablation

단순히 ‘특화 모델이 좋다’가 아니라 **평균 보정과 편파 신뢰도 조절의 조합이 왜 필요한지** 설명할 수 있도록, 같은 CSV의 B0 네 arm만 대표 표로 남긴다. 각 칸은 Heading ° / XY cm이며 모두 self-gate다. [S1]

| 경로 | 기준 BB_ORIG | 평균만 변경 MB_ORIG | 분산만 추가 BB_VAR | 평균+분산 MB_VAR |
|---|---:|---:|---:|---:|
| R2-B | 1.205 / 6.83 | 1.616 / 6.80 | 1.122 / 7.54 | **1.085 / 5.33** |
| R5-B | 1.073 / 8.69 | 0.825 / 5.78 | 0.967 / 8.65 | **0.643 / 4.46** |

두 경로에서 결합 모델이 두 단독 변경보다 Heading·XY 모두 낮다. 동일 CSV의 L0/L1/L2에도 이 순위가 유지되는 것을 확인했다. 따라서 **두 구성요소를 함께 사용하는 설계의 경험적 근거**로 활용한다. 단, 자체 gate 비교이므로 성능 차이에는 이후 수용집합·상태·공분산의 변화도 포함된다. 특정 물리 인과기여율이나 두 요소의 통계적 독립성을 증명하는 표는 아니다.

## D. ‘어떤 분석 → 어떤 모델 구성 → 어떤 성능’의 연결

본문에서는 아래 연결만 남긴다. 분석 자료를 있는 대로 나열하는 것이 아니라 **성공 모델의 설계 이유를 설명하는 자료**를 같은 R2-B/R5-B에서 갈무리한다.

| 설명할 특성·분석 | 대응 모델 구성 | 사용할 성공 근거 | 현재 근거와 다음 확인의 경계 |
|---|---|---|---|
| LoS 편파비의 Heading 민감도와 다중경로 왜곡 | SourceFFD h_s를 통한 직접 r/s 융합 | 성공 사례의 h/J·상태 궤적, 최종 Heading RMSE | 기존 물리 모델 검증 이용. 성공 사례만의 동일 포즈 연결을 유지 [S5] |
| CIR·Δs에 포함된 Range 오차의 구조적 정보 | μ_r를 EXDS 예측값으로 대체 | 평균-only 및 결합 모델 비교, raw/보정 후 Range 잔차 | 실제 μ_M은 Range 평균의 교체다. 편파 signed-bias 보정으로 서술하지 않음 [S4] |
| 위치·거리별 편파 잔여오차와 추정 신뢰도 차이 | σ_b(ρ)² 추가를 통한 편파 신뢰도 조절 | 분산-only 및 결합 모델의 Heading·XY·coverage | 거리별 잔차·prior 오차 분해를 연결하되 경험적 표를 분석적 최적해로 설명하지 않음 [S2, S6] |
| **시간·공간 상관과 정보 이용 — 핵심 분석** | 후속 분석에서 성공한 가중 방식의 이유를 검증하고 최종 모델에 필요한 항만 확정 | 같은 두 성공 사례의 시간순 ε, ν, P, 수용 이력과 결과 | 현재 VAR는 cross-time covariance를 명시적으로 모델링하지 않는다. 성능 성공을 곧 시간상관 문제의 해결로 주장하지 않음 [S6] |

**남길 데이터 묶음:** 선택한 두 case의 paired Full/LoS H·pose/time → raw r/s·평균보정값·조건부 불확실성 → 시간순 prior/posterior·NIS/gate → Heading/XY·coverage. 근거가 다른 관측모델·다른 시드·다른 mask인 결과를 연결하지 않는다. S6의 전체 경로 요약값을 선택 사례의 수치로 오인해 사용하지 않는다.

‘분석 → 모델 → 성능’은 논문의 설명 순서다. 실제로 사후에 확인한 설명을 설계 전에 이미 증명한 것처럼 연구 이력을 바꾸지는 않는다. 아직 성공의 구체적인 물리 원인이 확정되지 않은 부분은 다음 분석에서 확인한다. **모델은 성공한 후보로 먼저 선정하되, 최종 구성 확정은 설명 검증 뒤에 한다.**

## E. 고정된 6단계 논문에 배치할 최소 내용

| 논문 단계 | 중심 내용 | 이번 선정 데이터의 역할 |
|---|---|---|
| **1. Simulation Setup** | 동일 Corridor·Anchor B·Mount 0°·R2/R5, 공통 센서/평가 조건 | 설정 한 표·경로도. A/B 실패 대조를 셋업의 주 목적으로 삼지 않음 |
| **2. Dual-LP Concept** | 단일 앵커에서 편파비가 Heading 정보를 제공하는 원리 | 같은 사례의 Native LoS와 SourceFFD h/J |
| **3. Characteristics** | 성공 모델의 구성요소가 필요한 물리·통계적 이유 | D절의 연결. 시간·공간 정보 이용을 중심으로, 평균·분산 분석은 이를 뒷받침 |
| **4. Characteristic-Aware EKF** | 확인된 특성에 필요한 최소 모델 구성 | 기존 MB_VAR 조합이 우선 후보. 새 알고리즘이나 추가 상태를 지금 확정하지 않음 |
| **5. Performance Comparison** | 일관된 Heading·XY 개선과 구성요소별 기여 | 8개 성공 조건 + 최소 ablation. 최종 DR·single/≥3-anchor Conventional 비교는 같은 기준의 결과 확보 후 보완 |
| **6. Limitations** | 같은 모델이 이득을 유지하지 못하는 조건과 원인 | 아래 한계 자료를 압축 배치. 실패가 논문의 주인공이 되지 않음 |

최종 비교군에 대한 사용자 지시는 유지한다: **DR, 단일/세 개 이상 앵커 Conventional EKF, 특성 반영 EKF.** 현재 표의 BB_ORIG를 Conventional J4로 이름만 바꾸어 이 비교를 완료하지 않는다. 현재 8개 조건은 성공 모델·데이터를 고르는 근거이며 아직 최종 전체 비교표는 아니다.

추천 본문 도표는 설정·컨셉, 모델 근거, 성공 성능, 최소 ablation으로 압축한다. 실패 사례는 짧은 한계 표/대표 그림으로 추가하며 모든 연구의 history·모델 변형을 담지 않는다.

## F. 한계: 여기서만 실패 조건을 설명한다

> **같은 종류의 관측 보정인데, 왜 어떤 경로·앵커 조건에서는 이득이 유지되고 다른 조건에서는 재귀적으로 무너지는가?**

이 질문은 본문의 성공 모델을 부정하거나 대체하는 주제가 아니라 **적용 범위를 설명하는 후속 한계**로 다룬다.

| 한계 자료 | 포함할 내용 |
|---|---|
| R2-A/R5-A m0 | 같은 모델의 self-gate 적용에서 이득이 유지되지 않는 사례. 위치별 잔차·수용집합·미래 prior가 어떻게 달라지는지 확인하며 단일 원인을 미리 단정하지 않음 |
| R4-B m0 | 같은 Anchor B에서도 Heading·XY 동시 개선이 유지되지 않음. ‘B라서 성공’이라는 단순 일반화를 제한 |
| R5-B 초기화 교차 | 본문 성공 사례도 다른 초기상태에서 큰 오차가 가능. 기존 사후 선택 시드 실험은 원인 진단이며 실패 확률 추정이 아님 |
| 통계적·데이터 범위 | 기존 전체 m0 진단의 self-gate 동시 개선은 **8/24조건**, 본문 성공군은 그중 명시적으로 선정한 **8/8조건**. 단일 scene·seed 0이고 분산표는 B0/m0 개발자료에 기초한 경험적 설정 [S2, S6, S7] |

성공군의 8/8을 전체 24조건 성공률로 표현하지 않는다. 본문은 범위를 명시한 성공을 전달하고, 전체 평가 모집단의 요약 및 제외·실패 사례는 한계/보충 기록으로 남긴다. RMSE 개선과 posterior의 엄밀한 calibration도 구분한다.

R2-A45 및 회수된 R4/R5 m45 원본은 장착각 확장 후보로 보존한다. 이번 본문이 m0에 집중하는 이유는 일관된 모델·데이터 범위를 유지하기 위해서이지 원본 부재 때문이 아니다. 신규 RF 생성이나 타 장면 결과의 혼합은 이번 작업에 포함하지 않는다.

## G. GitHub 근거 및 이번 변경 범위

아래 full SHA는 근거를 읽은 스냅샷이다. 실제 실험 실행 commit/run/input hash는 해당 source·report의 원장을 따른다.

- **[S1] 성공 수치·ablation의 단일 CSV:** [D2_GATE_SCORES.csv](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv). 키: case∈{R2_aB_m0,R5_aB_m0}, bias∈{B0,L0,L1,L2}, gate=self. 비교 arm=BB_ORIG/MB_ORIG/BB_VAR/MB_VAR. 열 이름은 `head_rmse`, `xy_rmse_cm`이다. Blob: `efe55ff9b13b6c6c70f2820e26bacc88ca460d26`.
- **[S2] 모델 계약·시드·σ_b 설정 출처:** [PROTOCOL_PB.md](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/PROTOCOL_PB.md), [exp_pb.py](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py). 이 원실험은 BASE mask 기반이며 self 결과는 S3에서 확인한다.
- **[S3] 실제 self-gate 및 σ_b 조회 시점:** [diag_mbvar.py](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code/diag_mbvar.py). 저장된 기존 μ/R를 재사용한 연구 replay이며 새로운 장면에 대한 end-to-end 배포 검증과 구분한다.
- **[S4] Δs 보정이 실제로 바꾸는 항:** [X1 RESULTS_KO.md §2](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/x1/RESULTS_KO.md). MU_R_EXDS는 CIR+Δs에 의한 전체 Range 평균 교체이며 편파 평균은 유지한다.
- **[S5] 물리 관측·동일 원자료:** [SourceFFD 검증](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md), [BLOCK_C Full/LoS·pose 폴더](https://github.com/myoungsunk/sionna-resimulation/tree/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C).
- **[S6] 거리·잔차·prior·시간구조 진단:** [MB_VAR premodel README와 결과 파일 목록](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/README_KO.md). hand variance와 LORO 재적합의 결과는 다르며 섞지 않는다.
- **[S7] 초기상태·정정된 정보 분석:** [E2/E5 재검증 및 R5-B 교차 실험](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_e2_e5_revalidation_20261029/README_KO.md).
- **[S8] 회수된 Mount45 원본:** [R4/R5 m45 전달 README](https://github.com/myoungsunk/sionna-resimulation/blob/2b41f562063739d8d8f2011bc7248b561359580d/results/DRIVE_SIM_20261007/R4_R5_M45_ORIGINAL_DELIVERY_20261101/README.md).

이번 작업은 **성공 중심 논문 방향의 수정, 기존 성공 조건·모델의 선정, 기존 CSV의 감소율 계산과 ablation 대응**까지다. 원본 RF·기존 결과·구현 코드·계약을 변경하지 않았고 신규 EKF/RT 실행이나 독립 감사를 하지 않았다. 다음 분석은 이 성공을 설명하는 근거를 검증한 뒤 최종 모델 구성으로 연결하는 단계다.
