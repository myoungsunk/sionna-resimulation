# 앵커 B — Dual-LP 편파 다중경로와 재귀 EKF 설계 실패 분석

**작성일:** 2026-11-03  
**판정:** 관측오차·공분산 calibration 실패 확인 / EKF 수학 구현 오류 미확인 / 인과 기여율 일부 미확정  
**고정 범위:** R4-B / R5-B, Mount 0°, 4상태 (x, y, ψ, b_g), B0 중심. 비교 대상은 같은 단일 corridor Full/Native-LoS 채널.  
**원칙:** 원본 RF·EKF·보정 코드 및 동결 실험 조건을 수정하지 않고 기존 자료를 재구성하는 진단. 새 필터 승인, 모델 성공, 다른 공간 일반화를 뜻하지 않는다.

## 1. “필터 설계를 실패한 것 아니냐?” — 판정

**그렇다. 적어도 R4-B Full에서 현재 관측모델, 게이트와 공분산의 결합은 실제 측위오차를 충분히 표현하지 못해 통계적 calibration에 실패했다.** 그러나 이 사실을 Joseph covariance/동시 Gaussian update 구현의 수학 오류라고 주장하거나, 모든 경로의 추정이 실패했다고 일반화하면 안 된다.

- R4-B B0 BB_ORIG / POWER_DIAG 계열: Heading RMSE **1.442°**, 명목 Heading 95% 포함률 **20.61%**, XY95 **53.21%**.
- R5-B 동일 비교: Heading **1.073°**, Heading95 **93.60%**, XY95 **66.96%**. R5-B에도 문제가 없다는 뜻은 아니지만 R4-B와 Heading 공분산 일관성이 크게 다르다.
- 수용률은 R4-B **726/742 (97.84%)**, R5-B **1384/1415 (97.81%)**로 유사하다. 정상 NIS 수용률이나 작은 혁신은 상태가 정확하다는 증거가 아니다.
- Gaussian joint/whitened/sequential update와 Joseph covariance의 기존 QA가 통과하였다. 따라서 **현재 실패는 수치 계산보다 물리 관측오차와 필터가 가정하는 분포·독립성·상태 가중치 사이의 불일치**로 보는 것이 타당하다.

원본: [동일 필터 점수](../DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv), [동시·순차 갱신 검산](../PJ_SEPARATE_RS_20261020/01_EXECUTED_RESULTS_KO.md).

## 2. 용어·모집단·arm을 정확히 구분

관측 편파비 s=(P_+−P_−)/(P_++P_−), 고정 TX +45°, RX ±45°, Hann/IFFT 및 30% 첫 도착 검출을 사용한다.

1. **원시 물리적 왜곡**: e_MP = s_Full − s_LoS (정답 pose에서 같은 실제 수신기 체인으로 계산).
2. **평균 보정 후 RF 잔차**: ε_s = s_Full − h_s(q_GT) − μ_s(q). 원시 e_MP와 같은 개념·값이 아니다.
3. **상태오차로 인한 관측 차이**: δh_s = h_s(q_GT) − h_s(qhat_prior).
4. **실제 편파 혁신**: ν_s = ε_s + δh_s (동일 관측·보정 convention).
5. **물리 Jacobian**: g_GT=∂h_s/∂ψ at GT [s/degree]. 실제 EKF는 예측 상태에서 Jacobian H_ψ를 계산 [s/radian]. 이 둘과 K_ψs를 동일시하지 않는다.
6. **시간축**: 필터는 t=0부터 재귀 누적, 정식 RMSE/coverage는 t≥30초. RF 'all finite', C1B 'eligible', gate 'accepted'의 표본집합이 서로 다르다.
7. **Arm**: JOINT4=고정 평균·R, POWER1=첫 경로 전력으로 학습한 평균·joint R, POWER_DIAG=POWER1과 같은 평균·주변 R에 거리–편파 R_rs만 0, BB_ORIG/MB_VAR=기존 원인진단 arm. 결과 섞어 하나의 필터 성적처럼 표시 금지.

## 3. 반사파가 편파비를 왜곡하는 경로 — 물리 H 직접 검증

원래 복도 20×2.4×2.7 m, B=(10,0,2.65) m, 수신기 z=0.45 m. 새로 계산한 R4-B 네 대표 pose의 Full RT (max_depth=3, 실제 FFD 257 bin) 결과는 저장된 원본 Full H에 상대오차 약 3×10^-5, direct H는 Native-LoS에 약 1.5×10^-7로 일치했다.

