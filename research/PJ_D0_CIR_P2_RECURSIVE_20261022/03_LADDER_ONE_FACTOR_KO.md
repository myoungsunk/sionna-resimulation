# P2 사다리 — 한 번에 한 요인 (실행 전 고정, 2026-10-22)

P2-A(run 39780269171)는 BASE와 비교 arm 사이에 μ_s 제거·R_s 상수화·보정기 교체가 동시에 들어가 있어 어느 요인의 효과인지 분리되지 않았다. 이 실험은 인접한 두 arm이 **요인 하나만** 다르도록 배열한다. P2-A 결과와 코드는 수정하지 않는다.

## 고정
- 입력: P2-A와 같은 원본 RF, SourceFFD, odom·gyro seed, POWER μ_r·V_r, 4-state EKF, joint χ²₂(0.99) gate, Joseph.
- 모델: P2 smoke run 39773370468의 train-only artifact 그대로(재학습 없음).
- 초기조건: NOM 하나. 조건: Full B0와 Full L2 — **항상 따로 보고**.
- 채점: 0–2, 2–10, 10–30, 30+ s, 전체를 각각 보고. 기존 주 지표(30+ s)도 함께 남긴다.

## 사다리
| 단계 | arm | 편파 평균 보정 | 편파 R_s | ê | 이전 단계와 다른 것 |
|---|---|---|---|---|---|
| S0 | L_BASE | μ_s POWER | POWER V_s (packet별, R 원본) | 0 | 기준 (P2-A BASE와 1e-7 일치해야 함) |
| S1 | L_NOMU | 0 | POWER V_s | 0 | S0에서 μ_s만 제거 |
| S2 | L_CONSTR | μ_s POWER | 상수 R_s(CIR LORO), cross term 0 | 0 | S0에서 R_s 구조만 변경 |
| S3 | L_CIR | 0 | POWER V_s | CIR_ONLY | S1에서 ê만 추가 |
| S4 | L_WIDE | 0 | POWER V_s | WIDE, d0 = z_s − h_s(x̂⁻) | S3에서 보정기만 교체 (d0 추가) |
| S5 | L_WIDE_GTD0 | 0 | POWER V_s | WIDE, d0 = z_s − h_s(GT pose) | S4에서 d0 계산 위치만 GT로 (반사실, 진단 전용) |
| S6 | L_ORACLE | 0 | POWER V_s | z_s − s_LoS | S3/S4의 ê를 정답으로 (같은 R에서의 상한) |
| — | L_RAW | 0 | 상수 R_s | 0 | = P2-A RAW_SHARED (S1+S2 동시 변경, 가산성 확인용) |

## 각 쌍이 답하는 질문
- S0→S1: POWER μ_s의 효과. S0→S2: R_s 구조의 효과. (S1−S0)+(S2−S0) vs (RAW−S0): 두 요인의 상호작용.
- S1→S3: CIR 보정기 vs 보정 없음(같은 R). S3→S4: d0 추가의 효과. S4→S5: 재귀 prior 오차가 d0를 거쳐 주는 영향. S4 vs S6: 같은 R에서 남은 여지.

## 기록
arm·구간마다 heading RMSE, signed bias, NEES, 95% 포함률, σψ, XY·radial·tangential, accept율, 그리고 보정 후 관측의 LoS 대비 잔차 ε = (z_s − ê − μ_s) − s_LoS의 평균·accept 조건부 평균·RMS(s_LoS는 오프라인 채점 전용).

## QA (실패 시 해석 금지)
- L_BASE = P2-A BASE_POWER(NOM, B0/L2)와 1e-7 이내.
- L_RAW = P2-A RAW_SHARED(NOM, B0/L2)와 1e-7 이내.
- POWER_DIAG cross term C_rs의 최대값 기록(0이 아니면 S2는 R_s와 C_rs 두 요인 변경으로 표기).
- L_WIDE_GTD0와 L_ORACLE만 GT/LoS에 접근. 나머지 arm은 추정 상태와 측정만 사용.

## 판정
요인별 효과를 크기(비율·차이)와 방향으로 route×조건(B0/L2)×구간별로 보고한다. 통과/실패 임계값을 두지 않는다. 같은 세 개발 route 결과이므로 일반화 주장은 하지 않는다.
