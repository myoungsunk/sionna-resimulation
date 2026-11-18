# O3 Office LoS 궤적 필터 재생 — 실행 전 동결

| 항목 | 내용 |
|---|---|
| 질문 | Corridor에서 만든 방법(F2 + sweep 보정)이 Office에서도 H2보다 나은가. 보정을 Corridor에서 가져오는 경우(T0)와 Office sweep으로 다시 만드는 경우(T1)를 비교 |
| 데이터 | `OFFICE_DATA_ALL_20261118` (커밋 `04249f6`): 35 station 360° sweep, O01–O03 mount 0° Release |
| 사용자 결정 | NLoS 구간은 궤적으로 쓰지 않는다(2026-11-18, 우선 적용) |
| 사전 노출 | 실행기 점검 때 seed 10 B0 1건의 결과를 봤다(H2 pooled Pose95 0.353, F2T1 0.688). 이 결과로 바꾼 설정은 없다 |
| 봉인 | G-T2/G-V 미접근. Corridor 판정 결과와 설정은 바꾸지 않는다 |

## 1. 궤적

LoS 판정은 RT `LOS_EXISTS`를 따른다.

| 궤적 | RF pose | 시간 | 비고 |
|---|---|---|---|
| O01 | 192 | 115 s | 전 구간 LoS |
| O02 | 207 | 130 s | 전 구간 LoS |
| O03L | 136 | 95 s | O03의 RF 137–272행(t 99–194 s)만 사용 |

- O03L은 O03에서 30 s 이상 이어진 유일한 LoS 구간이다.
- O03의 NLoS 두 구간(19–98 s, 195–274 s)은 각각 복도를 올라갔다 돌아오는 왕복이고 180° 회전을 포함한다. 이어 붙이면 heading이 끊기므로 쓰지 않는다.
- O03의 짧은 LoS 구간(0–18 s, 275–293 s)도 궤적으로 쓰지 않는다. 다만 H2 학습 donor 행에는 포함한다.

## 2. 입력

- seed 10–29, 조건 B0와 L2(Q 일치). Corridor M7과 같은 생성 법칙이다.
  - 동결 sensor_v2, `motion_increments(legacy-euler)`.
  - x0 = truth[0] + rng(seed, "initial")·[0.1 m, 0.1 m, 5°].
- 관측 z = [range_m, s_fp]. 동결 추출기를 Office H_FULL에 적용한다.
- 관측 모델은 동결 FFD observer에 Office anchor (5, 2.2, 2.65)를 넣은 것이다.
  - O1 parity: 합성 LoS 상대오차 2e−5, h(truth)와 라벨 차 1e−15.

## 3. Arm

| arm | 구조 | μ_r | R_rr | μ_s | 편파 분산 | σ_b |
|---|---|---|---|---|---|---|
| H0 | DR | — | — | — | — | — |
| **H2 (비교군)** | M7 G0 | HGB(EXIST+DS), 궤적 LORO | POWER, 궤적 LORO | POWER, 궤적 LORO | POWER R_ss | 0.005 (M7 동결값) |
| F2L | F2 | H2와 같음 | H2와 같음 | H2와 같음 | rule B, donor 궤적 nested LORO 잔차 | 0.005 |
| F2T0 | F2 | Corridor sweep HGB (b) | Corridor POWER (b) | Corridor POWER (b) | Corridor 5줄 표 | 0 |
| F2T1nK | F2 | Office LoS sweep HGB (b) | Office POWER (b) | Office POWER (b) | Office LoS station rule B | 0 |
| **F2T1 (주 후보)** | F2 | 위와 같음 | 위와 같음 | ρ < 6 m는 Office kriging, 그 밖은 POWER (b) | Office 표 | 0 |
| F2T1V | F2 | 위와 같음 | 위와 같음 | F2T1과 같음 | 근·중거리를 kriging CV 잔차로 재적합한 표 | 0 |

공통 사항:
- **궤적 LORO:** 평가 궤적을 뺀 나머지 두 궤적의 LoS 행으로 학습한다.
- **(b) 가중:** 평가 궤적의 RF pose heading으로 만든 10° 히스토그램이다.
- **Office sweep:** LoS station 25곳(900행)을 쓴다.
- **kriging 초모수:** bin별로 station 하나씩 빼는 교차검증으로 정했다([O3_INFO.json](O3_INFO.json)).
- **F2 공통:** 핵 1 m/10°, 이력 10 s/100 packet은 M7 그대로다.
- **sweep 계열 packet:** 측정·센서·초기 필드만 원 packet에서 가져온다(Corridor 개정 01의 A6과 같은 구성).

## 4. 판정

- **채점기:** M7 동결 함수를 쓴다(`from_trace`, `scores_with_blocks` 블록 5/10/20 s, `assess_group`, `assess_seed`).
  - `assess_seed`에는 경로 이름표만 바꿔 넘긴다(O01→R2, O02→R4, O03L→R5).
  - 정확도 기준 arm은 H2다.
- **거울해 대신 gross 실패를 쓴다.** M7의 거울해는 Corridor 경로마다 정의된 통과 구간에 묶여 있어서 Office에 쓸 수 없다. 정의는 XY 오차 > 1.0 m가 10 s 이상 이어진 구간의 개수이고, M7의 mirror 칸에 넣는다.
- **arm별 판정:** 조건마다 N_J ≥ 18/20이고 gross 0이면 통과다.
- **함께 보고:** 궤적별로 seed 20개를 합친 RMSE와 포함률, H2 대비 변화율.
