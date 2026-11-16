# G1-INT-001/M5 · heading 영역 상한 KI(HF-KI) 단계별 검증 계획

- **상태:** DRAFT · PLAN · 2026-11-16 · DIAGNOSTIC_ONLY
- **브랜치:** `research/g1-sweep-heading-floor-spec-20261113`
- **근거 자료:**
  - Fable 답변 (요청 `FABLE_PROMPT_REDUCE_VS_KEEP_KO.md`, `7b18636`)
  - M1–M4 결과 (`exposure_m1_m4/run_01/REPORT_KO.md`, `390aebc`)
  - 감사 결과 (`audit_c1_c8/`, `audit_m45_donor/`)
- **범위:**
  - mount 0, 앵커 B, B0, Full RF, R2/R4/R5
  - 앵커 A와 L2는 마지막 단계에서 기술 통계로만 다룬다
  - mount 45° 자료는 사용하지 않는다
- **봉인:**
  - G-T2/G-V 봉인과 S2′ STOP, Step 3 HOLD를 유지한다
  - innovation 기반 판별·적응은 이번 계획에서 쓰지 않는다
  - 범위 변경 제안(y/−y 이중 가설)은 Stage 4 분기에서만 사용자 결정으로 넘긴다

## 0. 질문과 가설

**질문.** 편파 heading 정보에 correlation cell 단위 상한을 걸면 R2/R4/R5 모두에서 integrity를 얻는가? 조건은 두 가지다.
- 상한 상수는 σ_θ 하나뿐이다.
- 궤적별 크기 정보와 oracle을 쓰지 않는다.

**H-CAP.** 편파는 한 cell에서 heading을 σ_θ보다 정밀하게 주지 못한다.
- 이 상한을 KI로 구현하면 정보가 많이 쌓이는 구간만 강하게 줄어든다. 해당 구간은 R4와 R2 120–140 s다.
- 정보가 적은 구간은 거의 그대로 남는다. 해당 구간은 R5 접근 구간과 R2의 나머지다.
- 그 결과 세 궤적이 동시에 통과한다.

**구분해야 할 대립 설명.**

| ID | 설명 | 판별 arm |
|---|---|---|
| E-INFO | R5의 M1-D 실패는 명목 편파 정보의 부족 때문이다 | X1 |
| E-THIN | 솎아내기는 packet 하나를 그대로 쓰므로 빠른 성분이 평균되지 않는다. 그래서 heading을 잡지 못한다 (Fable 대안) | X1 |
| E-STOCH | R5의 반전은 앵커 통과 시점의 확률적 분기이고, 해당 arm 고유의 결함이 아니다 | X2, A0 seed |
| E-ALLOC | g²에 비례해 분산을 배분하면 균일 배분보다 손해다 (C3: oracle 크기 + g² 배분 −9 %p) | A2u |

## 1. 공통 정의

모든 arm에서 다음은 E0-LORO-σ_b와 같다.
- SourceFFD 관측식과 Jacobian, μ_B·μ_M, 초기값, Q, controls
- packet별 R_ref (E0-LORO Reff)
- E0 고정 gate mask (R2 971/979, R4 728/742, R5 1384/1415)와 전체 격자 점수

**HF-KI 편파 분산.**

R_eff,ss,i = R_ref,ss,i + V_i + 2 Σ_{j∈H_i} √(V_i V_j) · k_ij

- **V_i:** σ_θ² · g_i². g_i = |H_i[1, 2]|이고, 각 arm 자신의 prior에서 계산한다.
- **k_ij:** exp(−(arc_i − arc_j)/ℓ − (yaw_i − yaw_j)/ℓ_ψ). ℓ = 1.0 m, ℓ_ψ = 10°. arc와 yaw는 기존 `motion_arcs`와 같은 누적량이다.
- **H_i (수용 이력):** 같은 mask의 과거 수용 packet 중 직전 10 s, 최대 100개. C1 KI의 `_kernel_extra`와 같은 제한이다.
- **거리 채널:** 별도 arm(A3)이 아니면 R_ref 그대로 둔다.

**I_cell (진단용).** I_cell,i = Σ_{j∈H_i∪{i}} k_ij · g_j²/R_ref,ss,j

**branch 지표.** M1–M4 사양과 같다.
- **MIRROR_FAIL:** 앵커 x = 10 m 통과 후 2 s 이상 cross-track 부호가 참값과 다르고, |y_참| ≥ 0.2 m인 경우
- **PRE_PASS_OVERCONFIDENT:** 통과 5 s 전 |y 오차|/sd_y > 3인 경우 (경고)

## 2. 단계 구성

| 단계 | 내용 | 재생 | 진입 조건 |
|---|---|---|---|
| Stage 0 | 구현 검사, seed 자료 준비 가능성 확인 | parity만 | — |
| Stage 1 | trace 기반 예측: I_cell, 예상 팽창, σ_θ의 LORO 추정 | 없음 | Stage 0 통과 |
| Stage 2 | seed 10 재생: HF-KI grid와 대조 arm | 있음 | Stage 1 완료 (결과와 무관하게 진행) |
| Stage 3 | seed 5개 재생: 기준선, 대역 중앙값, R5 분기 | 있음 | Stage 2에서 A2 대역 통과 또는 X2 필요 판정 |
| Stage 4 | 판정, 분기, 확장 | 선택적 | Stage 3 완료 |

