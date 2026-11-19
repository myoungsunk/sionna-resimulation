# 편파 관측 LUT 대체와 기준 모델 잔차 — 단계별 검증 계획 (Stage 0부터)

| 항목 | 내용 |
|---|---|
| 목적 | 시뮬레이션에서만 가능했던 현재 필터를 **실측 환경으로 옮길 수 있는지** 단계별로 확인한다 |
| 실측에서 막히는 두 가지 | (1) 3D 실측 안테나 패턴이 없어 FFD 기반 관측 LUT를 만들 수 없다. (2) 실측에는 LoS 채널이 없어 보정 라벨 Full − LoS를 만들 수 없다 |
| 개입 I | **LUT 대체.** 관측 함수 h_s와 감도 a를 station sweep의 Full 관측만으로 학습한 경험적 LUT(EMP)로 바꾼다 |
| 개입 II | **기준 모델 잔차.** 보정 라벨을 e_s = s_full − s_LoS 대신 e_s = s_full − h_ref로 정의한다. h_ref는 EKF가 쓰는 관측 함수와 같다 |
| 진행 원칙 | I과 II를 따로 검증하고, 둘 다 유효하면 결합 모델로 확정한다 |
| 베이스라인 S0 | Corridor: F2SKRW-V ([Step 3 보고서](../step3_fair/REPORT_KO.md)). Office: F2T1V ([Office 전이 보고서](../office_transfer/REPORT_KO.md)) |
| 상태 | DIAGNOSTIC_ONLY. G-T2/G-V 미접근. S2′ STOP, Step 3 HOLD 유지 |

## 1. 사용자 결정 (2026-11-19)

| 항목 | 결정 |
|---|---|
| Stage 2 모델 오차 | 임의로 넣는다. 5° 수준의 heading 방향 이동 등 |
| LUT 정의역 | Stage 0 결과를 본 뒤 정한다 |
| kriging | 유지한다 (S0와 같은 구조) |
| seed | 개발 10–29, 확정 **50–69 (새 seed)**. S0도 50–69로 다시 돌린다 |

## 2. 현재 구조에서 FFD가 쓰이는 곳

| 쓰이는 곳 | 역할 | 개입 |
|---|---|---|
| ⓐ EKF의 h_s(x, y, ψ)와 위치·heading Jacobian | 관측 예측 | I |
| ⓑ 감도 a = ∂h_s/∂ψ | 분산 a²c₁ 항, F2 GM 상태의 적재 a·√c₁ | I |
| ⓒ 보정 라벨 e_s | μ_s(POWER), kriging, rule B의 c₁·c₀, V 표 적합 | II |

- **고정하는 것.** 거리 채널(sweep μ_r HGB (b), R_rr), F2 구조(핵 1 m/10°, 이력 10 s/100 packet, KI), (b) heading 가중, 판정 채점기는 모든 단계에서 S0와 같다.
- **거리 채널은 이미 실측과 호환된다.** 거리 라벨 e_r = range − (d₃D + B_OLD)는 station 위치만 있으면 만들 수 있다.
- **시뮬레이션의 항등 관계.** RT LoS와 FFD 합성 LoS는 같다(parity 6.5e−7). 따라서 FFD를 기준 모델로 두고 II를 적용하면 S0와 거의 같다. 이 조합은 항등 검사로만 쓴다. II의 실제 효용은 기준 모델이 틀릴 때 잔차 보정이 그 오차를 흡수하는지이므로, Stage 2는 일부러 틀린 FFD′로 시험한다.

## 3. 설계 (2요인)

| EKF 관측 함수 \ 보정 라벨 | Full − LoS (참값, 현재) | Full − h_ref (실측형) |
|---|---|---|
| FFD | **S0** | S0-id (항등 검사) |
| FFD′ (일부러 틀린 FFD) | **2a** | **2b** |
| EMP (sweep Full로 학습한 LUT) | **1** | **3** (최종 후보) |