| R4-B pose (x m) | s_LoS | s_Full | 원시 e_MP | 주요 기여 경로 |
|---|---:|---:|---:|---|
| 194 (6.103) | −0.341626 | −0.257065 | +0.084561 | 천장, +Y 측벽 |
| 234 (6.912) | −0.126962 | −0.125595 | +0.001367 | 천장과 +Y 벽 등 효과 상쇄 |
| 500 (13.095) | −0.059373 | −0.101159 | −0.041786 | 천장 |
| **525 (13.910)** | **+0.262938** | **+0.581863** | **+0.318925** | **−Y 측벽** 다음 천장·바닥 |

**Pose 525**는 약 63:37의 직접파 두 포트 비중이 Full에서 약 79:21로 변했다. 동일 Full first-path tap 비교에서 RX +45° 전력은 직접파 대비 **61.74% 증가**, −45° 전력은 **30.00% 감소**. 경로 간 간섭항을 분담한 결과:
- −Y 측벽 1회 반사: +45° **+51.67%**, −45° **−7.76%**. 그 경로만 제외한 동일 tap counterfactual 편파비 변화는 약 0.185.
- 천장 1회: +45° **+7.08%**, −45° **−14.81%**.
- 바닥 1회: +45° **+2.89%**, −45° **−7.26%**.
- Full first-path tap은 **28**, 단독 LoS는 **27**이다. 복소 간섭과 tap 이동이 공존.
- −Y 벽 반사점 (12.387,−1.200,1.307) m, direct 추가 약 0.391m/1.304ns는 **평면 거울법 추정**이다. PathSolver가 출력한 원시 vertex를 따로 대조한 좌표는 아니다.

**반례 Pose 234**: 천장·측벽의 경로별 제거 효과는 수 % 포트 전력 변화를 보이나 총 Full–LoS 편파비 차이는 +0.0014로 거의 상쇄된다. 반사별 제거 효과는 비선형이라 단순 합산 불가.

물리 결론은 “LoS 총전력이 약해야 편파비가 왜곡된다”가 아니라, **직접파의 포트 간 전력 분배를 경로별 상대 복소 진폭·위상·편파 투영이 바꾼다**는 것이다. 반사점/면의 변화는 경로 추가지연과 각 포트의 복소 채널을 바꾼다.

