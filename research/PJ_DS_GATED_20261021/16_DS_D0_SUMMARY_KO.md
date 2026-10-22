# Δs / d0를 이용한 ranging·heading 개선 시도 종합 (2026-10-22)

공통 조건: 4-state EKF [x, y, ψ, b_g], 관측 z = [r, s], SourceFFD 관측모델, χ²₂(0.99) 결합 gate, 7 case(R2 A M0, R2 A M45, R2 B, R4 A, R4 B, R5 A, R5 B) × bias B0/L2 = Full 14, LoS는 진단용. 학습이 있는 모든 모델은 route-heldout(다른 두 route로 학습). 기준 BASE = POWER_DIAG(POWER1 평균, C_rs = 0). 비율은 대 BASE, 14 case-bias 중앙값, 괄호는 개선 수 / 10% 넘는 악화 수.

정의
- Δs (1종) = s(fp+o) − s(fp), o ∈ {±1, ±2, ±4, ±8}. fp = 강한 포트 첫 tap(최대의 30% 이상), 1 tap = 0.499 ns = 15 cm.
- d0 (2종 Δs의 fp 값) = s_Full(fp) − s_LUT(fp; x̂⁻) = 편파 innovation + μ_s ≈ e_s + 상태 오차 부분(RMS 0.036).
- 2종 모양 = [측정 Δs] − [LUT(x̂⁻) Δs]: heading에 거의 무관(상태 부분 5–7%).

## 1. 접근별 결과

### A. 측정 수준 (필터 없음)
| 접근 | 문서 | 핵심 결과 |
|--|--|--|
| 부호 Δs와 편파 편향 | PJ_STEP1_SIGNED_DS/01 | e_s ≡ 순수 다중경로(h_s(GT) = LoS s, 1.1e-5). 부호 Δs Ridge가 편향 pose R² 0.27–0.46 (POWER1 −0.15–0.09). 부호 일치 +1 tap에서 최고(0.63–0.77) |
| Δs 사용 지도 | PJ_DS_USAGE_MAP/01 | μ_s 비선형(기존+Δs) pose 0.52 / 저주파 0.58, C_rs 부호 AUC 0.64(기존 0.54), μ_r에는 Δs 고유 가치 작음(+0.04), Δs는 ψ와 무관(R² 0.03) |
| ranging만 | PJ_RANGE_DS_CHECK | range 잔차 기존+Δs / 기존 0.89–0.96 (6/7 CI<1), 기존+Δs / POWER1 0.56–0.81 |
| Δs 양상별 개선 | PJ_DS_PATTERN | heading 개선은 |Δs₊₁| 상위 5분위에 집중, ranging은 전 구간 소폭(+0.3 → +1.0 cm) |
| heading 측정 오차 자체 | PJ_METHOD_A_DS_MEAN/heading_meas | robust 재분석에서 HGB 개선이 확실한 case 3/7 (처음 6/7은 과대 주장, 정정함) |
| unresolved 다중경로 | 12 | 편향 e_s²의 80%가 펄스 겹침(fp 이동 0–3 tap)에서 생김. 이 구간 Δs R² 0.38–0.69. 분리 펄스로 fp 이동(≥4 tap, 편향 17%)은 R² 음수. 겹침 지연 ≤3 tap R² 0.49–0.54, ≥4 tap 0.33–0.40 |
| Δs-LUT(2종) | 12 | LUT 모델 = 측정 LoS(3e-8). ∂Δs₊₁/∂ψ = ∂s/∂ψ의 4.4%. 편향 설명 R²: 1종 0.342 → 2종 모양 0.411. heading 오차와 상관 0.045 |
| d0 편파 극심 검출 | 13 | 상위 5% AUC |d0| 0.999 (χ² 편파 항 0.965, |Δs₊₁| 0.908) |
| d0 게이트 (측정) | 13 | 5% 기각 시 필터에 들어가는 편향 질량 0.53, 지속 편향 −28%, 깨끗한 패킷 오기각 0.04% |
| d0를 학습 라벨로 | 13 §5–6 | 정답 없이 μ_s 학습: R² 0.548 (정답 라벨 0.536). prior 오차 >10°이면 라벨 잡음 0.22 |
| d0 → range | 15 이전 | |d0| 상위 10%에서 range 잔차 20–45 cm(POWER σ 16 cm), 평균 +9~+31 cm |

