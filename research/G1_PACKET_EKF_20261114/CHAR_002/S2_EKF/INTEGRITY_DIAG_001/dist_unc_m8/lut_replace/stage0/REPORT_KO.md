# Stage 0 결과 — LUT 정의역, 교체 인터페이스, 입력·베이스라인 동결

| 항목 | 내용 |
|---|---|
| 계획 | [PLAN_LUT_REPLACE_KO.md](../PLAN_LUT_REPLACE_KO.md) (커밋 `638ebcc2`) |
| 범위 | 계획서 §4의 Stage 0 (0-A–0-D). 확정 seed 50–69는 입력만 만들었고 실행하지 않았다 |
| 상태 | DIAGNOSTIC_ONLY. G-T2/G-V 미접근 |

## 요약

| 항목 | 결과 |
|---|---|
| 0-A LUT 정의역 | **D2 (ψ, el, β)**. 같은 (ψ, el)에서 방위 β만 바뀌어도 s가 σ_res의 1.05–19배만큼 달라진다. 상대 방위형 (ψ − β, el)은 더 나쁘다 |
| C0-1 인터페이스 통과 검사 | **PASS.** 점수·신뢰구간 차이 0, 판정 동일 |
| C0-2 라벨 생성기 | **PASS.** 기존 라벨과 최대 차이 8.4×10⁻⁷ (기준 ≤ 1×10⁻⁵) |
| C0-3 S0-id 재적합·재생 | **판정은 40건 모두 동일.** 그러나 미리 정한 점수 허용치(≤ 1×10⁻³)를 넘었다. 최대 차이는 XY RMSE 1.74×10⁻³ cm, NEES3 1.29×10⁻³ → **FAIL로 기록** (판단 요청, §3) |
| 0-C 입력·동결 | Corridor·Office seed 50–69 입력 각 120개를 생성했다. Office 생성기 parity는 120/120 bit-exact. S0 해시를 기록했다 |

## 1. 0-A LUT 정의역

### 방법

- 동결 FFD 관측 모델로 합성 격자를 계산했다.
  - ρ = 1–9 m, β = 0–350°(10° 간격), ψ는 0.5° 간격으로 둔다.
  - 계산한 값은 s_LoS와 a = ∂s/∂ψ다.
  - 높이는 앵커 2.65 m, 수신 0.45 m로 두 장소가 같으므로 el은 ρ로 정해진다.
- 각 (ρ, ψ)에서 β에 대한 산포 SD_β(s)와 SD_β(a)/mean_β|a|를 구했다.
- 이 값을 배치 영역 pose(Corridor R2/R4/R5, Office O01/O03L)의 (ρ, ψ)에서 보간해 거리 bin별로 집계했다.
- 결정 규칙은 계획서 §4에 미리 고정한 것이다.

### 결과 ([DOMAIN_CHECK.csv](DOMAIN_CHECK.csv), [DOMAIN_GRID.csv](DOMAIN_GRID.csv))

배치 영역에서의 값이다.

| 장소 | 경로 | 거리 | σ_res (S0 표) | RMS_β(s) | 비율 (기준 ≤ 0.3) | SD_β(a)/\|a\| 중앙값 (기준 ≤ 0.2) |
|---|---|---|---|---|---|---|
| Corridor | R2 | < 3 m | 0.011 | 0.083 | 7.5 | 1.13 |
| Corridor | R2 | 3–6 m | 0.048 | 0.150 | 3.1 | 1.23 |
| Corridor | R2 | ≥ 6 m | 0.161 | 0.173 | 1.08 | 1.24 |
| Corridor | R4 | < 3 m | 0.011 | 0.212 | 19.2 | 0.25 |
| Corridor | R4 | 3–6 m | 0.048 | 0.283 | 5.9 | 0.43 |
| Corridor | R4 | ≥ 6 m | 0.161 | 0.288 | 1.79 | 0.50 |
| Corridor | R5 | < 3 m | 0.011 | 0.089 | 8.1 | 1.12 |
| Corridor | R5 | 3–6 m | 0.048 | 0.143 | 3.0 | 1.17 |
| Corridor | R5 | ≥ 6 m | 0.161 | 0.169 | 1.05 | 1.23 |
| Office | O01 | < 3 m | 0.016 | 0.098 | 6.0 | 1.19 |
| Office | O01 | 3–6 m | 0.061 | 0.223 | 3.7 | 0.88 |
| Office | O03L | < 3 m | 0.016 | 0.096 | 5.9 | 1.22 |
| Office | O03L | 3–6 m | 0.061 | 0.196 | 3.2 | 1.24 |

