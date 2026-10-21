# Δs의 ranging 개선 효과 확인 (필터 없음, 2026-10-21)
range 측정 오차 \(e_r=r-h_r(\mathrm{GT})\)에서 평균 보정을 뺀 잔차. 모델은 route-heldout(다른 두 route로 학습): POWER1 μ_r, Δs만(Ridge), 기존 특징만(Ridge/HGB), 기존 특징+Δs(Ridge/HGB). 라벨 변형: 순수 다중경로 range 편향 \(d^{mp}_r=r^{Full}-r^{LoS}\).
지표: pose RMS, 중앙값, 1 m 구간 평균의 RMS(저주파), 공간 0.4 m block bootstrap 2000회 95% CI.
핵심 결과(e_r, HGB): 기존+Δs / 기존 = 0.89–0.96, CI 전체 <1이 6/7 (R2 B만 0.84–1.01). 절대값으로 0.4–0.9 cm 추가 감소. Δs 단독/POWER1 = 0.88–1.19(단독으로는 불충분). 기존+Δs(HGB)/POWER1 = 0.56–0.81 (6/7 CI<1).