### B. Δs 크기로 분산 조정 (재귀)
| arm | 문서 | heading비 | 거리오차비 | 비고 |
|--|--|--|--|--|
| 2단 / 5단 양방향 (편파+range) | 02 | 1.25–1.38 | – | 패킷 NEES는 맞으나 다수 패킷 하향으로 재귀 과신(NEES 10–11) |
| INFL_S (큰 |Δs| 편파 ↑) | 03 | 1.04 (5/3) | 1.04 | |
| **INFL_R (큰 |Δs| range ↑)** | 03, 04 | **0.994 (8/1)** | **0.975 (11/0)** | radial 0.972, 유일한 무손실 이득 |
| DEFL_S (작은 |Δs| 편파 ↓) | 03, 04 | 1.27 (5/7) | 0.939 (10/0) | heading을 ranging과 맞바꿈 |
| DEFL_R | 03, 04 | 0.98 (10/1) | 1.077 | |
| MIX (INFL_R + DEFL_S) | 06 | 1.167 | 0.884 (14/0) | |
| 경로 분해 | 06 | – | – | 한 채널을 더 믿으면 그 채널의 지속 편향이 그 차원에 쌓임 |
| regime oracle (GT err/σ로 선택) | 07 | 0.964–0.972 | 0.955 | 온라인 지표 없음 (|Spearman| ≤ 0.65) |
| 위치·갱신 단위 switching | 09 | 온라인 1.06–1.10 | – | GT oracle 상한 0.959–0.969 |

### C. Δs로 평균 보정 (재귀)
| arm | 문서 | 측정 오차비 | heading비 | 거리오차비 | 비고 |
|--|--|--|--|--|--|
| 방법 A: Δs 편파 평균 (LIN/HGB) | PJ_METHOD_A | e_s 저주파 R² 0.03 → 0.58 | 1.25–2.06 | – | R4 B·R5 A만 개선 |
| 민감도 분석 | PJ_SENS_STRATA | – | – | – | 개선 여부 = 보정이 heading을 미는 양(Δμ/g)과 기준 heading 오차의 비 (14/14 일치) |
| MU_S_EXDS (편파 평균 HGB) | 11 | s 0.709 | 1.269 (4/9) | 1.014 | |
| MU_R_EX (range 평균, 기존 특징) | 11 | r 0.752 | 1.143 (3/8) | 0.718 (13/0) | |
| **MU_R_EXDS (range 평균, 기존+Δs)** | 11 | r 0.701 | 1.155 (3/9) | **0.639 (11/0)** | radial 0.633, Δs 고유 기여 0.718 → 0.639 |
| INFL_R + MU_R_EXDS | 11 | | 1.165 | **0.580 (12/0)** | |
| G_MU_R (Δs 큰 패킷만 보정) | 11 | r 0.857 | 1.044 | 0.950 | 이득이 전 분위에 퍼져 있어 손실 |
| heading 악화 원인 | 12 | – | – | – | U_S 경로 +17–19%. 원인은 χ²₂ gate accept 변화: range가 보정되면 gate가 편파 오염 패킷을 다시 받아들임(새로 수용 135개, 평균 |e_s| 0.34). 부가로 BASE에서 있던 range–편파 상쇄(−0.098)가 풀림. gate를 끄면 range oracle 보정 0.880 |

### D. d0 (재귀)
| arm | 문서 | heading비 | 거리오차비 | 비고 |
|--|--|--|--|--|
| B_INFL_S / B_GATE3 / B_GATE5 (|d0| 편파) | 14 | 1.046 / 1.007 / 1.022 | 1.05–1.07 | 측정 s95 0.956 → 0.99, NEES 5.2–5.8. 기각된 극심 패킷이 반대 부호 편향을 상쇄하고 있었음 |
| C_INFL_R (|d0| range ↑) | 14 | 1.012 (5/1) | 1.000 (8/0) | INFL_R(Δs)보다 약함 |
| MU_R_EXDS + C_INFL_R | 14 | 1.162 | **0.604** | |
| **MU_R_EXDS + B_GATE5 + C_INFL_R** | 14 | **0.997 (7/6)** | **0.649 (14/0)** | xy 0.935. 단 R2 A M45 2.4배, R2 B 1.6–1.9배 / R5 B 0.77, R2 A M0 0.86–0.93 |
| POWER 재학습: d0 라벨 (BASE 1차 필터) | 15 | 1.013 (6/0) | 0.979 (0) | 정답 라벨 POWER와 같음, NEES 4.04 |
| POWER 재학습: d0 라벨 (J4 1차 필터, GT 없음) | 15 | 1.026 (5/6) | 1.687 (12 악화) | 편파 라벨은 정상, range 라벨에 +3.6 cm 편향 |

### 종합
- ranging: Δs를 range 평균 보정에 쓰면 측정·재귀 모두 크게 개선(거리오차 0.58–0.65, radial 0.63). 분산만 바꾸는 INFL_R은 손실 없는 소폭 개선(0.975).
- heading: Δs/d0로 견고하게 개선한 arm은 아직 없음(최선 INFL_R 0.994). 측정 수준 편파 개선(Δs·d0)은 재귀에서 heading 개선으로 이어지지 않음. 반복되는 원인: 편파 편향을 일부 제거하면 남은 지속 편향의 상쇄가 풀림(평균 보정, 분산 하향, 게이트 모두 같은 구조).
- d0: 편파 극심 검출 0.999, 정답 없는 라벨로 POWER를 같은 품질로 재학습(1차 필터가 정확할 때). 같은 갱신 안에서 d0를 μ_s로 직접 빼는 것은 순환(ν_s = 0).