| 효과 | 비교 |
|---|---|
| LUT 대체 (I) | 1 대 S0 |
| 기준 모델 잔차 (II) | 2b 대 2a (회복 정도), 2b 대 S0 (비열등) |
| 결합 | 3 대 S0, 3 대 1, 3 대 2b |
| 공간 전이 | Stage 4 (Office) |

## 4. Stage 0 — 사전 확인 (이번 실행 범위)

### 0-A. LUT 정의역 결정

**질문.** 관측 함수를 h(ψ, el)로 충분히 쓸 수 있는가, 아니면 앵커에서 본 방위 β가 필요한가.

- 앞선 분석에서는 s와 a가 상대 방위보다 세계 heading ψ와 앙각 el로 잘 설명됐다.
- 하지만 Corridor sweep은 앵커에서 본 방위가 거의 ±x 두 방향이다. Office 경로는 모든 방위를 지난다.

**자료.** 동결 FFD 관측 모델(Corridor anchor (10, 0, 2.65), Office anchor (5, 2.2, 2.65), 수신 높이 0.45 m)로 계산한 s_LoS(ψ; x, y)와 a(ψ; x, y)다. 평가 위치 세 묶음은 다음과 같다.

| 묶음 | 내용 |
|---|---|
| G1 | Corridor 5줄 sweep 200 station |
| G2 | Office 35 station |
| G3 | 합성 격자: ρ = 1, 2, …, 9 m × β = 0°, 10°, …, 350° |

ψ는 0.5° 간격으로 둔다.

**후보 정의역.**

| 기호 | 정의역 |
|---|---|
| D1 | (ψ, el) |
| D2 | (ψ, el, β) |
| D3 | (ψ − β, el), 상대 방위 대조용 |

높이가 고정이므로 el ↔ ρ는 일대일이다. D1은 이 설치 조건에서 (ψ, ρ)와 같다.

**지표.** 각 앙각 구간(ρ 기준 0.5 m 폭)과 ψ에서, β에 대한 산포를 본다.
- RMS_β(s) = β에 대한 s_LoS의 표준편차
- RMS_β(a)/|a|의 중앙값
- D3에 대해서도 같은 지표

**결정 규칙 (사전 고정).**
- **D1 채택:** 배치 영역(Corridor R2/R4/R5 경로 pose, Office O01/O03L 경로 pose)에서, 모든 거리 bin의 RMS_β(s) ≤ 0.3 × σ_res(ρ)(S0 표 값)이고 RMS_β(a)/|a| ≤ 0.2이면 D1을 쓴다.
- **D2 채택:** 위 조건이 하나라도 깨지면 D2를 쓴다.
- **D2일 때의 결과:** Corridor sweep만으로는 β 범위를 학습할 수 없다. 그러면 LUT는 장소별(그 장소의 sweep)로 학습한다는 결론을 함께 기록한다.

### 0-B. 관측 함수 교체 인터페이스와 항등 검사

**구현.** 관측 함수 교체 인터페이스 `h_ref`를 만든다. 입력은 (x, y, ψ, 앵커 사양)이고 출력은 (h_s, ∂h_s/∂x, ∂h_s/∂y, ∂h_s/∂ψ)다. 거리 채널은 기존 모델 그대로 둔다.

| 검사 | 기준 |
|---|---|
| C0-1 | `h_ref = FFD`로 S0를 재생하면 seed 10, 30 (B0)의 GROUP 점수와 판정이 S0와 **비트 단위로 같다** |
| C0-2 | 라벨 생성기 `e_s = s_full − h_ref(x_st, y_st, ψ)`에 FFD를 넣으면, 기존 SWEEP_FEATURES의 e_s와 최대 차이가 1e−5 이하다 (RT LoS 대 FFD parity 범위) |
| C0-3 | S0-id(FFD + Full − h_FFD 라벨로 μ_s, kriging, c₁, c₀, V를 다시 적합) 재생 결과가 seed 10–29에서 S0와 판정이 같고, 점수 차이는 1e−3 이하다 |

