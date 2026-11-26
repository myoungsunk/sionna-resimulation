# 편파 관측의 0이 아닌 편향 반영 — Corridor FFD 실험 계획 (사전 고정)

| 항목 | 내용 |
|---|---|
| 상태 | DIAGNOSTIC_ONLY. 실행 전 동결(2026-11-26). 결과를 본 뒤 판정 규칙을 바꾸지 않는다 |
| 목적 | BV0(FFD 평균 + 분산 + 상관) 실패의 원인으로 지목한 "평균이 0이 아닌 편향"을 평균에 반영하면 회복되는지, 편향을 뺀 뒤 분산·상관 설정이 결과를 바꾸는지 확인한다 |
| 역할 | FFD는 시뮬레이션에서 LoS 참값과 같다(parity ≤ 1.7e−6). 이 실험은 SWB 조립 규칙의 힌트를 얻기 위한 oracle 단계이며, 실측 모델이 아니다 |
| 장면 | RT Corridor, 앵커 B (10, 0, 2.65), tag 0.45 m, mount 0°. station sweep 200위치 × 36 yaw |
| 궤적·seed | R2, R4, R5. dev seed 10–29. B0와 L2_GYRO_ARW |
| 고정 | F2 경로(GM 상태 + c₀ KI, 1 m / 10°, 10 s), range 채널 S0-id(μ_r, R_rr), H2·H2S 참조, M7 채점 모듈(해시 고정) |

## 1. 근거 (station 정적 분석, 열 하나씩 빼고 평가)

- 덧셈형(스칼라) 평균 편향은 MSE의 0.3% 이하다.
- 0이 아닌 편향은 heading형이다. s 편향이 a(ψ)에 비례해 스칼라 평균에서 상쇄되며, 중거리 heading 등가 −2.48°.
- 재현성: 근거리는 국소(이웃 열 R² +0.54, 같은 열 다른 줄 +0.66), 중거리는 bin 수준 평균만, 원거리는 없음.
- BV0의 분산 표는 이 편향을 MSE로 흡수한다. packet 포함률은 0.92–0.95로 맞아 보이지만, 필터는 이를 평균 0인 잡음으로 다뤄 heading 상태로 흡수한다(BV0 heading 편향 +0.80°).

## 2. arm

| arm | 평균 (블록 m) | μ_s | 분산 표 | 상관 | 비교 대상 |
|---|---|---|---|---|---|
| BV0 | FFD | 0 | M0 (s_full − FFD) | F2 기본 | (기존, parity) |
| BVK | BV 평활 δ̄, κ̄ (Gaussian 0.75 m) | 근거리 kriging | BVK | F2 기본 | (기존, parity) |
| P0 | FFD + 스칼라 offset (bin × 앵커 쪽 평균) | 0 | P0 재적합 | F2 기본 | BV0 |
| P1 | FFD에 heading형 bin × 쪽 평균(δ_bin, κ_bin, offset) 적용. bin 경계는 logistic 연결(폭 0.15 m) | 0 | P1 재적합 | F2 기본 | BV0 |
| P2 | P1 | 근거리(< 3 m) kriging, 라벨 s_full − m_P1, S0 근거리 초모수 | 근거리는 LOSO kriging 잔차, 중·원거리는 P1 | F2 기본 | BVK |
| P3 | BVK와 같음 | 같음 | BVK | kernel을 거리 bin별로: 근거리 0.4 m / 25°, 중·원거리 0.15 m / 20°·15° (station·경로 상관 측정값) | BVK |
| P4 | BVK와 같음 | 같음 | BVK | 원거리(≥ 6 m) packet의 KI·누적항 V = 0 (GM 적재는 유지) | BVK |

- 블록 정의와 표: `code/bb_block.py`, `code/prep_bb.py`. replay: `code/m8_replay_k.py`(frozen `m8_replay.py` sha 4069ec621458에서 kern, far_corr_off만 추가. 기본값에서 동일)
- BVK 표는 저장된 TABLE_BVK.json과 c1, c0 최대 차 0.0. seed 10에서 BV0 replay는 저장 결과와 일치, BVK는 상대 차 ≤ 1e−4(근거리 kriging 수치 경로)

## 3. 판정 (dev seed 10–29, B0·L2 각각)

공통 지표
- N_I: integrity 통과 seed 수(M7 assess, 참조 H2S, I_seed)
- 짝 비율: seed별 pooled(R2+R4+R5) XY RMSE, heading RMSE의 arm / 비교 대상 비. 중앙값과 bootstrap(10,000회, rng 0) 97.5% 상한
- 거울해 seed 수, pooled Pose95 / Heading95 / XY95 / NEES3 중앙값
- 진단 D1: 궤적·거리 bin별 heading 평균 오차(°), heading z RMS

| 질문 | 규칙 |
|---|---|
| Q0 스칼라 offset은 원인이 아닌가 (P0 vs BV0) | XY·heading 짝 비율 중앙값이 모두 [0.97, 1.03]이면 "원인 아님" |
| Q1 heading형 평균이 회복시키는가 (P1 vs BV0) | 개선: XY·heading 비율 상한 < 1, N_I(P1) > N_I(BV0). 개선이 없으면 "bin 평균만으로는 부족" |
| Q2 근거리 국소 평균 + bin 평균이 BVK와 동등한가 (P2 vs BVK) | 비열등: N_I ≥ N_I(BVK) − 1, XY·heading 비율 상한 ≤ 1.10, 거울해 ≤ BVK |
| Q3 kernel 길이 (P3 vs BVK) | Q2와 같은 비열등 규칙 + Pose95·Heading95 변화 보고 |
| Q4 원거리 상관 처리 (P4 vs BVK) | Q2와 같은 비열등 규칙 + Pose95·Heading95 변화 보고 |

B0와 L2 중 하나라도 규칙을 못 넘으면 해당 질문은 "불성립"으로 기록한다.

## 4. 한계 (사전 기록)

- FFD 기준이라 실측에서 만들 수 있는 블록이 아니다. 결론은 SWB 조립 규칙의 방향만 준다.
- 확정 seed(70–89)는 이 계획에 없다.
- 절대 기준(18/20)은 판정하지 않는다. BVK 자체가 상대 판정 통과였다.