## 2. 브랜치와 포함 내용
저장소 myoungsunk/sionna-resimulation. 각 브랜치는 앞 브랜치 위에 쌓였고, 최신 `research/powerjoint-ds-gated-plan-20261021`(head 3a3af98, 2026-10-22)이 아래 모든 브랜치를 포함한다(GitHub compare 기준 behind 0). 예외: `research/powerjoint-step2-gm-temporal-20261021`(Gauss-Markov 시간상관 모델, 3 commit)은 분기되어 포함되지 않음. default `main`에는 이 계열이 병합되지 않음.

| 브랜치 (head) | 추가된 디렉터리·문서 | 내용 | 주요 run |
|--|--|--|--|
| powerjoint-d1-temporal (9195c17) | PJ_D1_TEMPORAL | D1 정확 오차 분해, 시간상관(ACT/SHUF 4.6) | – |
| powerjoint-consistency-m123 (d352e73) | PJ_CONSISTENCY_M123 | M1–M3, COMMON η 상향(η = 2–3) | – |
| powerjoint-adaptive-inflation (bc78934) | PJ_ADAPTIVE_INFL | innovation 기반 적응 상향(실패) | – |
| powerjoint-step1-signed-ds (8274d22) | PJ_STEP1_SIGNED_DS/00–01 | 부호 Δs ↔ 편파 편향 | 39542255471 |
| powerjoint-step2-gm-temporal (b7464b7, 미병합) | (GM consider / augment) | 시간상관 직접 모델 | – |
| powerjoint-ds-usage-map (1477e59) | PJ_DS_USAGE_MAP/00–01 | Δs 사용 지도 | 39543861322 |
| powerjoint-method-a-ds-mean (91d7adf) | PJ_METHOD_A_DS_MEAN/00–01, heading_meas/ | Δs 편파 평균(방법 A), heading 측정 오차 robust 재분석 | 39544894508 |
| powerjoint-sensitivity-strata (f5ed359) | PJ_SENS_STRATA/00–01, PJ_RANGE_DS_CHECK, PJ_DS_PATTERN | 민감도 분석, ranging만 확인, Δs 양상 | 39547230273 |
| **powerjoint-ds-gated-plan (3a3af98)** | PJ_DS_GATED_20261021/00–16 | 아래 | 아래 |

PJ_DS_GATED_20261021 (ds-gated-plan) 세부
| 문서 | 내용 | 코드 | 결과 디렉터리 | run |
|--|--|--|--|--|
| 00, 01, 02 | 계획, 간이 테스트(2단·5단 분산) | v_replay.py, v_summary.py | results/ | 39549019861 |
| 03 | 한쪽 방향(INFL/DEFL) | v_replay.py (PJ_ARMSET=oneside) | results_oneside/ | 39550698373 |
| 04 | 같은 arm의 ranging 지표 | v_replay.py | results_ranging/ | 39551585368 |
| 05, 06 | trade-off 경로 분해 | tradeoff_path.py, tradeoff_summary.py | results_tradeoff/ | 39563292062 |
| 07 | regime 지표(사후) | (로컬) | results_tradeoff/REGIME_CASE_TABLE.csv | – |
| 08, 09 | 위치별 분석·switching | series_dump.py, series_collect.py, switch_replay.py, switch_summary.py | results_series/, results_switch/ | 39567982615, 39568946101 |
| 10, 11 | 측정 → 재귀 평균 보정(MU_R/MU_S) | mu_recursive.py, mu_recursive_summary.py | results_murec/ | 39574195919 |
| (CIR 그림) | 극심 패킷 CIR | cir_extract.py | results_cir/ | 39575453259 |
| 12 | unresolved·Δs-LUT·heading 경로·gate 기전 | hpath_lut.py, hpath_summary.py, hpath_analyze.py, hpath_strata2.py, hpath_gate.py, hpath_gate_summary.py | results_hpath/, results_hgate/ | 39582073787, 39586037715 |
| 13 | d0 검출·게이트(측정), d0 라벨 | d0_gate_meas.py | results_d0gate/ | (로컬) |
| 14 | |d0| 편파 분산·게이트, range 분산 (재귀) | d0var_replay.py, d0var_summary.py, d0var_analyze.py, d0_var_calib.json | results_d0var/ | 39706713737 |
| 15 | POWER d0 라벨 재학습 | d0p_labels.py, d0p_fit.py, d0p_replay.py | results_d0power/ | 39705943733 |
| 16 | 이 종합 | – | – | – |
workflow: .github/workflows/powerjoint-ds-gated-{oneside,ranging,tradeoff,series,switch,murec,cir,hpath,hgate,d0var,d0power}.yml (각자 자기 yml 경로 push에만 반응).
