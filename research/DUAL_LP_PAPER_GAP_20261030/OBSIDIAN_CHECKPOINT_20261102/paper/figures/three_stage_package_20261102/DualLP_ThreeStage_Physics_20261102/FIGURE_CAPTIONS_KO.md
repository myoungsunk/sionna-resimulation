# 논문 본문에 직접 사용할 수 있는 그림 캡션 및 서사

## Main Figure A — 물리 관측의 생성과 다중경로 왜곡

**추천 삽입:** `F03_RAW_MULTIPATH_POLARIZATION_TIME.png` (주행 전체), `F13_YAW_DEPENDENT_DUAL_LP_PHYSICS.png` (입사·상대 방향), `F10_MAX_DISTORTION_PORT_POWER_EXAMPLES.png` (부록의 극단 사례).

**캡션 초안:** “동일한 로봇 pose와 안테나 FFD를 기준으로 직접경로 LoS 채널과 반사경로를 포함한 Full 채널에서 추출한 두 직교 수신 포트의 signed 편파비. 공통 first-path 검출 규칙을 적용하였으며, Full−LoS 차이와 검출 tap 전환 구간을 함께 나타냈다. 이 비교는 물리 채널 관측의 변화이고 상태 추정 개선량을 표시한 것은 아니다.”

**표:** `PHYSICAL_LOS_FULL_PACKET_3136.csv`, `YAW_BIN_PHYSICAL_SIGNATURES.csv`.

**근거가 되는 결과:** 
dt≥30, Full−LoS s의 RMS는 R2-B 0.1129, R4-B 0.1174, R5-B 0.0949. Full/LoS 첫 tap 불일치율은 26.30%, 34.63%, 29.33%다. 물리 간섭이 `s` 차이로 나타날 수 있음을 직접 보여주지만, 특정 ray 하나의 기여로 환원해서는 안 된다.

## Main Figure B — 물리 민감도와 관측 왜곡은 기하·거리 조건에 따른다

**추천 삽입:** `F04_RANGE_CONDITIONED_PHYSICS.png`, `F11_PHYSICAL_SENSITIVITY_VS_FILTER_GAIN.png`.

**캡션 초안:** “앵커 수평거리 조건별 Full−LoS 편파 잔차 RMS, 공통 first-path tap 선택 변화율 및 직접경로 기반 Heading Jacobian의 조건부 통계. Heading 민감도가 존재한다는 사실은 실제 관측오차가 작거나 EKF에 높은 신뢰도를 부여해도 된다는 충분조건이 아니다. 별도의 동일 BB-prior shadow 계산에서는 편파 추가분산에 따른 Kalman-gain 축소를 확인하였다.”

**표:** `DISTANCE_BINS_PHYSICAL.csv`, `MATCHED_PRIOR_POLARIZATION_GAIN_12.csv`, `PHYSICAL_SIGNATURES_3_ROUTES.csv`.

**주의:** 민감도는 true-pose FFD이고 gain은 BB-prior fixed-accepted 표본이다. 두 통계를 동일 분모의 원인·결과로 나누거나 곱하지 않는다.

## Main Figure C — 관측 특성 기반 보정 후 무엇이 실제 개선되었는가?

**추천 삽입:** `F01_THREE_STAGE_B0_PERFORMANCE.png`, `F02_THREE_STAGE_12_CONDITIONS.png`, `F12_DISTANCE_CONDITIONED_3_STAGE_PERFORMANCE.png`.

**캡션 초안:** “동일 원 RF 경로·모션 입력·초기 상태에 대한 탐색적 Direct LoS replay, 기존 Full RF 기반 보정 기준선 및 제안된 Range 평균 교체+편파 추가분산 모델의 Heading/XY RMSE. Direct LoS는 기존 R과 μ=0을 사용하는 추가 탐색적 반사실이므로 Full의 기존 RF-trained 평균보정을 사용하는 두 arm과 정확히 동일한 평균모형 비교는 아니다. 동일 평균을 고정한 LoS 통제군을 부록에 별도로 제공한다.”