### Stage 0 · 구현 검사와 준비

1. **HF-KI parity.**
   - σ_θ = 0이면 E0-LORO trace와 ≤ 1e−10으로 일치해야 한다.
   - V_i와 k_ij를 고정 스케줄로 주입하면 C1 KI(`continuation_checks_c1_c8/run_01/C1_R4_KI.npz`)의 R_eff와 trace를 재현해야 한다. 커널 구현이 같은지 확인하는 검사다.
2. **커널 독립 재계산.** causal 합, 회전 항, 10 s / 100 packet 제한을 trace에서 다시 계산해 ≤ 1e−10으로 맞춘다.
3. **정보 차단.** 온라인 경로(g, arc, yaw, V, k)에 참값을 쓰지 않는다. LORO σ_θ 추정(Stage 1)은 donor 참값만 쓰며 평가 궤적의 참값은 쓰지 않는다.
4. **seed 자료 확인.** B0의 seed 11–14 online packet(z, controls)을 만들 수 있는지 확인한다.
   - Full RF H는 같고 센서 잡음과 controls만 달라진다.
   - 만들 수 없으면 Stage 3은 `BLOCKED_SEED_DATA`로 두고 Stage 2 결과만으로 판정 범위를 제한한다.
5. **앵커 통과 목록.** R2 2회, R4 1회, R5 3회로 감사 결과와 일치해야 한다.

### Stage 1 · trace 기반 예측 (재생 없음)

입력은 E0-LORO trace(`attempt_02/d5/B_B0_*.npz`)와 truth 잔차·D3 분해다. 두 가지를 출력한다.

1. **I_cell 분포와 예상 팽창.**
   - ℓ = 1 m, ℓ_ψ = 10° 기준의 I_cell 분포를 궤적별, 구간별(R2 120–140 s, R5 접근 0–44 s 포함)로 낸다.
   - σ_θ grid 각각에서 예상 팽창 배수 1 + I_cell·σ_θ²의 중앙값과 95분위를 낸다.
   - R4 예상 팽창을 C1 KI 실현비(중앙값 20.4)와 비교한다.
2. **σ_θ의 LORO 추정 (보조).**
   - 각 fold의 donor 두 궤적에서 g ≥ 1.0인 D3 지지 시점을 쓴다.
   - |느린 편파 성분 ÷ g|의 중앙값과 4분위 범위를 낸다. 단위는 °다.
   - 이 값은 판정에 쓰지 않는다. Stage 2 통과 대역 안에 드는지만 보고한다.

**판정.** 없음. 모두 기술 통계이며 Stage 2 해석에 쓴다.

### Stage 2 · seed 10 재생

| arm | 내용 | 대상 | 목적 |
|---|---|---|---|
| A1 | M1-I 0.5 m 재현 | R2/R4/R5 | 기존 결과 재현 (parity ≤ 1e−10) |
| **A2(σ_θ)** | HF-KI, σ_θ ∈ {2, 3, 4, 6, 8}° | R2/R4/R5 | 주 arm. 통과 대역 판정 |
| A2u(σ_θ) | 균일 배분 대조: V_i = σ_θ² · g_ref², g_ref = 1.0 (고정 상수) | R2/R4/R5 | E-ALLOC: g² 배분과 균일 배분 비교 |
| A3(σ_θ*) | A2 + 거리 채널 KI | R2/R4/R5 | 거리 편향이 cross-track을 미는 경로 차단 |
| A4(σ_θ*) | A2에서 회전 항 제거 (ℓ_ψ = ∞) | R4 | 회전 탈상관의 역할 |
| X1 | M1-I의 F를 4배 (명목 정보를 M1-D 아래로) | R5 | E-INFO 대 E-THIN 판별 |

- **σ_θ\*:** Stage 2에서 A2를 먼저 실행한 뒤, 통과 대역의 중앙 grid 값으로 정한다. 대역이 없으면 4°로 둔다. A3와 A4는 그 뒤에 실행한다.
- **A3의 거리 KI.**
  - 거리 느린 분산은 해당 fold의 donor 두 궤적에서 거리 bin별 D3 느린 거리 분산의 평균으로 둔다.
  - 상관 길이는 ℓ = 1 m, ℓ_ψ = 10°로 같다.
  - 편파와의 교차 공분산은 두지 않는다.

**궤적별 판정 (각 arm·σ_θ).**
- heading95·XY95·Pose95 각각 ≥ 0.75
- 10 s 블록 하한 각각 ≥ 0.60
- MIRROR_FAIL 0건
- heading·XY RMSE 각각 E0-LORO 대비 +25% 이하

**pooled 판정.**
- heading95·Pose95 ≥ 0.90, 10 s 블록 하한 ≥ 0.80
- NEES3 ∈ [1.5, 6.0]
- 정확도는 두 표기를 모두 낸다.
  - 동결 기준: pooled RMSE +10% 이하면 `ACCURACY_PASS`
  - Fable 제안: +10–25%면 `ACCURACY_MARGINAL`
  - `ACCURACY_MARGINAL`을 진행 기준으로 채택할지는 사용자 결정으로 남긴다