검증: [Native H 재계산 #41578225906](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41578225906), [경로별 복소 전력 분해 소스](../R4B_RAY_ATTRIB_20261103/compute.py).

## 4. 편파 민감도 vs 편파비 오염: 국소 시점별 실제 EKF

[Pose-level C1/C1B join #41590339308](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41590339308)는 g_GT가 *이미 s/degree*임을 원본 code에서 검증했다.

| case/pose | 시간 | |g_GT| [1/°] | e_MP | POWER_DIAG NIS | 공동 게이트 | 그 직후 Heading 오차 |
|---|---:|---:|---:|---:|---|---:|
| R5-B 401 | 80.2 s | 0.001877 | +0.530837 | 34.85 | 거절 | −2.18° |
| **R5-B 982** | 196.4 s | **0.008687** | **+0.587542** | **7.01** | **수용** | −0.73° |
| **R4-B 168** | 33.6 s | **약 0.0302** | **+0.342** | **7.98** | **수용** | −1.86° |
| R4-B 525 | 105.0 s | 0.041451 | +0.318925 | 73.79 | 거절 | +1.26° |
| R5-B 465 | 93.0 s | 0.032664 | −1.297953 | 298.46 | 거절 | −0.44° |

- **저민감도에서도 편파오차는 클 수 있다.** R5-B 982는 큰 왜곡이 수용됐으나 Head 오류가 갑자기 급증하지 않았다.
- **고민감도에서도 크고 왜곡된 관측이 수용될 수 있다.** R4-B 168 구간은 추후 Heading RMS 증가와 관측 수용·P 감소를 동반했다. 단일 패킷의 독립 인과 기여는 아직 확정되지 않았다.
- **게이트는 큰 오염을 실제로 거절하기도 한다.** R4-B 525·R5-B 401 반례. “민감도가 크면 무조건 거절”도 “큰 편파오차를 EKF가 모두 수용”도 성립하지 않는다.
- POWER1의 **보조** 성분별 갱신에서는 R4-B 168 편파 혁신 약 +0.264 → Heading 갱신 약 −0.328°, R5-B 982 편파 혁신 약 +0.587 → +0.009°였다. **이는 POWER_DIAG의 갱신량으로 인용할 수 없다.**

전체 경로 g 중앙값(/rad)은 R4-B 약 1.705, R5-B 약 0.500. 하지만 R5-B에도 원시 e_MP가 1 이상인 시점이 있다. **민감도는 다중경로를 발생시키는 원인이 아니라 같은 물리 오염이 상태 추정으로 전달되는 경로의 한 요소**이다.

근거: [R2DIAG의 GT derivative](../PJ_D0_CIR_P2_RECURSIVE_20261022/p2_r2diag.py), [per-pose 비교 소스](../R4B_RAY_ATTRIB_20261103/sensitivity_vs_multipath.py), [원본 재귀 trace #39376076166](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166).

## 5. 왜 어떤 경로에서는 왜곡이 필터 실패로 이어지는가?

**같은 앵커 B / B0 / BB_ORIG / s에 대한 D3 원본 분해**:

| 지표 | R4-B | R5-B |
|---|---:|---:|
| E[ε_s²] / E[R_ss] | 0.897 | 0.163 |
| **E[δh_s²] / E[H_s P_prior H_sᵀ]** | **20.956** | 2.144 |
| E[ν_s²] / E[S_ss] | 0.819 | 0.165 |
| 2E[ε_s δh_s] | **−0.002604** | −0.000106 |
| lag-1 RF residual | 0.728 | 0.762 |

기존 R4-B에서는 보정된 RF 오차 ε_s와 상태 오차에 의한 예측차 δh_s의 **음의 교차항**이 편파 혁신을 줄일 수 있다. **상태가 크게 틀렸더라도 ν_s가 작을 수 있다는 점**이 핵심이다. R5-B도 교차항 부호가 음수이나 상대적인 상태오차/사전 P의 괴리가 작다.

**B에서 1.5m 이내의 near 구간**(C1B/C3 그룹, 동일 B0/BB):

| 지표 | R4-B | R5-B |
|---|---:|---:|
| 보정 후 RF 잔차 RMS | 0.01155 | 0.00836 |
| 위치오차 때문에 생긴 편파 예측 차이 RMS | **0.02737** | 0.00505 |
| Heading오차 때문에 생긴 편파 예측 차이 RMS | **0.03620** | 0.00314 |
| 접선 위치오차 RMS | **11.02cm** | 3.91cm |
| 접선 σ 중앙값 | 3.22cm | 4.13cm |
| Heading RMSE | **1.247°** | 0.460° |
| Heading σ 중앙값 | **0.290°** | 0.539° |
| Heading95 포함률 | **36.8%** | 100% |

**의미**: R4-B는 근접 구간 RF 편파 잔차가 작아도, 그 전부터 위치·Heading이 틀려 예측 편파값이 정답 pose에서의 LoS 편파값과 다르다. 그리고 이 오류를 나타낼 P가 작게 보고된다. 다만 R4-B도 근접 통과 후 자연 회복이 *일부* 나타났다. “전혀 리프레시되지 않는다”는 표현은 옳지 않다.

**초기 생성**: 별도 time-aligned 기존 POWER/JOINT4 trace에서 t=0 공동 갱신 전 Heading 초기오차 약 +0.461°, R4-B 편파 raw Full−LoS 약 +0.182, R5-B 약 +0.109로 보고됐고, R4-B는 첫 수용 갱신 직후 POWER_DIAG 약 +3.565°까지 증가했다. R5-B 역시 첫 갱신 후 오차가 생긴다. 이는 *초기 오염 수용이 가능한 원인*이라는 강한 진단이나, 첫 갱신과 이후 전체 failure 간 독립 인과율은 실험으로 분리하지 않았다.

## 6. 왜 보정이 해당 hotspot을 못 맞췄는가?

LoS FFD \(h_s(q)\)에 별도 통계 평균 \(μ_s(q_{\rm RF})\)를 더한다. 기존 POWER1/POWER_DIAG는 ray label·반사면·경로별 H를 **사용하지 않고**, 주로 **log first-path power를 학습 feature**로 사용한다. leave-one-route-out(R4 테스트에는 R2/R5 학습)이고 같은 복도 한 곳에서 실험한 것이다.

| R4-B x | 원시 e_MP | POWER mean μ_s | mean 이후 잔차 |
|---|---:|---:|---:|
| 6.103m | +0.0846 | +0.0265 | +0.0581 |
| 6.912m | +0.0014 | +0.0098 | −0.0084 |
| 13.095m | −0.0418 | +0.0111 | −0.0529 |
| **13.910m** | **+0.3189** | **+0.0258** | **+0.2932** |

전력 기준 평균을 보정해도 벽 반사/천장 반사의 지연·복소 위상·편파 투영 차이를 구별하지 못한다. SEP_DIAG의 delay/threshold/s_diff4 등 특징 확대 모델은 일부 R4-B 개선은 있었지만 **전역 POWER 대체는 기존 검증 NO-GO**였다. 즉 어느 route에서 잘된 통계 보정의 상용화 성공을 주장하면 안 된다.

원본: [학습/재귀 코드](../PJ_SEPARATE_RS_20261020/experiment.py), [검증 결과](../PJ_SEPARATE_RS_20261020/01_EXECUTED_RESULTS_KO.md).

## 7. 게이트와 공분산 실패를 분리

기존 joint gate: ν=z−h(qhat_prior)−μ, S=HP_prior Hᵀ+R, NIS=νᵀS^{-1}ν ≤ χ²₂(.99)=9.2103. 따라서 게이트는 **물리 오염 e_MP 자체**를 검사하는 것이 아니다.
- R4-B pose525: e_MP +0.319, NIS73.79 → joint rejection. 편파뿐 아니라 거리도 같은 packet으로 거절.
- R5-B pose982: e_MP +0.588, NIS7.01 → acceptance. 선형화된 예측값과 더 큰 R, state coupling 등을 고려한 결과이므로 큰 물리오차만으로 게이트 결정 안 됨.
- R4-B pose500: 물리오염 −0.0418이나 잘못된 상태의 POWER1 편파 예측 −0.1007과 실제 Full −0.1012가 거의 일치 → ν_s 약 −0.0005. 이 수치는 **POWER1 보조 비교**이며 R4-B POWER_DIAG의 NIS·Heading을 동일 업데이트로 취급하지 않는다.

Joseph 공분산 P_post=(I−KH)P_prior(I−KH)ᵀ+KRKᵀ는 측정 혁신 ν의 크기를 직접 항으로 쓰지 않는다. 수용된 순간 상태를 거의 움직이지 않아도 오지정된 관측 likelihood를 가정하면 P는 축소될 수 있다. R4-B 근접 구간에서 실제 Heading RMSE 1.247°인데 σ 중앙값 0.290°인 현상이 이에 부합한다.

**모델·경로 상호작용**: R4-B JOINT4 Full Heading 1.323°/coverage40%, POWER1 1.508°/13.2%; 반면 R5-B JOINT4 2.541°/22.1%, POWER1 1.056°/97.2%. “R5 경로가 본래 안전”하다는 일반화도 잘못이다.

## 8. 시간상관·정보 과신은 원인 후보이지 단일 원인이 아님

0.2s 간격 RF 오차 lag-1은 R4-B 0.728 (n742, 추정 유효 117), R5-B 0.762 (n1415, 추정 유효 191). 따라서 관측을 조건부 독립처럼 반복 수용하면 정보가 과대계상될 위험이 있다.

기존 **MB_VAR 별도 개입**에서 R4-B accepted 726 → DEC4 182로 줄일 때 Heading RMSE 1.391→1.006°, Heading95 26.0→85.8%. R5-B는 0.540→0.511°, Heading95 100→100%. 갱신시각과 궤적 자체가 변했으므로 이것을 ‘시간상관의 순수 인과 기여율’이라고 할 수 없고, BB_ORIG 효과와 혼합해서도 안 된다.

## 9. 반드시 유지할 반례·한계

- **저민감도 ≠ 작은 다중경로 오차**: R5-B 982가 반례.
- **고민감도 + 큰 오차 ≠ 필터 무조건 실패**: R4-B 525에서 거절.
- **RF 오염의 발생 ≠ posterior overconfidence의 충분조건**: R5-B에서도 큰 극단 RF 오염이 있지만 POWER 계열의 Heading coverage는 양호.
- **상수 mean 제거 하나로 기여율 단정 금지**: RF 잔여는 위치·시간상관, 상태 예측오차와 결합.
- **LoS 단독이 항상 Full보다 Heading이 낫다는 주장 금지**: 다른 시간 창·arm에서 반례 존재.
- **마운트 0/45 일반 우열 미확정**: 이전 S6와 현 4상태 POWER는 비교 설계가 다르며, 같은 hotspot의 mount-paired native ray attribution은 수행되지 않음.
- **R4-B 4개 선택 pose는 사후 hotspot 진단**이며 R4-B/R5-B 전체 반사면 분포의 대표 표본이 아님.
- 오차원인이 ‘벽 표면’으로 특정됐다는 것은 **선택 pose의 물리적 경로 분해**에 한정. 경로 전체 EKF 차이의 독점적 원인 검증 아님.
- 교차조건 B0/L2와 시간별 RF packet은 통계적으로 독립 환경 반복이 아님.

## 10. 이어서 실행할 인과 검증

조건을 보고 선택해 실행하는 개입은 추가 모델개발용 실험이다. 핵심은 **오차 발생 → 상태 업데이트 → 은폐된 작은 혁신 → 반복수용/게이트 → posterior calibration**의 각 단계 개입이다.

1. **초기 편파 오염**: R4-B/R5-B 최초 0–15초만 Full s→동일 pose LoS s로 치환(원래 range 그대로). 게이트 변경 여부와 이후 prior/P/Heading 차이를 추적한다. 별도 ‘동일 gain/동일 gate one-step’ 대조 필수.
2. **핫스팟 오염**: R4-B 33.6초 고민감도 수용, R5-B 196.4초 저민감도 수용 주변 동일 시간폭의 s만 oracle LoS로 치환. 실제 Heading 누적 인과차와 R/mean 간 상호작용 분리.
3. **공분산만 보수화**: same prior same gain gate (진단) vs 자연재귀 R_s inflation/temporal block decimation. 정확도뿐 아니라 Heading95·XY95·NEES·NIS 및 accepted masks 확인. 사후 최적 m 금지.
4. **공동 게이트 vs 편파-only reject**: 조건부 sequential update로 range-only survivor를 수학적으로 동등하게 구현, 거절 packet의 range 실질 오염도 진단. 단순 scalar 덧갱신으로 중복 정보 생성 금지.
5. **near-anchor refresh**: RF quality 기준 + 다중 pose/heading 수집 + 다중 초기값 short-window 추정. 단일 scalar \((r,s)\) 순간 관측으로 4상태 리셋 불가. 과신된 P를 복원하는 원리와 신뢰구간 검증이 필수.
6. **반사별 물리 반증**: R4-B 525에서 wall_y_neg/ceiling/floor individual complex-ray ablation 뒤 EKF 영향 측정. R5-B 982에 동일 ray-level decomposition 추가. ray ground truth는 오프라인 진단에서만 사용.
7. **mount**: B 같은 pose·yaw에서 0 vs 45 Native Full/LoS 257 bins, ray attribution + Jacobian·Heading 정보량 및 전체 동일 seed 재귀 실험. S6 결과를 직접 이식하지 않음.

사전 계약·성공 기준은 [NEXT_VERIFICATION_CONTRACT_KO.md](NEXT_VERIFICATION_CONTRACT_KO.md)를 참조. 이 문서는 구현·실행 승인이 아니다.

## 11. 검산·근거 인덱스

- [원본 POWER/JOINT/SEP 실험 및 갱신 QA](../PJ_SEPARATE_RS_20261020/01_EXECUTED_RESULTS_KO.md) · [원본 필터 및 통계학습 코드](../PJ_SEPARATE_RS_20261020/experiment.py) · [Actions #39376076166](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166)
- [D3 원시 혁신 분해](../DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D3_DECOMPOSITION.csv) · [D2 게이트](../DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv) · [잔차 시간상관](../DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D3_EPS_TEMPORAL.csv)
- [근접 RF/상태 편파 차이](../DS_MASK_CAUSAL_X1_X2_20261026/pol_azimuth_alloc/C1B_GROUPS.csv) · [near Heading/XY covariance](../DS_MASK_CAUSAL_X1_X2_20261026/pol_azimuth_alloc/C3_GROUPS.csv) · [관측 decimation](../DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D3b_OVERCOUNT_TEST.csv)
- [R4-B 실제 Sionna RT reflection-path 재계산](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41578225906) · [복소 경로별 채널 분해 코드](../R4B_RAY_ATTRIB_20261103/compute.py)
- [R4-B/R5-B 민감도·물리 RF 오염 시점별 검산](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41590339308) · [분석 코드](../R4B_RAY_ATTRIB_20261103/sensitivity_vs_multipath.py)
- [복도 geometry](../../src/qclean_uwb/scenarios/corridor.py) · [관측 first-path 구현](../../src/qclean_uwb/drivesim/observation.py)
- [핵심 사건 표](POSE_HOTSPOTS.csv) · [수치 근거 원장](EVIDENCE_MATRIX.csv)
