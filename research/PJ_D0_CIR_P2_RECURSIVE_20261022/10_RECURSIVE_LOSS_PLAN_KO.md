# 재귀 손실 기전 분해 (실행 전 고정, 2026-10-23)

## 무엇을 설명하려는가
R2 분해에서 GT pose 기준의 정적 구간(≈65 패킷) 가중 편향비 PWIDE/BASE는 case별 재귀 heading RMSE비의 순위를 맞혔지만(Spearman 0.86), 모든 case에서 재귀 결과가 더 나빴다: R2 +0.54~+0.64, R4 +0.16~+0.29, R5 +0.07~+0.21. 또한 정확한 LoS를 쓰는 ORACLE도 R5에서 1.0°가 남는다. 정적 분석과 재귀 필터 사이에서 무엇이 오차를 키우는지 찾는다.

## 정적 분석과 재귀 필터의 차이 (후보 기전)
| 기전 | 정적 분석 | 재귀 필터 |
|---|---|---|
| M1 gate | 전 패킷 | joint χ²₂(0.99) 수용 패킷만 |
| M2 선형화 | GT pose의 h, g | 추정 prior의 h, H (위치·heading 오차가 h와 g를 바꿈) |
| M3 gyro bias 흡수 | 없음 | b_g 상태(process noise 0)가 지속 편향을 gyro bias로 해석 → heading에 적분 |
| M4 위치 결합 | 위치 = GT | 추정 위치 오차가 h_s(x̂)와 range 갱신을 통해 heading에 들어옴 |
| M5 보정기의 prior 의존 (c2) | d0(GT) | d0(prior) (검증 1에서 WIDE는 작았음, PWIDE는 미측정) |
| M6 필터 기억 | 창 단위 WLS | heading q가 매우 작아 사실상 전 이력의 가중평균, P_ψψ 축소 |

## 반사실 replay (한 번에 한 기전만 끈다)
보정기 3종 × 조건 5종 = 15 arm, NOM, Full B0/L2, R = POWER V_s.
- 보정기: BASE(μ_s POWER), PWIDE_NOES(사다리 4 P_D0), ORACLE(정답 LoS).
- 조건:
  - REAL: 실제 필터 (parity: BASE = P2-A, PWIDE_NOES = 사다리 4, ORACLE = 사다리 1).
  - NOGATE: gate 판정 R만 10¹²배(항상 수용), 갱신 R 그대로 → M1.
  - GTLIN: h·H를 GT pose에서 계산하고 h(x̂) ≈ h(GT) + H_GT(x̂ − x_GT)로 1차 근사. 보정기 입력 d0는 실제 prior 그대로 → M2(+M4의 h 경로).
  - BIASFIX: b_g를 참값으로 고정(P의 bias 행·열 0) → M3.
  - XYGT: 매 갱신 전에 x, y를 GT로 두고 위치 공분산·교차 공분산 0 → M4(+M2의 위치 부분).
- 추가 기록: 각 arm의 c2(PWIDE: ê(d0 prior) − ê(d0 GT)), accept, b_g 오차, eps(= 보정 관측 − s_LoS).
- M6는 별도 arm이 아니라, 각 조건에서 ORACLE의 남는 오차로 본다.

## 판정 방식
각 조건에서 (a) BASE·PWIDE·ORACLE의 heading RMSE 절대값, (b) PWIDE/BASE 비, (c) REAL 대비 변화를 route × 조건 × case로 보고한다. 어떤 기전을 껐을 때 PWIDE/BASE 비가 정적 구간 편향비 쪽으로 가장 많이 이동하는지, 그리고 ORACLE의 남는 오차가 줄어드는지를 크기로 비교한다. GTLIN·XYGT·BIASFIX·ORACLE은 GT를 쓰는 진단 전용이며 운용 후보가 아니다.