다른 정의역 후보의 결과는 다음과 같다.
- **상대 방위형 (ψ − β, el):** 비율이 3.9–61로 더 나쁘다.
- **ψ + kβ 꼴 (k = ±1, ±2):** 모두 β 산포가 0.61–0.68로, 세계 heading만 쓰는 꼴(k = 0, 0.12–0.27)보다 나쁘다.
- **β마다 ψ 이동량을 따로 최적화한 경우:** 잔차가 0.17–0.32 남는다. 즉 β에 따라 곡선의 **모양**이 바뀐다.

### 판정

**D2 (ψ, el, β)를 채택한다.** 다섯 배치 경로의 모든 거리 bin에서 두 조건이 모두 깨졌다.

### 결과가 갖는 의미

- **앞선 해석의 정정.** 앞선 분석의 "a는 상대 방위가 아니라 세계 heading과 앙각이 정한다"는 비교의 방향으로는 맞다. 세계 heading 꼴이 상대 방위 꼴보다 β 산포가 훨씬 작다. 그러나 β를 빼도 될 정도는 아니다.
  - 앵커의 편파 축이 세계 좌표에 고정되어 있어서, 앵커에서 본 방향(β)에 따라 전파 방향의 횡단면과 투영된 편파가 달라지는 것으로 해석한다.
  - 앵커 바로 아래(ρ = 1 m)에서 β 산포가 가장 작다(0.12).
- **Corridor.** 경로와 sweep이 모두 앵커 양쪽 β ≈ 0°/180° 근처에 있다. 두 쪽의 s 차이가 RMS 0.12–0.24라서, 최소한 앵커 양쪽을 구분하는 LUT가 필요하다. 5줄 sweep의 측방 ±0.45 m가 작은 β 변화를 준다.
- **Office.** 경로가 모든 β를 지난다. LoS station 25곳(1.5 m 간격)으로 (el, β) 평면을 채워야 하므로, 학습 자료가 부족할 위험이 있다. Stage 4의 주요 위험으로 기록한다.
- **계획서 §4 결론 반영.** LUT는 장소별로, 그 장소의 sweep으로 학습한다.

## 2. 0-B 교체 인터페이스와 항등 검사

**구현.** [code/h_ref.py](code/h_ref.py)
- `SwapS`는 동결 관측 모델을 감싸고, 예측과 Jacobian의 편파 행만 `s_fn(states, case) → (s, ∂s/∂(x, y, ψ))`로 바꾼다.
- 거리 행과 나머지는 동결 모델 그대로다.
- `label_es`는 station 자세에서 기준 모델 잔차 라벨 e_s = s_full − h_ref를 만든다.

| 검사 | 내용 | 결과 |
|---|---|---|
| C0-1 | `h_ref = FFD`, S0 보정 그대로. B0 seed 10, 30을 재생해 저장된 S0 GROUP과 비교 (H2, H2S, F2SKRW-V) | 점수·신뢰구간 하한 최대 차이 **0**, I/A/J/거울해 동일 → **PASS** ([C0_1_RESULT.json](C0_1_RESULT.json)) |
| C0-2 | `label_es`(FFD)와 기존 SWEEP_FEATURES e_s(RT LoS 기반) 비교, 7,200 pose | 최대 8.4×10⁻⁷, p99 5.1×10⁻⁷ → **PASS** ([C0_2_LABELS.json](C0_2_LABELS.json)) |
| C0-3 | S0-id: 새 라벨로 rule B 표, POWER (b) μ_s·R_ss, V 표, kriging 자료를 다시 적합한 뒤 seed 10–29 B0·L2 재생 | 아래 |

### C0-3 상세

**보정값 차이** ([S0ID_TABLES.json](S0ID_TABLES.json)):
- μ_s ≤ 2.8×10⁻⁸
- R_rr = 0 (거리 채널은 바뀌지 않음)
- 5줄 표와 V 표의 상대 차이 ≤ 1.6×10⁻⁶

**재생 결과** ([C0_3_COMPARE.csv](C0_3_COMPARE.csv), [C0_3_RESULT.json](C0_3_RESULT.json)):

| arm | 최대 점수 차이 | 최대 CI 하한 차이 | 판정 (H2·H2S 기준 I/A/J, 거울해) |
|---|---|---|---|
| H2 | 0 | 0 | 40/40 동일 |
| H2S | 5.1×10⁻⁵ | 4.5×10⁻⁵ | 40/40 동일 |
| F2SKRW-V | **1.74×10⁻³** | 2.96×10⁻³ | 40/40 동일 |

F2SKRW-V 점수 차이의 지표별 최댓값은 다음과 같다.

