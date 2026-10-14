# D2: P2 재개 후 두 번째 수치 실패의 원인 진단

P0 16/P1 8/R1 5 검사는 다시 PASS했으나, run 38518908286의 MAP3/straight/bias0/trial0/6.0s에서 LINE_SEARCH_FAILED. 원 4.5s를 지나 6.0s까지 진행했다. 완전 paired trial은 0이며 bias 효능은 미평가다.

가설 D2-C: R1의 최적점 인근 보호 조건 중 GN 곡률과 실제 gradient 변화의 5% 일치 조건 또는 terminal-only 조건이 필요 이상으로 제한적이라 유효한 감소 스텝을 막는다. 가설 D2-F: 직접 비용 차의 반올림이 계속 문제다. 대안은 잘못된 Jacobian, 실제 나쁜 곡률, 높은 gradient 계산 noise, 다른 국소해다. 이 가설들은 아직 결론이 아니다.

고정된 원 4.5s와 새 6.0s 스냅샷만 GitHub cloud에서 평가한다. R1 재현, 저장 iterate의 GN step/기울기/정확 Hessian 비교, float 상수를 그대로 승격한 80자리 독립 목적함수 감소, independent SciPy TRF/dogbox/LM 및 analytic/numeric Jacobian을 비교한다. SciPy success와 별개로 원 좌표 gradient infinity norm 1e-8로 판정한다. SciPy 기준 최대 500 평가점은 진단용이며 P2의 80회 solver 설정을 바꾸지 않는다.

D2는 고정 입력 진단이다. P2나 RF는 실행하지 않는다. 이후 진단으로 지지된 한 문제 해결 trial R2를 설계하여 회귀검증→동일 P2로 검증한다. R2에서도 다시 막히면 멈춘다. 최초/두 번째 실패, 목적함수/R/Q/P2_SPEC/seed는 보존한다.
