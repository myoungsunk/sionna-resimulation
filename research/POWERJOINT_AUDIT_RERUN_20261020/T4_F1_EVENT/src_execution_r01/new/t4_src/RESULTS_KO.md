## 2026-10-20 사후 적용성 정정

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN — SRC_TAP에 한정.** Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T4 F1 이벤트 진단

TECHNICAL: ERROR_OR_BLOCKED_INPUT; 과학 판정: NOT_ESTABLISHED.

고정 이벤트의 역할·bin·visit은 결과에 따라 변경하지 않았다. D1–D6 및 skip은 ORACLE_DIAGNOSTIC이며 온라인 정책 성능 주장이 아니다. 전체 모션 t≥30 s 판정과 RF 시점 비교·이벤트·이후 30 s 지표를 함께 보존한다. 분할 실행의 최종 판정은 전체 INTERVENTIONS.csv를 합친 뒤 수행한다.

| 이벤트 | 기존 역할 | 정본 skip 개선량 ° | 부호 변경 | ≥50% 회수 및 전체 유익 안전성 충족 개입 |
| --- | --- | --- | --- | --- |
| R5_A_M0_x10_16_V1 | harmful | None | None | 없음/미확립 |
| C01_A_x16_21_V1 | harmful | 1.3862410590257153 | False | 없음/미확립 |
| O03_y4_8_V1 | harmful | 1.2224214641011435 | False | 없음/미확립 |
| C01_B_x16_21_V1 | harmful | 2.589767756182732 | False | 없음/미확립 |
| C02_A_x4_10_V1 | harmful | -0.19484800156560933 | True | 없음/미확립 |
| R5_A_M0_x10_16_V2 | beneficial | None | None | 없음/미확립 |
| C01_A_x10_16_V1 | beneficial | -5.308801935276251 | False | 없음/미확립 |
| O03_y4_8_V2 | beneficial | 0.2865938078988064 | True | 없음/미확립 |
| O02_y4_8_V1 | beneficial | -7.783617051282871 | False | 없음/미확립 |
| R2_A_M45_x10_16_V1 | beneficial | None | None | 없음/미확립 |

FIRST_HARMFUL_UPDATE.csv는 최초 유해 update의 채널을, DECISION.json은 개입별 회수 비율을 제공한다. 어느 개입의 RMSE 회수가 가장 큰지는 인과 경로의 유일성을 뜻하지 않는다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 이전 skip 수치는 정본 센서 재실행과 직접 동일하다고 가정하지 않는다.
