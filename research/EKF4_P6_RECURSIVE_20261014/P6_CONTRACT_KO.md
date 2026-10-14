# P6 단계 시작 — 동결 RF R0 기반 재귀 4-state 추정 연구용 실행 계약

**주의:** P4의 동일 선형화/관측 parity는 검증됨. P4의 국소 MAP는 4/10 미수렴, 기존 P5 G3 위치 적분은 TV=0.387065로 기준 posterior 미확보. 이 상태에서 P6을 실행하더라도 **'정식 P5를 통과한 전체 nonlinear posterior/최종 연구 성공'이라고 쓰지 않는다**. 사용자가 요청한 단계별 진행을 위하여 P6을 구분된 **exploratory audited recursive branch**로 실행하고, 미해결 reference는 `P5_UNVALIDATED`로 명시.

입력: P0 동결 R2_aA_m0의 `H_LoS/H_FULL`, archived observer, 2deg LUT, Tnone 195.6sec (979 frames), 동일 frozen source; R0 offset=-0.5315983906250129, `Rs=0.09²`, `Rr=.0068578637`, `Rsr=0`은 가정으로 유지. 독립 sensor seed는 실제 RF scene 독립이 아님.

우선 대상: R2_aA_m0, LoS·Full, 각 `noise_pair(level1)`, `gyro_bias(level2)`, sensor seed0. 주요 비교군: DR3(3state no RF), EKF3 joint C, DR4(bias state no RF), EKF4 joint C, G2-like matched-gate Range→s relinearized 4state, 국소 MAP4(기본 joint gate와 동일). Range와 s를 한 번씩만 사용하고 RF 품질·시간 상관을 과학적으로 확인했다고 주장하지 않음.

원인분해: 정확한 과거 measurement/pose_id 시간 정렬; same input controls & initial errors; 상태·Jacobian bias 부호; full 4x4 covariance; gated RF failure count, Heading RMSE, XY RMSE, pose NEES/95 coverage, 4state bias posterior 및 status trace. 동결 원본 관측 생성기에서 truth는 원시 시뮬레이션과 사후 점수에만 사용하며 filter 입력 금지.

실행 전 의무 감사: frozen P0 manifest/blob SHA·선택된 모든 source/input SHA, 독립 P4 parity 근거 및 새 P6 source AST의 truth 누수 확인. 어떤 해당 코드/입력 결함은 실행 차단; LoS/FULL RF에서 기대 가설과 다른 성능 자체는 예외/실패로 감추지 않고 측정값으로 보고. P5의 실패 reference를 성능 순위 근거로 사용하지 않음.

최초 1case/seed 실행 후 감사와 결과 분석. 정상적인 R0 joint/g2 관측이 동작하고 과학적 모순이 없으면 7case/3seed 전체로 확장할 수 있지만, 본 계약 자체가 전체 결과를 미리 PASS로 승인하는 것은 아님.
