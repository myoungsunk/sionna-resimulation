# G1-CHAR-001 실내 다중경로 오차 특성화 사양 (2026-11-15)

상태: DIAGNOSTIC_ONLY. S2′ STOP(FULL_6), Step 3 보류, G-T2/G-V 봉인을 그대로 유지한다.

## 0. 목적

Goal 1은 편파(dual-LP s) 정보를 heading/편파 자체에 대한 다중경로 완화 없이 사용하면서, 먼저 integrity(NEES, 95% coverage)를 확보하는 것이다.

지금까지 MODEL-003 v2/v3, D7/D7.1, +K는 모두 어떤 오차 표현(가우시안+분산, colored, consider, Student-t)을 먼저 정하고 시험했다. 이 사양은 순서를 바꾼다. 실내 데이터에서 다중경로 오차가 실제로 어떤 모양이며 무엇에 따라 달라지는지 먼저 전부 조사한다. 표현의 선택은 그 결과를 본 뒤 §6 결정표로 Fable과 논의한다.

이 사양은 모형을 고르거나 integrity를 판정하지 않는다. 어떤 수치도 확인(confirmation) 모수로 옮기지 않는다.

## 1. 데이터

| 묶음 | 케이스 | 용도 | 비고 |
|---|---|---|---|
| 새 RT G-T1 | G-T1_A(앵커 x=7.0), G-T1_B(9.8), G-T1_C(3.0), mount 0 | 특성화 본체 | 6242fb9 생산, MANIFEST SHA 일치 확인 |
| BLOCK_C (기존 RT) | R2_aA_m0, R2_aA_m45, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0 | RT 간 비교, mount 비교 | CASES.json SHA 일치 확인 |

G-T2와 G-V는 읽거나 스테이징하지 않는다. BLOCK_C의 기존 EKF 결과(results_*.csv)는 mount 비교의 보조 근거로만 쓴다.

## 2. 오차 정의 (MODEL-003 관측 체인과 동일)

체인은 Hann/4× IFFT, 가장 강한 Rx 가지의 30% 선행 에지(O30), Tx port 0, s=(P0−P1)/(P0+P1)이다. 잡음은 넣지 않는다. 열잡음 분산은 이미 알려져 있으므로 별도로 다루지 않는다.

| 기호 | 정의 | 의미 |
|---|---|---|
| e_s | s_full(full O30 tap) − s_LoS(LoS O30 tap) | MODEL-003의 e_mp. 필터가 실제로 받는 편파 오차 |
| e_s^same | s_full(LoS O30 tap) − s_LoS(LoS O30 tap) | 같은 tap에서의 오염. tap 이동 효과를 분리 |
| e_s^shift | e_s − e_s^same | tap 이동이 만든 부분 |
| Δtap | idx_full − idx_LoS | 선행 에지 이동 |
| e_r | r_full − r_LoS | 다중경로 거리 오차(offset 무관) |
| e_r^abs | r_full − offset − d, offset=−0.5316 m (MODEL-003 S1 PARITY) | 필터가 받는 절대 거리 오차 |
| g_ψ | ∂s_LoS/∂ψ, 동결 FFD bank로 ±0.5° 중앙차분 | s의 heading 민감도 |
| e_ψ^eq | e_s / g_ψ | 등가 heading 오차. |g_ψ|가 작은 곳은 별도 표시 |

g_ψ는 hs_lut.los_h(동결 소스, SHA 고정)에 antenna yaw = body yaw + mount를 넣어 계산한다. RT LoS와 los_h의 s 차이(parity)를 케이스마다 보고한다.

## 3. 독립 단위와 thinning

오차는 공간과 yaw에 강하게 상관되어 있다. 따라서 분포를 적합할 때 모든 표본을 독립으로 쓰지 않는다.

- 새 RT: 경로 표본은 along 거리 0.25 m 간격으로, sweep 표본은 station당 yaw 20° 간격으로 솎는다. 사전에 측정한 상관 길이(5–24 cm, 16–20°)보다 크다.
- BLOCK_C: 연속 주행이므로 누적 이동거리 0.25 m 또는 누적 회전 20° 중 먼저 오는 쪽마다 1개를 남긴다.
- 솎기 결과가 바뀌는지 보기 위해 0.5 m / 40°에서도 반복한다.

