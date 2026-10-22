# 엄격 분리 재검증 계획 (실행 전 고정, 2026-10-22)

목적: (Q1) 학습·비교 조건을 엄격히 분리한 뒤에도 Δs range 평균 보정의 이득이 유지되는가. (Q2) heading 오차와 heading 포함률을 함께 개선하는 조합이 있는가.
배경: 외부 평가(첨부)의 지적 — 다단계 학습의 간접 누수(앞단 POWER teacher가 평가 route GT를 사용), NEES 기준 표기, 포함률 해석, d0 검출기 prior 혼재, 편파 gate 구현(큰 분산 + χ²₂ 유지), 14 조건 독립성, 방법 선택의 적응.

## 1. 격리 규칙
평가 route H ∈ {R2, R4, R5}, 학습 route T = 나머지 둘 {A, B}. H의 정보(GT·RF 모두)는 아래 어떤 단계에도 쓰지 않는다.
- H 평가에 쓰는 POWER: 기존 OOF(H용, A+B로 학습) 그대로 — 이 모델은 H를 쓰지 않음.
- T 안에서 쓰는 POWER(teacher): inner OOF로 새로 적합. A용은 B만, B용은 A만으로 학습(POWER_BIN_JOINT 동일 절차, 위치 중복 제외 동일). 기존 OOF(A용은 B+H)를 쓰지 않는다.
- range 평균 HGB(기존 / 기존+Δs): H 평가용은 T의 GT 라벨로 학습(기존과 동일, 누수 없음). T 안의 1차 필터용은 inner(A용은 B만).
- Δs range 상향(INFL_R) 계수 τ, κ: T 패킷 + inner POWER 잔차로 산출.
- d0 임계 τ5(편파 플래그): T의 inner-POWER BASE 필터 prior d0의 95분위.
- COMMON η: T의 inner 필터 결과로 선택(아래 기준), H 결과를 보지 않는다.

## 2. arm (stage B, H의 Full B0·L2, LoS B0)
| arm | range 평균 | gate 판정 | 편파 플래그(|d0|>τ5) | 갱신 R |
|--|--|--|--|--|
| BASE | POWER | χ²₂, 보정된 ν | – | R |
| INFL_R_S | POWER | χ²₂ | – | V_r×κ_hi (|Δs₊₁|≥τ) |
| MU_R_EX | HGB 기존 | χ²₂ | – | R |
| MU_R | HGB 기존+Δs | χ²₂ | – | R |
| MU_R+GRAW | HGB 기존+Δs | χ²₂, **보정 전**(POWER μ_r) ν로 판정 | – | R |
| MU_R+RONLY | HGB 기존+Δs | 플래그 시 range-only χ²₁(0.99)=6.635, 아니면 χ²₂ | 플래그 시 편파 관측 제거(명시적 1차원 갱신) | R |
| MU_R+GRAW+RONLY | HGB 기존+Δs | 위 둘 결합(range-only 판정도 보정 전 ν_r) | 동일 | R |
| BASE_η* / MU_R_η* / MU_R+GRAW_η* / MU_R+GRAW+RONLY_η* | | | | ηR (gate는 R, COMMON 방식) |
| (투명성) BASE_η2, BASE_η3, MU_R+GRAW_η2, MU_R+GRAW_η3 | | | | 고정 η |

η 선택(stage A): 격자 {1, 1.5, 2, 3, 4}. T의 각 case-bias(B0·L2)에서 inner 필터로 BASE와 MU_R+GRAW를 실행, 기준 = T 중앙값 |log(heading NEES)| 최소. η*_BASE, η*_MU를 따로 선택. MU_R+GRAW+RONLY_η*는 η*_MU 사용.

## 3. 지표 (t≥30 s)
- heading: RMSE, 평균 |오차|, signed bias, **heading NEES(1차원, 기준 1)**, **명목 95% 구간의 실제 포함률(기준 0.95)**, 평균 σψ.
- 위치: 앵커 거리 오차(‖p̂−a‖−‖p−a‖), radial, tangential, XY RMSE, **XY NEES(2차원, 기준 2)**, XY 95% 포함률.
- 보고 단위: case-bias 14개 중앙값 외에 route별 중앙값(독립 단위 3개), case별 표. 14 조건을 독립 표본으로 해석하지 않는다.
- 불확실성: case별 heading MSE비·포함률 차이에 대해 시간 블록(10 s) paired bootstrap 2,000회 95% CI.
- 동일 prior 검출기 비교(BASE prior, H): |d0|, |ν_s|, w_s² = ν_s²/(H_sP⁻H_sᵀ+V_s), |ν_s|/√(H_sP⁻H_sᵀ) — 같은 prior·같은 공분산.

## 4. 판정 (사전 고정)
- Q1 (range 이득 유지): MU_R의 앵커 거리 오차비 route별 중앙값이 세 route 모두 < 1, 그리고 XY RMSE비를 함께 보고(XY 악화 시 "앵커 방향만 개선"으로 기술).
- Q2 (동시 개선): 어떤 arm이 BASE 대비 (i) heading RMSE비 route별 중앙값 세 route 모두 ≤ 1, (ii) heading 포함률이 BASE보다 0.95에 가까움(route별 중앙값 세 route 모두), (iii) heading NEES가 BASE보다 1에 가까움, (iv) 앵커 거리 오차비 < 1을 모두 만족하면 "동시 개선 후보". 하나라도 실패하면 실패 항목을 그대로 보고.
- 이 결과도 같은 세 route에서 얻은 개발 결과이며, 일반화 주장은 미사용 자료(새 route·실측) 확인 후로 둔다.

## 5. 이번에 하지 않는 것
- d0 라벨 POWER 재학습의 엄격 재실행(별도), fp 이동 계층과 실제 경로 겹침의 대조(경로 데이터 필요).
