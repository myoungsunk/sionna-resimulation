# T7B 효용 target 정책

TECHNICAL: TECHNICAL_PASS; 과학 판정: NOT_ESTABLISHED.

Nested route-heldout P1 prior 생성과 정책 label 학습을 분리한다. 학습 GT는 offline label에만, 온라인 결정은 실제 RF 특징과 해당 정책의 prior 내부량만 사용한다. 10 s label은 같은 prior에서 현재 행동만 바꾸고 이후 POWER로 계산한다. 단계별 완료는 전체 정책 승인과 다르다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. NO-GO와 오류도 보존한다.