**표:** `THREE_STAGE_COMPARISON_12_BIASES.csv`, `DISTANCE_BIN_PERFORMANCE_B0.csv`, `LOS_COUNTERFACTUAL_24.csv`.

**주요 결론:** R5-B의 Heading은 B0 LoS 0.215° → Full BB 1.073° → MB 0.643°이며, XY는 2.10 → 8.69 → 4.46cm. R4-B는 LoS 0.303° → Full BB 1.442° → MB 1.431°, XY 5.91 → 8.54 → 9.43cm로, 모든 경로의 위치 성능이 회복되지는 않는다.

## Mechanism Figure D — 왜 같은 물리 민감도가 같은 성능을 보장하지 않는가?

**추천 삽입:** `F05_RANGE_MEAN_ERROR_DECOMPOSITION.png`, `F06_LOCAL_VS_RECURSIVE_EFFECT.png`, `F07_TIME_ALIGNED_PHYSICS_AND_HEADING.png`, `F08_TEMPORAL_CORRELATION_AND_TRAVEL.png`.

**캡션 초안:** “동일 BASE 수용집합의 Range 잔차 평균·RMS, 동일 BB-prior에서 편파 추가분산이 만드는 국소 Heading 손실 변화, 자기 gate를 포함하는 전체 재귀 RMSE의 비교. 동일-prior 즉시 손실과 최종 성능은 상반될 수 있으며, 이는 매 packet의 가중치 감소가 곧바로 추정오차 감소를 의미하지 않음을 보여준다. 시간순 잔차 ACF와 주행거리 변환은 잔차 지속성의 진단이지 시간·공간 오차의 독립적 분해가 아니다.”

**표:** `RANGE_ERROR_SAME_FIXED_MASK_B0.csv`, `LOCAL_VS_RECURSIVE_HEADING_12.csv`, `POLARIZATION_ACF_TIME_AND_TRAVEL.csv`, `TIME_RESOLVED_*.csv`.

**추가 주의:** V4 전체 누적인과 분해 없이 “특정 2초 구간이 전체 RMSE 개선의 n%를 만들었다”라고 주장하지 않는다.

## Supplementary S — LoS 평균모형 대조

**그림:** `F09_LOS_MEAN_CONTROL_AND_CAUSAL_BOUNDARY.png`.

**캡션 초안:** “같은 LoS 채널에 직접경로에 적합한 무보정 평균과 과거 Full RF에서 학습한 평균을 각각 적용했을 때의 4상태 EKF 성능. LoS에 Full RF용 평균을 적용하면 정확도가 악화할 수 있으므로, LoS(μ=0)→Full BB 비교는 물리 채널 차이뿐 아니라 평균모형 적합성도 다름을 명시한다.”

## 논문 본문 권장 배치

1. **물리 관측:** Figure A와 B의 첫 두 물리 지표, signed 편파비 및 h/J 설명.
2. **물리 관측 기반 모델:** Range 평균 교체 전후 F05, gain 대응 F11, 직접 이득과 재귀 이득 F06.
3. **결과:** F01과 F02, 거리별 성능 F12, R4 반례를 같은 척도로 제시. F07·F08은 필요에 따라 보충자료.

### 금지할 주장

- 직접경로 μ=0과 기존 Full μ가 다른데, LoS→Full Heading RMSE 차이의 전부를 “다중경로만의 인과효과”로 표현하지 않는다.
- MB_VAR 적용으로 **물리적 편파 방향 민감도 자체가 향상**했다고 주장하지 않는다.
- 12조건을 독립적인 RF scene 12개로 세지 않는다.
- 잔차의 시간 ACF를 독립적인 시간 drift로 단정하지 않는다.
- 선택한 최대 왜곡 구간을 전체 경로를 대표하는 평균 효과로 소개하지 않는다.
