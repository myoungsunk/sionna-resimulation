# G1-DIAG-002 K9/K10 실행 전 기록

- 상태 DIAGNOSTIC_ONLY, S2′ STOP, Step 3 보류
- 역할 IMPLEMENTER. 기준 사양 2068954c07770cffee1a8745e53e0383c5ef8c96. K0–K8 기준 b070c8685e03133cfe4b846b530181acf66260b8. 실행 전 GitHub head aba234ed47f6028272c4b6de67b704dcddb90e09.
- 지침 RESEARCH-GOVERNANCE-v1. COMMON SHA-256 a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb. IMPLEMENTER SHA-256 2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da.

## K9
- r2.1.0 보정된 DR은 공칭 β=0.482°/visit을 제거한 상태에서 run마다 고정인 평균 0의 잔여 bias와 독립 백색 오차를 공유한다. σ_w=0.40°/visit, E₀=0. σ_β는 사양의 격자 그대로다. G1도 같은 증분 및 해당 σ_w·σ_β를 사용한다.
- S2′ 200개 경로(6 case에 33–34개씩)의 난수와 K3 NR-rand 첫 10개 방문을 재현한다. 같은 station 순열의 나머지 방문을 사용해 정해진 station 수까지 연장한다. K4 oracle은 E1 측정 분산만 바꾼다. 누적 RMSE와 구분해 각 방문의 RMSE를 사용한다.
- 최소 N에서 DR-cal RMSE > G1 RMSE를 검사한다. 유한 표본으로 계산한 범위는 OBSERVED_STATION_SUPPORT(기존 station 지원 범위 내 모의실험)다. N은 방문 수다. 초과 방문에서는 DR-cal 해석식과 마지막 5개 G1 RMSE 평균을 비교한 EXTRAPOLATED를 별도로 기록한다. 관측 범위에 교차가 있고 뒤에 역전해도 N*는 최초 교차다. 외삽 조건은 관측 교차 여부와 독립적으로 표시한다. §4의 20방문 기준에는 기존 station 지원 범위 내 결과만 들어간다. 서로 다른 horizon은 case 단위로 비교한다.

## K10
- K4에 사용한 station z²를 재집계한다. case별로 비복원 순열 200개를 전 station에서 생성한다. seed는 2026111401이며 K9와 표본 수 및 생성 순서가 다르다. 순열은 관측 station 집합의 조건부 순서 민감도를 나타낸다.
- 사전 IG(3,2), 첫 사후 중앙값 >1.5와 우측 검열을 기록한다. 10방문 이내와 case 전체 horizon을 함께 보인다. 탐색 전용이며 모형 파라미터 채택, 실제 오경보율, 시간적 수렴 보장에 사용하지 않는다.
