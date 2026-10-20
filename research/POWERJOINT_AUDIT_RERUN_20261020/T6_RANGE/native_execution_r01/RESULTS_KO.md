## 2026-10-20 사후 적용성 정정

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN — SRC_TAP에 한정.** Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다.

과거 '요청 9,519점 중 2,268점 미확보이므로 BLOCKED_INPUT'이라는 현재 판정은 철회한다. 7,251점 실행 기록과 원문은 보존하며, 서로 다른 모집단의 대응은 별도 S0 모집단 감사에서 판정한다. 이 정정은 새 모집단 수치나 대응 인증을 주장하지 않는다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T6 Native LoS 검출기 진단

점수 7251 / expected 9519; SRC_TAP RMSE 0 m, <.01 m 목표 True.

안정 셀 FD 최대차 0.0; tap 전환 stencil 0/43506. 전환에서는 미분이 정의되지 않는다.

P1 재학습·POWER1 재귀·LoS 안전성 평가: NOT_EXECUTED. 잔차 개선만으로 추정 개선을 주장하지 않는다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, tap 전환점의 미분 가능성을 주장하지 않는다.
