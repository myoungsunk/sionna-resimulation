# 측정 수준 Δs 결과를 재귀 필터로 확인 — 실행 전 고정 (2026-10-21)

## 확인할 측정 수준 결과
1. Δs(+기존 특징) 평균 보정이 range 측정오차 4–11%, heading 측정오차(편파) 22–35%(고민감도 case) 감소.
2. Δs 고유 개선은 |Δs₊₁| 상위 20%(≈|Δs₊₁|≥0.04–0.06)에 집중.
3. 편향 극심과 Δs의 연관(재귀 출력의 국소 err/σ 기준, 이미 일부 확인) — 이번에는 재귀 개선량을 Δs 5분위별로.

## 구현
EKF 구조·gate(패킷 R)·η=1 그대로. 분산은 POWER_DIAG(보정 arm도 분산 불변 → 평균 효과만 분리). INFL_R 결합 arm만 range 분산 상향.
평균 모델: held route 제외 두 route의 Full 패킷으로 HGB(max_iter=200, lr=0.05, leaves=15, l2=1, seed 0) 학습, 라벨 \(e_r=r-h_r(\mathrm{GT})\), \(e_s=s-h_s(\mathrm{GT})\). 입력 EX = 기존 특징 16개, EXDS = EX + 부호 Δs 8개(o=±1,±2,±4,±8). 게이트 G = |Δs₊₁|≥τ(train 80분위)인 패킷만 보정, 나머지 POWER1 평균.
| arm | range 평균 | 편파 평균 | range 분산 |
|--|--|--|--|
| BASE | POWER1 | POWER1 | POWER |
| INFL_R | POWER1 | POWER1 | 상향(큰 Δs) |
| MU_R_EX / MU_R_EXDS | HGB(EX) / HGB(EXDS) | POWER1 | POWER |
| MU_S_EX / MU_S_EXDS | POWER1 | HGB(EX) / HGB(EXDS) | POWER |
| MU_RS_EXDS | HGB(EXDS) | HGB(EXDS) | POWER |
| G_MU_R / G_MU_S / G_MU_RS (EXDS) | 게이트 패킷만 | 게이트 패킷만 | POWER |
| INFL_R+MU_R_EXDS | HGB(EXDS) | POWER1 | 상향 |
| INFL_R+G_MU_RS | 게이트 | 게이트 | 상향 |
조건: 7 case × {Full B0, Full L2, LoS B0(진단)}.

## 보고
- 재귀: heading·거리오차·radial RMSE비(대 BASE, 대 INFL_R), 개선/>10%악화, NEES, gyro bias.
- 측정 대 재귀: 같은 arm의 패킷 측정오차 감소율과 재귀 오차 감소율을 나란히.
- Δs 양상: 재귀 오차 차이(arm − BASE)를 case 내부 |Δs₊₁| 5분위별로.
- Δs 고유 기여: EXDS 대 EX.
- QA: BASE·INFL_R가 이전 재귀 run 재현.
