## 2026-10-20 사후 적용성 정정

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN — SRC_TAP에 한정.** Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T3 SourceFFD 표 재생성

네 표와 구 LUT 변화 목록을 실제 실행에서 산출했다. VERIFICATION에 기존 POWER1 RMSE·gate 및 독립 scorer 검사를 기록했다.

Native LoS 및 hybrid는 ORACLE_DIAGNOSTIC으로 분리했다. Hybrid POWER 파라미터는 네 셀 모두 원본 Full-only로 고정했다. 미확보 E1 ZIP parity는 NOT_ESTABLISHED다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.

T6 이후 SRC_TAP 재학습판의 동일 표는 SRC_TAP/에 보존했다. 실행39361112976, artifact12237193562. B_OLD 표를 덮어쓰지 않았다. SRC_TAP의 범위 Jacobian은 tap 내부 0이며 경계에서 미분 불가능하므로 연속적 Range 정보나 정규화 posterior를 주장하지 않는다.
