# H3 4단계 동결 R0 사전 검사 — FAIL_CLOSED

3단계 실행·자체 검산을 통과한 뒤, R2_aA_m0의 seed 0에서 무편향 및 gyro_bias Level 0/1/2, LoS B_OLD·Full B_OLD/E1을 검사했다. 평가 시작·중간·마지막 시점의 G0/G1/G2H/G2X/G3를 실행 전에 정한 순서로 비교했다. 기존 RF, LUT, 센서 입력, R0, NIS gate 및 수치 허용치는 유지했다. 학습 RF 공분산 분기는 기존 0.5 m 공간 buffer 실패 때문에 보류했다.

169개 방법·시점 출력 후 다음 검사에서 중단됐다.

- 조건: R2_aA_m0 / gyro_bias Level 2 / seed 0 / LoS / B_OLD.
- 시점: sample 978, 195.6 s.
- 방법: G3, 위치를 적분한 공동 s·Range likelihood의 Heading 주변 posterior.
- 실패: Gauss–Hermite 위치 적분의 마지막 두 차수 41·65 사이 정규화 posterior TV가 0.38706501555739936. 동결 허용치는 0.001이다.
- 실행 exit code: 1. 수치 판정: FAIL_CLOSED.

적분 실패 posterior를 성능 결과로 해석하지 않는다. 앞서 통과한 부분 출력도 전체 비교나 후보 채택을 대신하지 않는다. 추가로 최종 각도 격자에서 인접 적분 차수의 TV를 확인했으며, 검사 기록을 QUADRATURE_CHECKS.csv에 보존했다.

현재 4단계 전체 gate는 통과하지 않았다. 전체 4단계 실행과 재귀 융합은 중단했다. `scientific_PASS=false`를 유지한다. 원본 결과와 실패 증빙을 보존하고 허용치를 늘리지 않는다.

다음 수치 수정 검토는 넓은 위치 prior와 좁은 Range likelihood에서 고정 Gauss–Hermite 적분이 충분한지 확인하는 데 한정한다. 적응형 적분 또는 likelihood에 맞춘 중요도 적분을 별도 검증한 뒤, 동일 입력과 동결 허용치로 다시 검사해야 한다. 이번 실행은 실패 원인이 위 구조라고 확증한 결과는 아니다.