## 4. 조사 항목

### C1. 주변분포 모양

케이스별, 그리고 묶음별 pooled로 e_s, e_r, e_ψ^eq에 대해 다음을 계산한다.

1. 원값과, 거리 구간(1 m) robust scale(1.4826·MAD)로 나눈 z를 모두 본다.
2. 후보 모형: Gaussian, Laplace, Student-t(ν 자유), Gaussian mixture K=1..4. 솎은 표본으로 최대우도 적합하고 BIC를 보고한다.
3. 꼬리 지표: P(|z|>2), P(|z|>3), q95/q68, q99/q95 비율과 Gaussian 기준값(2.0/1.0 기준 1.96, 1.31) 비교.
4. GMM 성분별 평균/분산/가중치를 보고한다. 평균이 0이 아닌 성분이 있는지 확인한다(편향 모드).

### C2. 모드의 물리적 원인

각 표본에 다음 분류를 붙이고, 분류별 평균, σ, 꼬리 지표, GMM 성분 사후확률과의 대응(adjusted Rand, 상호정보량)을 계산한다.

| 분류 | 정의 | Goal 1에서 런타임 사용 가능 여부 |
|---|---|---|
| Δtap | 0 / −1 / +1 / 그 밖 | 불가(수신 신호로 오염을 감지하는 것이므로 Goal 2) — 원인 설명용 |
| 근접 경로 지배 객체 | PATHS_NEAR(LoS 이후 2 tap 이내)의 비LoS 에너지 비중 1위 객체: floor/ceiling/wall_y±/end | 불가 — 원인 설명용 |
| 근접 에너지비 | 근접 비LoS 에너지 / LoS 에너지 (dB) | 불가 — 원인 설명용 |
| 거리 d | 1 m 구간 | 가능(상태에서 계산) |
| 앙각 | 앵커에서 본 LoS 앙각 구간 | 가능 |
| 상대 bearing | 몸체 yaw − 앵커 방향 bearing, 30° 구간 | 가능 |
| 운동 | straight / in_place(회전) / stationary | 가능 |
| |g_ψ| | 하위 20% / 그 밖 | 가능 |

PATHS_NEAR는 G-T1에만 있다. BLOCK_C는 Δtap과 기하 분류만 쓴다.

### C3. 다중 척도 분산 분해

경로 표본을 along 거리 순으로 놓고 e_s의 분산을 다음으로 나눈다.

- 앵커 상수 μ_case
- 5 m 창 평균의 분산(느린 공간 성분)
- 1 m 창 평균의 분산 − 5 m 창 분산
- 0.25 m 창 평균의 분산 − 1 m 창 분산
- 나머지(λ 규모)

sweep 표본에서는 station 내 yaw 분산과 station 간 평균 분산을 나눈다. TEACH↔REPEAT, P-D(오프셋 재방문), P-E(검증 재방문) 쌍의 상관을 함께 보고한다. 같은 위치를 다시 지날 때 같은 오차가 나오면 이 오차는 잡음이 아니라 결정론적 공간장이다.

### C4. 기하 조건부 구조

σ(d), σ(앙각), σ(상대 bearing), GMM 가중치(d)를 robust 구간 추정으로 보고하고 부트스트랩(site 단위) 95% 구간을 붙인다. log σ와 log d의 기울기를 보고한다. 이것은 MB_VAR형 arm(Goal 1 허용)이 쓸 수 있는 정보의 양을 알려 준다.

### C5. 앵커 간 이전성 (LOAO)

새 RT 세 앵커에서 하나를 빼고 두 개로 다음 표현을 적합한 뒤, 뺀 앵커의 솎은 표본에서 95% 구간 coverage와 PIT 분포를 계산한다.

- R0 Gaussian, σ 상수
- R1 Gaussian, σ(d)
- R2 Student-t, scale(d), ν 공통
- R3 GMM K*(C1 BIC), 가중치 상수
- R4 GMM, 가중치(d)

이것은 표본 단위(주변분포) coverage이며 필터 integrity가 아니다. 상관 구조가 빠져 있으므로 필터 NEES와 다를 수 있다. 그 차이 자체를 §6에서 쓴다.

### C6. heading으로의 전달

