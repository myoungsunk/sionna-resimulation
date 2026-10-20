# S3 실행 계약

기존 v2의 17개 Full-only 특징과 POWER 후보 NIS, prior heading 표준편차(rad), P(psi,bg), H(s,psi)를 순서대로 쓴다. 추론 내부량은 정책 자신의 현재 prior에서만 계산한다. 학습·OOF label은 offline GT를 사용하며 온라인 callback에는 GT·미래·route/case·bias·seed 식별자를 전달하지 않는다.

P1은 v2와 동일하게 outer와 label route를 제외하고, label route의 위치와 1e-4 m 이내인 site를 제외한다. site 가중치와 ScalarPower는 변경하지 않는다. TRAIN_FOLDS.json의 순서 있는 case/pose_id key와 hash를 실제 적합 전 확인한다. 모델은 outer별 한 번 학습한다.

OOF 검증 route의 모든 seed·bias·중첩 창을 함께 제외하여 HGB를 학습한다. ROUTE_DEPENDENCIES.csv는 각 HGB 학습행을 생성한 P1이 HGB 검증 route를 사용했는지를 명시한다. 이 OOF는 고정된 v2 prior-label 조건부 HGB 단계 route-heldout OOF다. 상위 P1까지 제외한 전체 pipeline OOF가 아니며, margin에 독립 보정·coverage 보장을 부여하지 않는다. outer fold에는 inner route가 둘뿐이어서 상위 P1까지 추가 제외하면 학습 route가 0개가 된다. P1 구조를 바꾸거나 조용히 검증 route를 재사용하지 않는다.

3개 nonPOWER 행동별 HGB를 고정 설정으로 적합한다. POWER 효용은 정확히 0이므로 학습하지 않는다. OOF 보정 전 예측의 argmax(전부 음수여도 선택)를 R0, INFLATE4, SKIP 순서로 결정한다. 선택된 행동의 max(0,예측-실제)만 모아 numpy linear 80% 분위수를 margin으로 쓴다. 보정 후 선택 집합을 다시 만들지 않는다. 선택이 없으면 delta=null과 UNCALIBRATED_NO_OOF_SELECTION을 저장하고 V3에서 해당 행동을 비활성화한다. 추가 최소 표본 수는 없다.

POLICY_V3는 활성 행동의 예측-margin 최댓값이 엄격히 양수일 때만 전환한다. POLICY_NO_MARGIN은 같은 최종 모델에 margin=0을 적용하며 세 행동 모두 허용한다. 선택 표본 부족 비활성화는 V3의 보수적 보정 규칙이다. 두 정책 모두 정확히 0이면 POWER다. 모델은 재학습하지 않는다.

label은 저장 POWER prior에서 현재 update를 분기하고 다음 패킷부터 POWER로 복귀한다. loss는 현재 시점을 제외한 (t,t+10s] 전체 clock이며 prediction을 중복 적용하지 않는다. 모든 POWER restart의 상태·공분산·gate를 원 baseline과 비교한다. seed는 실제 Sensor-v2 controls 생성에 들어가며 controls hash와 seed0 대비 실제 차이를 기록한다.

평가는 288행이며 주 scope는 전체 motion clock t>=30s다. RF-only는 별도 보조 표다. 단발 행동 label과 매 패킷 정책의 분포·목적함수 차이를 한계로 보고한다. 중첩 창, 동일 RF의 bias/seed, fold 중복을 독립 표본으로 세지 않는다. ALL_OLD의 고유 RF와 비중첩 10초 창 수를 별도 보고한다.

공통 입력·기준선 불일치 시 해당 shard를 중단하고 실패 trace와 누락 분모를 보존한다. NONSPD·비유한 값에 jitter나 PSD projection을 추가하지 않는다. 잘못된 실행은 이전 결과를 보존하고 수정 코드와 재시도 관계를 기록한다. v2의 이벤트 명단과 무효 D4는 S3 dependency가 아니다.

주장하지 않는 것: 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, delta의 coverage 보장, q의 인과적 물리 기전.