### 0-C. 입력과 베이스라인 동결

| 항목 | 내용 |
|---|---|
| Corridor 확정 seed 50–69 입력 | `gen_inputs_ext.py`(M7과 같은 법칙, parity PASS_TOL_1e-10)로 만든다. 경로와 sha256을 index로 남긴다 |
| Office seed 50–69 입력 | `o3_build.py`의 `inputs()`와 같은 법칙으로 만든다 |
| 베이스라인 동결 | S0(F2SKRW-V, F2T1V)의 코드·보정 배열·표 해시를 기록한다 |
| seed 50–69 결과 | Stage 1–4 확정 실행 때 S0와 함께 돌린다. Stage 0에서는 보지 않는다 |

### 0-D. Stage 0 산출물

- `stage0/REPORT_KO.md`: 정의역 결정과 근거 표, C0-1–C0-3 결과
- `stage0/DOMAIN_CHECK.csv`, `stage0/code/`, `stage0/SHA256SUMS`
- **개정 기록:** 정의역 결정과 Stage 1 정적 관문의 수치 기준(감도 부호 일치율)을 Stage 1 실행 전에 이 계획에 덧붙인다.

## 5. Stage 1 — LUT 대체 (I 단독)

**EMP LUT 학습.**
- **자료:** Corridor 5줄 sweep 200 station × 36 yaw의 s_full과 station 자세(x, y, ψ)만 쓴다. RT LoS와 FFD는 보지 않는다.
- **형태:** ψ에 대한 K차 Fourier 급수다. 계수는 Stage 0에서 정한 정의역 변수(el, 필요하면 β)에 대한 3차 B-spline으로 둔다.
- **추정:** Huber 손실로 강건 적합한다. 감도 a_emp와 위치 Jacobian은 해석적으로 미분해 얻는다.
- **K와 매듭 수:** 공간 블록 교차검증으로 고른다. 이웃 station을 묶어 x 방향 10 블록, 5줄 전체를 한 블록 단위로 뺀다.

**정적 평가 (같은 공간 블록 교차검증).**
- 미사용 station에서 s_full 예측 RMSE를 EMP와 FFD로 비교한다.
- a_emp와 a_FFD의 부호 일치율과 상관을 거리 bin별로 본다.
- h_emp − s_LoS를 본다. 평균 다중경로가 LUT로 흡수된 정도이고, 시뮬레이션에서만 볼 수 있는 진단이다.

**필터 arm.** 보정 라벨은 참값(S0의 μ_s, kriging, 표 그대로)이다.

| arm | 바뀌는 것 |
|---|---|
| S1-h | ⓐ만 EMP |
| S1-a | ⓑ만 EMP |
| **S1** | ⓐ와 ⓑ 모두 EMP |

## 6. Stage 2 — 기준 모델 잔차 (II 단독)

**FFD′ (일부러 넣는 모델 오차).**

| 기호 | 오차 | 정의 |
|---|---|---|
| **P1 (주)** | heading 방향 이동 +5° | h′(x, y, ψ) = h_FFD(x, y, ψ + 5°), a′도 같은 이동 |
| P1− | −5° 이동 | 부호 민감도 확인 |
| P2 | 포트 이득 불균형 +1 dB | s′ = (g·P₊ − P₋)/(g·P₊ + P₋), g = 10^0.1 |
| P3 | P1 + P2 | 결합 |

**arm (P마다).**

| arm | EKF | 보정 라벨 |
|---|---|---|
| 2a | FFD′ | 참값 (S0 보정 그대로) |
| **2b** | FFD′ | s_full − h′. μ_s(POWER), kriging 자료, c₁·c₀(rule B, a′ 사용), V 표를 다시 적합. kriging 초모수는 S0 값으로 고정 |
| 2b-cv | FFD′ | 2b와 같되 kriging 초모수를 같은 교차검증 절차로 다시 고른다 (민감도) |

