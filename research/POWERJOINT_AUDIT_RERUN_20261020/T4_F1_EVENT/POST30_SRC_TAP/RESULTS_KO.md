## 2026-10-20 사후 적용성 정정

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN — SRC_TAP에 한정.** Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T4 F1 병합 결과

TECHNICAL: INCOMPLETE_OR_ERROR; 과학 판정: NOT_ESTABLISHED.

고정 5+5 이벤트를 대상으로 같은 개입의 전체 유익 이벤트 안전성을 요구했다. 세부 회수 비율·부호 변경은 DECISION.json, 모든 지표는 INTERVENTIONS.csv에 보존한다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 모든 개입 비교는 ORACLE_DIAGNOSTIC이다.
