# G1-DIAG-002 실행 기록

- 역할 IMPLEMENTER
- 분기 research/g1-sweep-heading-floor-spec-20261113
- 사양 2068954c07770cffee1a8745e53e0383c5ef8c96
- 기준선 d7a35296b287fe46d9da0741c950bdfd51bcf14e
- Q1 42fe9c7 (CSV Git blob db19ca2d71a7f5f4d7eb8df9d6a0d4ea5274bccd)
- 연구 지침 RESEARCH-GOVERNANCE-v1, COMMON a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb, IMPLEMENTER 2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da

## 실행·보고 범위

K0 → K1/K2 → K7/K8 → K3–K6. K0에서 coverage mask나 규정된 비교 항목이 다르면 중단한다. 후속 필터 진단 전에는 더 강한 점검인 K0 상태 배열 50방문 전수 일치도 확인한다. K9/K10과 Step 3는 실행 범위 밖이다. S2′ 판정은 STOP이다.

K0는 동결 필터와 입력을 그대로 방문 1–50에 적용하는 nominal 전용 드라이버로 실행한다. 부트스트랩 경로 배열도 동결 버전과 대조하되 K0에서 해당 경로의 필터는 돌리지 않는다. 최초 사전 점검에 사용한 primary 시점 코드 목록에서 seal_s2.py 하나가 달랐다. 결과 패키징을 맡은 이 파일은 배포된 최종 매니페스트와 일치하며, 해당 목록의 다른 파일은 실행 시점 해시와도 일치했다. 최종 매니페스트가 고정한 실행 코드 전체를 검사하고 실행한다.

K7/K8에서는 Q1의 full 관측을 수치로 다시 확인한다. K7은 같은 seed로 시작한 복소 잡음을 full과 LoS에 사용하고, noise scale과 열잡음 분산 보정은 고정한다. K8은 공통 LoS tap에서 두 채널을 비교하고 full 검출 tap 이동을 따로 집계한다.

K3–K6은 같은 10방문에서 대비한다. NR-seq는 S2′가 쓰던 차선(y 부호) 각각에서 x 순서 연속 10개를 양방향으로 열거한다. 지원되는 길이 10 창이 없는 case는 미적용이다. NR 경로는 물리 station 중복을 허용하지 않는다. R4 원본 10개 집합에서는 S2′ 복원추출 후 유일한 station 수가 대부분 10개보다 작으므로 NR에 대한 station-cluster CI는 산출하지 않는다. 조건부 고정 bank 경로 구간을 별도로 표시한다. S2 경로 arm의 CI는 고정 bootstrap 첫 200개를 쓴다.

K4는 Q1과 일치하는 station 평균 오차/평균 표준편차 비의 제곱을 station 간 평균한다. κ는 E1 측정 분산에 적용하고 Markov 상태의 고정 분산은 유지한다. K5는 후보 선택 후 혁신의 관측 heading에서 μ를 뺀다. K6의 순수 갱신 생략 대비는 편향·스케일 oracle을 공유하는 OB와 SKIP이다. K6-10과 SKIP 사이에는 개입 두 가지가 달라진다.

K7의 §4 분산비 구간과 K8의 §4 상관 동시 기준은 원문 그대로 집계한다. 원인 해석에는 K7의 LoS 잔차 편향과 짝 공분산, K8의 tap 이동과 검출 및 기하 지원 범위를 같이 보고한다. 여기서 나온 수치는 DIAGNOSTIC_ONLY다.