**주의.** P1은 실측의 장착 yaw 오차와 같다. 보정이 이 오차를 흡수하지 못하면 heading에 일정한 편향이 남는다. 이 편향을 heading 평균 오차로 따로 보고한다.

## 7. Stage 3 — 결합 (I + II)

- **arm 3:** EKF는 EMP를 쓰고, 보정 라벨은 s_full − h_emp다. μ_s, kriging(초모수 재선정), c₁·c₀(a_emp 사용), V 표를 모두 다시 적합한다.
- **강건성 (실측 문제를 시뮬레이션으로 주입).**
  - **R1: station heading 영점 오차.** station마다 상수 오프셋 ~N(0, σ²), σ = 1°, 2°를 sweep 학습용 yaw에만 더한다. EKF의 참값은 바꾸지 않는다.
  - **R2: 식별성 진단.** 거리 bin별로 δ_p(heading 등가 오프셋)의 평균을 본다. 평균이 0이 아니면 h_emp에 흡수되는데, 그 크기를 EMP와 FFD의 위상 차이로 보고한다.

## 8. Stage 4 — 공간 전이 (Office)

- **보정:** Office LoS 25 station × 36 yaw만으로 Stage 3 절차를 그대로 다시 실행한다. EMP 학습, 라벨, 보정을 모두 다시 만든다.
- **평가:** O01과 O03L로 판정한다. O02(관측성 한계)는 따로 보고한다.
- **비교:** F2T1V(S0-Office)와 Office LORO H2.
- **한계:** Office는 앵커·수신 높이가 Corridor와 같다. 그래서 앙각과 거리의 결합 문제는 이 전이에서 시험되지 않는다.

## 9. 판정 규칙 (모든 단계 공통, 사전 고정)

**실행 순서.**
- 개발 seed 10–29로 설계를 마친다.
- 확정 seed 50–69에서는 후보 arm과 S0를 같은 입력으로 한 번만 실행한다.
- 확정 실행 뒤에는 설정을 바꾸지 않는다.

**정적 관문 (필터 실행 전).**
- 미사용 station(공간 블록)에서 |z_s| ≤ 1.96 포함률이 거리 bin마다 0.90 이상
- 감도 부호 일치율: 기준은 Stage 0 뒤 개정으로 고정

**필터 비열등 (S0 대비, B0와 L2 각각).**
- N_I ≥ N_I(S0) − 1
- pooled XY RMSE와 heading RMSE의 seed별 비율(후보/S0) 중앙값에 대한 bootstrap 97.5% 상한 ≤ 1.10. bootstrap은 10,000회, seed 20261119
- 거울해 경로 수(Corridor)와 gross 실패 수(Office)가 S0보다 많지 않을 것

**함께 보고하는 것.**
- N_J(H2S 기준), M7 규칙(H2 기준)
- 궤적별 seed 20개 합산 RMSE와 포함률의 H2 대비 변화

**진행 규칙.**
- S1과 2b(P1)가 모두 비열등이면 Stage 3으로 간다.
- 하나가 실패하면 원인을 먼저 나눈다.
  - Stage 1: S1-h 대 S1-a
  - Stage 2: P1·P2·P3 크기별 비교
- 원인을 나눈 뒤 진행 여부를 사용자와 정한다.
- **모델 확정 조건:** Stage 3이 비열등이고, Stage 4가 F2T1V 대비 비열등일 때 결합 모델로 확정한다.

## 10. 시뮬레이션에서 시험하지 않는 항목 (실측 단계로 넘김)

