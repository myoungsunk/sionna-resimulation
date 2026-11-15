# G1-MODEL-003 v3 S3 실행 계획

## 입력과 판정 순서

- S0, S1′, S2′, S2-T, S2-F 입력 고정 커밋은 `e9939694027381a36aea26cfc60a98aa53a62f43`이다. 실행 매니페스트에 타임라인과 각 결과의 SHA-256을 기록한다.
- G-T1 A/B/C의 3개 LOAO fold를 사용한다. 학습 앵커 쌍은 BC/AC/AB다. RF 입력은 G-T1의 동결 생산 결과만 연결하고, 원본과 G6 재생성본의 봉인 해시를 전후 확인한다.
- 30 dB O10이 판정 체인이다. O30 30 dB와 O10 20 dB는 보고용이다. 같은 case·경로·SNR에서 두 체인이 같은 thermal draw를 공유한다. 동일 seed·부호·경로의 DR 및 갱신 모델은 같은 운동 입력과 초기 상태를 쓴다.
- S3-R은 R4, R-M, R-MC와 DR을 TEACH→REPEAT, P-B, P-C의 C1–C4에서 실행한다. B0/L0/L1/L2/TB3 두 점, seed 0–39, 양·음 bias를 포함한다. B0의 두 부호는 동일 실행을 같은 seed 안에서 집계한다. B0 초기 heading 오차 0은 별도 보고다.
- S3-R에서 통과 arm이 없으면 `DEV_FAIL_RANGE`을 기록하고 S-V와 S-C만 `DIAGNOSTIC_ONLY`로 실행한다. 통과하면 선택한 거리 모델을 고정하고 S3-J의 12개 후보와 J4/J4+K를 실행한다. S3-J 통과 후보가 생긴 경우에만 전체 G-T1으로 재적합해 동결한다.
- S2-F 영점 RMS 표의 원본을 보존한다. v2 S2-F의 적용 범위에 따라 P-B 수치는 직진 대조로 보고한다. P-B는 integrity와 B0 무해성에 포함하며, S2-F에 따른 나머지 수준의 무해성 및 정확도 판정에서는 제외한다.

## 계산과 집계

- C2 거리 유색 분산의 입력은 고정 K_r와의 중복을 피하도록 앵커 잔여 평균을 분리한 `range_conditional` 적합이다. C3 공간·yaw nugget은 적합에 쓰인 쌍 수로 가중한다. 하한에 닿은 채널은 백색 전이를 사용한다. 상한에 닿은 채널의 선택 후보는 해당 consider 상태를 포함해야 한다.
- v2 초기 공분산과 운동 모델을 유지한다. S3에서는 R4에도 v3 S2′ 통합 백색 분산을 적용한다. S0의 v2 회귀 모드와 독립된 비교다. 거리 gate는 χ²₁ 99%다. Gaussian s는 두 관측을 쓸 수 있을 때 v2 결합 gate와 거리 단독 갱신 경로를 쓴다. s만 남으면 χ²₁ 99%를 쓴다. +T는 사양의 가중 규칙을 쓴다.
- TEACH/REPEAT의 sweep 종료와 이동 구간 중간점을 평가하며 같은 station의 checkpoint 및 REPEAT 재방문을 한 site로 묶는다. P-B/P-C는 동결 C3의 `max(1 m, 2ℓ_d)` 구간을 사용한다. 조합 안에서 site를, 조합 사이에 공통으로 seed를 재표집한다. 부호는 seed와 함께 묶는다. B=2,000이며 조합은 고정한다.
- `contributions`의 `attempted`, `available`, `accepted`는 각 직진(`straight`)·회전(`turn`)·정지(`hold`) 구간의 seed·부호별 packet 수다. restart 시점은 `hold`로 분류한다. `sum_abs_heading_update_rad`는 같은 구간에서 관측 갱신에 의한 절대 heading 변화의 합이다. 시간 전파에 따른 변화는 포함하지 않는다.
- `directional_heading_misses`와 `maximum_continuous_heading_miss_checkpoints`는 조합·경로·phase별로 출력한다. 편파의 미사용률은 gate 기각·유효 기각·사용 불가의 합집합을 사용한다. 거리 전용 arm의 s 지표는 판정에서 제외한다. `m1r_clipped`, `student_weights`, `j_minus_range`는 해당 arm에서 함께 보고한다.
- S2-T의 |Z| > 2 사전 예측과 G-T1의 fold별 포함률을 대조한다. 결과 해석은 mount 0의 이 RT 자료로 한정한다.
