# T9 q와 거리 교란 분리

TECHNICAL: TECHNICAL_PASS; 거리 가설: NOT_ESTABLISHED; Δq: NOT_ESTABLISHED.

모든 양의 POWER 이득 조건에서 거리 arm 회수율 ≥80%를 요구했다. 비양수·미소 이득은 분모로 사용하지 않는다. Δq 기본 feature 채택은 후보 판정이며 자동 변경하지 않는다. 학습은 원래 route-heldout/site-disjoint이며 추론 특징은 prior와 실제 RF q뿐이다. 기대 LoS q의 근사 오차는 TRAIN_PARAMS.json에 보존한다.

## 주장하지 않는 것

거리만이 유일 원인이라는 주장, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.

실행 39359824661 / artifact 12237051901. 72행 재귀 표를 보존했다. 양의 POWER 이득 10개 조건의 합계 기준 거리 회수율은 1.242830이지만, R2 A M45 B0에서는 q 이득 +0.023673°에 대해 거리 arm 이득 −0.597351°로 조건별 80% 기준을 실패했다. 합계만으로 거리 주성분을 확정하지 않으며 Δq를 기본 feature로 채택하지 않는다.
