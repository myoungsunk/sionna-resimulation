# heading 민감도별 분석 — 왜 고민감도에서는 Δs가, 저민감도에서는 POWER가 나은가 (실행 전 고정, 2026-10-21)

## 정의
- heading 민감도: \(g=\partial h_s/\partial\psi\) (SourceFFD Jacobian, GT pose). 위치 민감도: \(\nabla_{xy}s=\partial h_s/\partial(x,y)\). range 기울기 \(\nabla_{xy}r\). 모두 GT에서 계산(분석용; 온라인에서는 추정 상태의 H로 대체).
- 평균모델: POWER1(OOF), LIN(Ridge Δs+전력), HGB(기존 특징+Δs) — 방법 A와 같은 route-heldout 적합.
- 잔차: \(r_s=e_s-\hat\mu_s\), \(r_r=e_r-\hat\mu_r^{POWER1}\).

## 분석
A. \(|g|\) 층화(전 case 합친 사분위): 층별 \(r_s\) RMS, heading 환산 \(|r_s/g|\) 중앙값(유효층), 위치 환산 \(|r_s|/|\nabla_{xy}s|\) 중앙값.
B. 정보 기하(case별): \(|g|\) 중앙값, \(|\nabla_{xy}s|\) 중앙값, 편파 Fisher 정보 중 heading 몫 \(\sum g^2/(\sum g^2+\sum|\nabla_{xy}s|^2\cdot(1\,\mathrm m/1\,\mathrm{rad})^2)\), range 대비 편파의 위치 정보비 \(\sum|\nabla_{xy}s|^2/V_s\ /\ \sum 1/V_r\).
C. 구간 결합 WLS(동역학 없는 필터 정보 구조): x 방향 1 m 구간마다 미지수 \([\delta x,\delta y,\delta\psi]\), 관측행 range \((\nabla_{xy}r, r_r, V_r)\)와 편파 \((\nabla_{xy}s, g, r_s, V_s)\), 약한 사전정보 diag(0.5 m, 0.5 m, 10°)⁻². 구간별 \(\delta\psi,\delta xy\)의 case별 RMS를 세 평균모델로 비교 → 재귀에서 본 패턴(R2·R5 B에서 A 악화)을 정적 정보 구조가 재현하는가.
D. 평균 변화의 유도 이동: \(\Delta\mu=\hat\mu_s^{A}-\hat\mu_s^{POWER1}\)만 넣었을 때 C의 WLS가 내는 \(\delta\psi,\delta xy\) (평균 교체가 상태를 어느 방향으로 미는가), corr(Δμ, g), corr(Δμ, \(\nabla_{xy}s\) 크기).

해석: 저민감도 case에서 편파 정보가 주로 위치 쪽이고(B), 평균 변화가 위치를 체계적으로 민다면(D), "편파 잔차는 줄었는데 heading·xy가 나빠지는" 재귀 결과가 xy–ψ 결합으로 설명된다.