| 지표 | 최대 차이 | 위치 | 상대 차이 |
|---|---|---|---|
| XY RMSE | 1.74×10⁻³ cm (17 µm) | L2 seed 29 R2, 7.66 cm | 2.3×10⁻⁴ |
| NEES3 | 1.29×10⁻³ | B0 seed 10 R2, 4.48 | 2.9×10⁻⁴ |
| XY95 | 7.1×10⁻⁴ | 한 packet이 경계를 넘나든 차이 | — |
| heading RMSE | 1.6×10⁻⁴° | — | — |
| Pose95, Heading95 | 0 | — | — |

## 3. 판단 요청: C0-3 허용치

- 미리 정한 기준(점수 차이 ≤ 1×10⁻³, 단위 구분 없음)으로는 **FAIL**이다. 사후에 기준을 바꾸지 않고 그대로 기록한다.
- 원인은 RT LoS와 FFD 합성 LoS의 차이(라벨 ≤ 8.4×10⁻⁷)가 kriging과 EKF를 거치며 커진 것이다. 판정은 40건 모두 같고, 상대 차이는 3×10⁻⁴ 이하다.
- **선택지.**
  - (가) "판정 동일 + 상대 차이 ≤ 1×10⁻³"으로 허용치를 다시 정의하는 개정을 하고 C0-3을 통과로 본다.
  - (나) 기준을 유지하고, Stage 1 이후의 S0 비교 기준을 저장된 S0(RT LoS 라벨)가 아니라 S0-id(FFD 기준 라벨)로 바꾼다. 이렇게 하면 이후 단계의 비교가 모두 같은 라벨 정의 위에서 이루어진다.
- **제안.** (나)를 권한다. 실측형 파이프라인과 같은 라벨 정의를 쓰는 S0-id가 이후 단계의 공정한 기준이다. S0-id의 확정 seed 50–69 결과는 Stage 1 확정 실행 때 함께 만든다.

## 4. 0-C 입력과 베이스라인 동결

| 항목 | 결과 |
|---|---|
| Corridor seed 50–69 | `gen_inputs_ext.py generate 50 69` → 120개. 인덱스: [INPUT_INDEX_EXT_50_69.json](INPUT_INDEX_EXT_50_69.json). 생성 법칙의 parity는 이전 검사(PASS_TOL_1e-10)를 따른다 |
| Office 생성기 parity | seed 10–29 재생성이 기존 입력과 **120/120 bit-exact** ([OFFICE_INPUT_PARITY_10_29.json](OFFICE_INPUT_PARITY_10_29.json)) |
| Office seed 50–69 | 120개 ([OFFICE_INPUT_INDEX_50_69.json](OFFICE_INPUT_INDEX_50_69.json)) |
| S0 동결 | Corridor F2SKRW-V와 Office F2T1V의 코드·보정·표·입력 인덱스 해시 ([BASELINE_FREEZE.json](BASELINE_FREEZE.json)). Corridor 해시는 Step 3 개정 01의 동결값과 일치한다 |
| 확정 seed 결과 | 실행하지 않았다 |

## 5. Stage 1 실행 전 개정이 필요한 항목

| # | 항목 | 제안 |
|---|---|---|
| A1 | C0-3 허용치와 S0 비교 기준 | 위 §3의 (나) |
| A2 | LUT 형태 (D2 반영) | ψ에 대한 K차 Fourier, 계수는 (el, β)의 함수. Corridor는 앵커 양쪽(β ≈ 0°, 180°)을 구분하고 el 방향 B-spline + 측방 β 1차 항. Office는 (el, 주기적 β)의 텐서 B-spline. K와 매듭 수는 공간 블록 교차검증으로 고른다 |
| A3 | 감도 부호 일치율 관문 | 거리 bin마다 \|a_FFD\| ≥ 0.3인 pose에서 sign(a_emp) = sign(a_FFD) 비율 ≥ 0.95. 0.3은 rule B의 저감도 경계와 같다 |

## 6. 파일

| 파일 | 내용 |
|---|---|
| [code/domain_check.py](code/domain_check.py) | 0-A. 합성 격자는 이 스크립트로 약 2.5분이면 다시 만들 수 있다 |
| [code/h_ref.py](code/h_ref.py) | 교체 인터페이스와 라벨 생성기 |
| [code/s0id_refit.py](code/s0id_refit.py), [code/run_c0.py](code/run_c0.py), [code/cmp_c03.py](code/cmp_c03.py) | C0-1과 C0-3 |
| [code/gen_office_inputs.py](code/gen_office_inputs.py), [code/gen_inputs_ext.py](code/gen_inputs_ext.py) | 입력 생성 |
| [groups_c0.tar.gz](groups_c0.tar.gz) | C0-1, C0-3 GROUP 42개 |
| [SHA256SUMS](SHA256SUMS) | 해시 |
