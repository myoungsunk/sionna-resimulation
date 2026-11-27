# 시간 상관 1차 시험 — range 비백색 처리, 궤적 학습 kernel, N1 거울해 (사전 고정)

| 항목 | 내용 |
|---|---|
| 상태 | DIAGNOSTIC_ONLY, 1차 시험. 필터 실행 전 동결(2026-11-27). 정적 특성화(T1)는 실행 완료 후 모수를 아래에 고정 |
| 블록 | SWB fullco (`sw_block_farst.py`에서 FAR_STATION = False). Paper 1/ABL_N1N6과 같은 블록 |
| 장면 | RT Corridor, 앵커 B, mount 0°. seed 10–29, B0 |

## 1. 정적 특성화 결과 (N1–N6, 참 pose, Full) — 모수 출처

잔차: r_s = s_fp − m_fullco(참 pose), r_r = range − (d3D + B_OLD) − μ_r(U3). `static_tc.py`, `corr_tc.py`, `CORR_ROUTES.csv`, `RANGE_AXIS_LORO.csv`

| 거리 bin | 편파 arc 길이 L (궤적 중앙값, 범위) | 편파 yaw 길이 Y (적합 궤적 수) | range 상관 몫 f | range Δd 길이 ℓ_r |
|---|---|---|---|---|
| < 3 m | 0.104 m (0.080–0.135) | 22.3° (N4 하나) → 규칙상 기본값 10° | 0.282 | 0.025 m |
| 3–6 m | 0.094 m (0.090–0.411) | 12.2° (2) | 0.499 | 0.087 m |
| ≥ 6 m | 0.124 m (0.080–0.194) | 26.8° (3) | 0.002 → 0 | 0.073 m |

- 앞 packet과 range가 같은 비율: 궤적별 0.74–0.84
- range 상관 축 비교(궤적 하나 제외, pair 점수, 낮을수록 좋음): Δt 1.4129, Δarc 1.4168, arc+yaw 1.4191, Δd 1.4254, 상관 없음 1.4278. 모든 축이 null과 거의 같아 이 점수로는 축을 가리지 못함. HT2(Δd 축 우위)는 이 지표로 지지되지 않음
- N1 거울해 진단(N1-K)용 kernel은 N1을 뺀 N2–N6 중앙값으로 따로 계산: L = 0.096 / 0.094 / 0.112 m, Y = 10°(기본) / 12.2° / 27.0°

## 2. arm

### 2-1. Corridor R2/R4/R5 (판정)
range는 S0-id(μ_r, R_rr), 분산 표는 V0_BLOCK_RSS c1a²+c0(ABL F2와 같음), F2 경로(GM + c₀ KI).

| arm | 편파 kernel | range | 질문 |
|---|---|---|---|
| C0 | 1 m / 10° (기본) | 백색 | 기준 |
| C1 | 1절 학습값 (N1–N6 전체) | 백색 | 궤적에서 학습한 kernel이 다른 궤적에 옮겨지는가 |
| C2 | 기본 | 반복 무시: 앞 packet과 range 값이 같으면 range 정보 0 (R_rr = 1e6) | 반복값 중복 계수 제거 효과 |
| C3 | 기본 | range KI: R_rr,eff = (1−f)R + fR + 2Σ√(V_iV_j)exp(−\|Δd̂\|/ℓ_r), d̂는 prior 예측 거리 | 상관 몫 할인 효과 |
| C4 | 학습값 | C3 | 결합 |

### 2-2. N1 거울해 진단 (V1 range, ABL_N1N6 설정)

| arm | 내용 |
|---|---|
| N-B, N-T, N-F2 | ABL_N1N6과 같은 설정 (parity: 거울해 0 / 6 / 2) |
| N-T-near0, N-F2-near0 | 근거리(< 3 m) packet의 상관 몫 V = 0 |
| N-F2-K | N2–N6에서 학습한 kernel |

## 3. 판정

**Corridor (C1–C4 대 C0, B0)**
- 비열등: N_I ≥ N_I(C0) − 1, pooled XY·heading 짝 비율 bootstrap 97.5% 상한 ≤ 1.10, 거울해 seed ≤ C0
- 목표 지표: pooled XY95 ≥ 0.90, Heading95 ≥ 0.95
- 보고: Pose95, NEES3, 궤적별 XY95

**N1 거울해**
- 원인 가설(근거리 할인에 따른 정보 손실) 지지: near0 arm에서 거울해 seed가 같은 계열의 할인 arm(T, F2)보다 줄고, 출발 15 s 동안 y 방향 정보량 Σ H_y²/R_eff가 거울해 seed에서 비거울해 seed보다 작음(중앙값 비교)
- N-F2-K: 거울해 seed 수와 정확도 보고

## 4. 한계

- 1차 시험이라 L2와 확정 seed는 없다.
- Corridor kernel은 N1–N6에서, 판정은 R2/R4/R5에서 한다. N1 진단 kernel은 N1을 뺀 궤적에서 학습한다.
- range 상관 축은 1절의 점수로 결정되지 않았다. C3는 사전 가설(Δd)을 그대로 쓴다.