e_ψ^eq의 분포, |g_ψ| 하위 20% 영역의 기여, 경로별 e_ψ^eq의 누적(5 m 창 평균)을 보고한다. 이는 EKF가 받는 heading 정보의 실제 오차 크기를 직관적으로 보여 준다. 필터 재실행은 이 사양에 포함하지 않는다.

### C7. RT 간, mount 간 비교

- 새 RT G-T1 vs BLOCK_C(기존 RT): C1, C3 지표를 나란히 놓는다. 두 RT의 기하(앵커 높이, 복도 폭, 재질)가 다르므로 차이는 기하 차이로만 해석한다.
- R2_aA_m0 vs R2_aA_m45: 같은 궤적과 앵커에서 e_s, e_ψ^eq, g_ψ 분포를 비교한다. 같은 pose에서 |e_ψ^eq|가 작은 쪽의 비율을 보고한다.
- 사용자 요청에 따라, mount 비교는 민감도가 아니라 EKF heading 정확도로 본다. BLOCK_C results_R2_aA_m0.csv와 _m45.csv의 heading_rmse_deg를 같은 (drift, SNR, seed, filter, baseline) 조합끼리 짝지어 차이와 부호 비율을 보고한다. 이 결과는 기존 파이프라인 결과이므로 보조 근거다.

## 5. 산출물

`research/G1_PACKET_EKF_20261114/CHAR_001/`

- `SPEC_KO.md` (이 문서, 실행 전 커밋)
- `scripts/` 특성화 코드
- `out/ERRORS_<case>.npz` 표본별 e_s, e_s^same, Δtap, e_r, e_r^abs, g_ψ, 분류 열
- `out/C1_SHAPE.json` … `out/C7_COMPARE.json`
- `fig/` 그림
- `REPORT_KO.md` 케이스별 다중경로 특성 설명과 §6 결정표 적용 결과

## 6. 표현 선택 결정표 (사전 등록, 실행 후 Fable과 논의)

결정은 표의 위에서 아래로 본다. 여기서 "가능"은 Goal 1 경계 안의 표현이라는 뜻이다.

| 관찰 | 해석 | 다음 모형 방향 |
|---|---|---|
| D1. 느린 공간 성분(5 m 창 분산 비중)이 50% 이상이고 재방문 상관 ρ≥0.9 | 오차는 결정론적 공간장. 독립잡음 표현으로는 분포 모양과 무관하게 NEES가 깨진다 | 상관 상태(colored/Schmidt) 또는 site 단위 공분산이 필수. 분포 모양은 그다음 문제 |
| D2. 기하 조건부 σ(d) 등으로 z의 꼬리가 Gaussian 기준 안으로 들어옴 | 꼬리는 이질 분산에서 생긴 것 | MB_VAR형 σ(geometry) + Gaussian |
| D3. 기하 조건부 후에도 K≥2 GMM이 BIC로 선택되고 성분이 Δtap/근접 객체와 대응(ARI≥0.3) | 모드는 물리적으로 다른 기전(tap 이동 vs 같은 tap 오염) | 런타임에 성분을 감지하면 Goal 2. Goal 1에서는 고정 가중치 Gaussian sum(가중치가 기하에만 의존)으로 표현 |
| D4. 성분이 물리 분류와 대응하지 않고 꼬리만 두꺼움 | 연속적 꼬리 | Student-t(ν, scale(geometry)) |
| D5. LOAO coverage가 앵커에 따라 크게 다름(어느 표현도 세 앵커 모두 0.90 이상이 아님) | 표현이 앵커 간 이전되지 않음 | 앵커 특이 성분을 불확실성 상태로 둬야 함(site/anchor bias를 consider가 아닌 상태로) |
| D6. e_r이 e_s보다 NEES에 더 큰 기여(기존 D7.1 결과와 일치) | 실패의 주원인은 거리 | 거리 쪽 표현을 먼저 정함. ranging 완화는 Goal 1 허용 |

## 7. 금지 사항

- G-T2, G-V 접근 금지
- 이 결과로 S2′ STOP 해제나 Step 3 재개 금지
- Δtap, 근접 경로, CIR 모양을 런타임 s 가중이나 기각에 쓰는 표현은 Goal 1 후보로 올리지 않는다(Goal 2)
