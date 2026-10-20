## 2026-10-20 사후 적용성 정정

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN — SRC_TAP에 한정.** Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T4 F1 이벤트 검증

TECHNICAL: COMPLETE_WITH_PRESERVED_D4_NONSPD. 과학 판정: NOT_ESTABLISHED (B_OLD 및 SRC_TAP).

고정 10개 이벤트의 POWER1/SKIP/D1/D2/D3/D5/D6 실행과 독립 채점을 완료했다. B_OLD와 SRC_TAP 각각 D4 5건은 교차공분산 제거 후 NONSPD로 실패했다. 공분산을 수리하거나 실패를 제외해 통과시키지 않았다.

주 판정 구간은 원문과 같은 POST30(마지막 이벤트 RF 시점부터 30초 후까지)이다. 최초 lock의 GLOBAL_T30는 원문 효과량과 평가 범위가 달랐다. 결과를 지우지 않고 52b1212에서 범위 수정 lock을 먼저 커밋한 뒤 기존 POST30 행만 다시 집계했다. GLOBAL_T30 결과는 final_B_OLD/ 및 SRC_TAP/에 그대로 있다. 필터·RF·arm·임계값을 변경하지 않았다. 원문의 상세 끝점 구현은 확보되지 않아 완전한 수치 일치를 주장하지 않는다.

D3/D4/D6 중 유해 이벤트에서 50% 이상 회수하면서 모든 고정 유익 이벤트의 안전성을 만족한 진단은 없다. F1 지지 이벤트는 0/5이며, 채널 제거만으로 설명된다는 기각 기준도 충족하지 않았다.

| 이벤트 | 고정 역할 | B_OLD POST30 skip 개선 ° | SRC_TAP POST30 skip 개선 ° | SRC 부호 변경 |
|---|---|---:|---:|---|
| R5_A_M0_x10_16_V1 | harmful | 7.740819 | 5.537667 | False |
| C01_A_x16_21_V1 | harmful | 5.389283 | 3.107087 | False |
| O03_y4_8_V1 | harmful | 1.803351 | 1.360401 | False |
| C01_B_x16_21_V1 | harmful | 4.318979 | 3.786330 | False |
| C02_A_x4_10_V1 | harmful | 1.770663 | -0.222308 | True |
| R5_A_M0_x10_16_V2 | beneficial | -1.176322 | 3.887806 | True |
| C01_A_x10_16_V1 | beneficial | -3.070171 | -2.659054 | False |
| O03_y4_8_V2 | beneficial | -15.264760 | 0.775746 | True |
| O02_y4_8_V1 | beneficial | -4.305695 | -4.754674 | False |
| R2_A_M45_x10_16_V1 | beneficial | -2.437877 | -2.283843 | False |

SRC_TAP에서는 tap 안의 range Jacobian이 0이므로 D2(s 제거)는 range-only update의 정보가 없어져 skip과 같아진다. 이를 관측 원인의 일반적 증거로 해석하지 않는다.

## 주장하지 않는 것

개입은 모두 ORACLE_DIAGNOSTIC이다. GT prior reset을 온라인 정책으로 제시하지 않는다. 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.