- **수신 백색잡음 R_white.** 정지 상태 반복 측정으로 공간 오차와 분리한다. 시뮬레이션에는 수신 잡음이 없다.
- **앙각과 거리의 분리.** 일부 station에서 태그나 앵커 높이를 바꾸는 보조 측정이 필요하다.
- **heading 기준.** 실측 교정 중의 절대 heading 기준을 확보한다. Stage 3 R1은 그 허용 오차를 정하는 근거로 쓴다.

## 11. 산출물 위치

`dist_unc_m8/lut_replace/` 아래 `stage0/` … `stage4/`. 단계마다 다음을 남긴다.
- 보고서, 코드, 표(CSV), GROUP 묶음, SHA256SUMS
- 확정 실행 전 개정 기록

## 개정 01 — Stage 0 결과 반영, Stage 1 실행 전 (2026-11-19, 사용자 확인)

Stage 0 결과: [stage0/REPORT_KO.md](stage0/REPORT_KO.md) (커밋 `fdbd223d`).

| # | 항목 | 개정 내용 |
|---|---|---|
| A1 | 비교 기준 | C0-3은 기준(점수 차이 ≤ 1e−3)을 바꾸지 않고 FAIL로 둔다. 판정은 40/40 같고 최대 차이는 XY RMSE 1.74e−3 cm다. **Stage 1 이후의 비교 기준을 S0-id로 바꾼다.** S0-id는 F2SKRW-V 구조를 그대로 두고 라벨만 e_s = s_full − h_FFD로 다시 적합한 것이다. 확정 seed 50–69에서 S0-id를 후보와 같은 입력으로 함께 실행한다 |
| A2 | LUT 형태 | 정의역은 **(ψ, el, β)** (Stage 0-A). h_emp(ψ, el, β) = Σ_q Σ_j Σ_m θ_qjm f_q(ψ) B_j(el) g_m(β)이다. f_q는 ψ에 대한 K차 Fourier 기저(2K+1개), B_j는 el에 대한 3차 B-spline(기저 J개)이다. g_m은 β의 주기 조화 기저로, Corridor는 {1, cos β, sin β}이다. cos β가 앵커 양쪽(β ≈ 0°/180°)을 가르고, sin β가 측방 1차 항이 된다. 이렇게 두면 앵커 바로 아래에서도 연속이다. Office(Stage 4)는 2차 조화까지 쓴다. K ∈ {2, 4, 6, 8}과 J ∈ {4, 6, 8}은 x 방향 10개 공간 블록(5줄을 함께 뺌) 교차검증의 미사용 s_full RMSE로 고른다. 적합은 Huber IRLS다. a_emp와 위치 Jacobian은 해석적으로 미분해 얻는다. el은 학습 범위 밖에서 경계값으로 고정하고, 그 비율을 보고한다 |
| A3 | 감도 부호 관문 | 거리 bin마다, \|a_FFD\| ≥ 0.3인 미사용 블록 pose에서 sign(a_emp) = sign(a_FFD) 비율 ≥ 0.95 |
| A4 | Stage 1 구현 | 감도 a는 F2 상관 상태의 적재(a·√c₁)와 Jacobian에 쓰인다. S1-h와 S1-a를 분리하려고, 동결 `m8_replay.replay_m8`을 복사해 a를 따로 넣는 훅 `a_fn`만 더한다. `a_fn`이 없으면 원본과 비트 단위로 같아야 하며, 실행 전에 검사한다. S1 계열의 정확도 기준 arm(H2, H2S)은 FFD 관측 모델 그대로 함께 재생한다 |
| A5 | Stage 1 정적 관문의 z_s | 미사용 블록 station에서 z_s = (s_full − h − μ_s)/√(c₁a² + c₀)를 계산한다. μ_s는 ρ < 6 m에서 미사용 블록을 뺀 kriging(S0-id 라벨, S0 초모수), 그 밖에서는 미사용 블록을 뺀 POWER(균일 가중)다. c₁, c₀는 S0-id V 표를 쓴다. S0-id(h = FFD)에도 같은 값을 계산해 함께 보고한다 |
