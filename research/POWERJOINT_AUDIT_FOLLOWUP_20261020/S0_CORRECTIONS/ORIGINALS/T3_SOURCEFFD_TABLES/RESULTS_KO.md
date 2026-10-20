# T3 SourceFFD 표 재생성

네 표와 구 LUT 변화 목록을 실제 실행에서 산출했다. VERIFICATION에 기존 POWER1 RMSE·gate 및 독립 scorer 검사를 기록했다.

Native LoS 및 hybrid는 ORACLE_DIAGNOSTIC으로 분리했다. Hybrid POWER 파라미터는 네 셀 모두 원본 Full-only로 고정했다. 미확보 E1 ZIP parity는 NOT_ESTABLISHED다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.

T6 이후 SRC_TAP 재학습판의 동일 표는 SRC_TAP/에 보존했다. 실행39361112976, artifact12237193562. B_OLD 표를 덮어쓰지 않았다. SRC_TAP의 범위 Jacobian은 tap 내부 0이며 경계에서 미분 불가능하므로 연속적 Range 정보나 정규화 posterior를 주장하지 않는다.