**대역 판정 (A2).** grid 순서에서 서로 인접한 σ_θ 세 값 이상이 궤적별과 pooled 기준을 모두 통과하면 `BAND_PASS`다. 단일 값만 통과하면 `SINGLE_POINT`로 표기하고 판정으로 쓰지 않는다.

**보조 판정.**
- **E-ALLOC:** 같은 σ_θ에서 A2u가 A2보다 R4 heading95가 +5 %p 이상 높으면 g² 배분의 손해를 지지한다.
- **E-INFO/E-THIN:** X1에서 R5 MIRROR_FAIL이 0이면 E-INFO를 기각한다(솎아내기 고유 문제). 1건 이상이면 E-INFO를 지지한다.

### Stage 3 · seed 5개 재생

| arm | 대상 | 목적 |
|---|---|---|
| A0 | E0-LORO, R2/R4/R5 | 기준선의 seed 의존성, R5 반전 여부 |
| A2(σ_θ\*) | R2/R4/R5 | 대역 중앙값의 견고성 |
| X2 | M1-D 0.5 m, R5 | E-STOCH 판별 |

- **seed:** 10–14. RF 실현은 같고 센서 잡음만 바뀐다.
- **판정:**
  - 궤적별 기준은 Stage 2와 같다. MIRROR_FAIL은 모든 seed에서 0이어야 한다.
  - pooled 기준은 seed 5개 중 4개 이상에서 성립해야 한다.
  - E-STOCH: X2에서 반전한 seed가 5개 중 2개 이하면 R5 분기가 확률적이라는 해석을 지지한다. 그 경우 M1-D 기각 근거를 다시 평가한다.
  - A0에서 R5가 seed에 따라 반전하면 기준선 자체가 취약하다고 기록한다.

### Stage 4 · 판정과 분기

| 결과 | 결론과 다음 단계 |
|---|---|
| A2 `BAND_PASS`이고 Stage 3 통과 | HF-KI 채택 후보. 다음 단계는 자체 NIS gate 확인, 앵커 A·L2 기술 통계, Goal 1 정확도 비교(DR/TB3) |
| A2는 integrity만 통과, A3에서 정확도 회복 | 거리 KI를 구조에 포함하고 Stage 3를 A3로 다시 실행 |
| R4 통과 σ_θ 대역과 R2/R5 통과 대역이 겹치지 않음 | 상태 공변량만으로는 세 궤적 동시 해가 없다. 범위 변경 제안(y/−y 이중 가설, innovation 사용)을 사용자 결정으로 넘긴다. 고감도 heading으로 앵커를 두 번 이상 지나는 새 궤적도 함께 제안한다 |
| X1에서 반전 없음 | 솎아내기 계열 폐기, 팽창 계열만 유지 |
| A0에서 seed에 따라 반전 | 거울해를 Goal 1 integrity 구조와 분리해 별도 과제로 다룬다 |
| Stage 0에서 seed 자료 생성 불가 | Stage 2 결과만으로 "seed 10 조건부" 판정. 채택 후보로 올리지 않는다 |

## 3. 산출물

- **단계별 `RUN_CONTRACT.json`.** 다음을 동결한다.
  - 입력과 코드의 SHA-256
  - σ_θ grid, ℓ, ℓ_ψ, KI 제한, g_ref, 거리 KI 분산표
  - bootstrap 설정: 5/10/20 s, 1,500회, seed 20261115
- **Stage 1:** `PREDICT.json` (I_cell 분포, 예상 팽창, σ_θ LORO 추정)
- **Stage 2·3:** arm별 trace NPZ. 추가 필드는 `V`, `k_sum`, `I_cell`, `g`, `s_infl`이다. 그 밖에 `SCORES.json` (궤적별·pooled 점수, 블록 구간, branch 지표, 판정 표기)와 `BAND.json`
- **단계별 `REPORT_KO.md`, 재집계 검증 기록**

## 4. 한계와 주의

- **사후값.** σ_θ grid와 I_cell 해석은 M1–M4 결과를 본 뒤에 세웠다. 그래서 단일 값 통과는 판정에 쓰지 않고 대역 견고성으로만 판정한다.
- **seed의 한계.** seed는 센서 잡음만 바꾼다. RF 실현과 복도는 하나이고, 대역은 이 세 궤적으로만 정해진다.
- **미시험 조건.** 고감도이면서 앵커를 여러 번 통과하는 궤적이 없다. R4형 제약과 R5형 제약이 한 궤적에서 충돌하는 경우는 시험되지 않는다.
- **편파 기여의 대가.** R4에서 약 20배 팽창은 편파의 heading 기여를 그만큼 줄인다. 채택 시 Goal 1 주장에 이 대가를 함께 기록한다.
- **정확도 기준.** `ACCURACY_MARGINAL` 도입은 제안 단계다. 동결 기준(+10%)에 따른 판정도 항상 함께 보고한다.
