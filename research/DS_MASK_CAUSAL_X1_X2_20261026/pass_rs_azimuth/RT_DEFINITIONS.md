# CUT_RT 実행 정의

2a에서 R2_aA_m45/R4_aA의 rng,tan signed 비율이 0.3 이상이므로 원 계획의 개입 조건을 충족했다. 비교 범위는 주 분석6조건 전체이며 R4_aB는 보조 대조로 함께 계산한다.

- joint gain K[:,0] 중 XY 벡터에서 prior 추정 접선축 투영만 제거한다. K의 편파 열과 range 열의 psi/bg 성분은 유지한다.
- 조정한 K 전체와 원래 joint R로 Joseph 공분산을 계산한다. 순차 갱신으로 바꾸지 않는다.
- PASS는 GT 첫 통과 ±10초 창만, ALL은 전체 시점. 이후 통과는 PASS 개입 대상이 아니다.
- 모든 arm은 A_B 고정, 기존 mu/R/Q. alpha0/1. 모델 h/H 및 P/K 재계산.
- RT_OFF 전6조건이 E1 x/P/prior/Pprior/h/H/K/mu/R/nu/acc와 1e-10 이내 일치해야 RT_CUT 실행.
- 통과 후 gap은 사용자 확정 post 창 평균. heading/beta 분모 최소0.01도, 접선 분모 최소0.1cm를 사용하며 작은 분모는 NA. f_magnitude=1-|G_cut|/|G_base|, f_signed=1-G_cut/G_base, 부호반전 별도 보고. 0.7/0.3 운영기준.
- t>=30 지표도 별도 기술. 개입 결과는 후속 P/K 변화까지 포함하며 유일한 인과 경로로 확정하지 않는다.
