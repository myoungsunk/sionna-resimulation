# Innovation 기반 적응형 COMMON inflation — 사전등록 (2026-10-21)

결과를 보기 전에 등록한다. 입력은 이전 run과 동일(run 39376076166 불변 산출물, SourceFFD, Sensor-v2 seed0). RF 재학습 없음.

## 1. 왜 이 실험을 하는가 (이전 결과에서의 연결)
- D1: heading 오차는 저주파 편파 편향의 선형 응답이고, 측정기인 오차는 필터 신념의 ACT/SHUF배(case별 1.9–11.3, 중앙값 4.6)이다. 원인은 연속 패킷이 같은 편향을 공유하는데 필터가 독립으로 취급하는 것.
- M1–M3: \(R^{\rm eff}=\eta R\)(COMMON, range·편파 동일 배율)은 range/편파 상대가중을 유지한 채 측정 대 예측 대역폭만 낮춰 정확도와 신뢰도를 함께 개선했다(route-heldout B0 7/7). 그러나 필요한 η가 case마다 다르고(R4 B는 η=2에서 NEES 8.6, R2는 η=24에서 0.1–0.9), η가 너무 크면 gyro bias 학습이 느려져 L2가 악화된다.
- 따라서 η를 상수가 아니라 온라인으로, case/구간마다 정한다. GT 없이 쓸 수 있는 신호가 innovation이다. 모델이 맞으면 Kalman innovation은 시간적으로 white이므로, 그 자기상관은 필터가 무시한 비대각(시간상관) 항을 직접 측정한다.

## 2. 구현 (모든 arm 공통)
- 평균 POWER1, 패킷 분산 POWER 대각(\(C_{rs}=0\)), κ=1(bias 이득 축소 없음).
- gate: \(\nu^\top(HPH^\top+R)^{-1}\nu\le\chi^2_2(.99)\) (패킷 R).
- update: \(K=PH^\top(HPH^\top+\eta_kR)^{-1}\), Joseph 공분산 \(P^+=(I-KH)P(I-KH)^\top+K\eta_kRK^\top\).

## 3. 적응 추정기 (인과적, GT 미사용)
1. whitened innovation \(\tilde\nu_k=L_k^{-1}\nu_k\), \(L_kL_k^\top=HP^-H^\top+\eta_kR\) (필터 자신의 innovation 공분산).
2. gate 통과 패킷만 최근 W=150개(30 s) buffer에 저장.
3. \(\hat\rho(\tau)=\dfrac{\frac{1}{n-\tau}\sum_i\tilde\nu_i^\top\tilde\nu_{i-\tau}}{\frac1n\sum_i\tilde\nu_i^\top\tilde\nu_i}\), τ=1..L, L=50(10 s). (D1과 같은 비중심 정의)
4. \(\hat\eta^{\rm raw}=1+2\sum_{\tau=1}^{L}\big(1-\tfrac{\tau}{L+1}\big)\hat\rho(\tau)\) (Bartlett 가중; 잡음 억제)
5. \(\eta_{k+1}=\mathrm{clip}\big(\eta_k+\alpha(\hat\eta^{\rm raw}-\eta_k),\,1,\,\eta_{\max}\big)\), α=Δ/10 s=0.02. buffer ≥L+10 전까지 η=1.
W, L, α는 D1의 상관시간 1.5–11.6 s에서 정함: L은 최대 상관시간을 덮고, W는 L의 3배, α는 10 s 시상수.

**feedback 위험:** η가 크면 필터가 편향을 덜 추종하여 innovation에 편향이 더 남고, \(\hat\eta^{\rm raw}\)가 커질 수 있다(양의 feedback). 이를 아래 진단 D-F로 직접 측정한다.

## 4. 상한 η_max (held route를 보지 않음)
- 1차 규칙 MAX: train route case들의 D1 ACT/SHUF(POWER_DIAG, Full B0) 최대값. 근거: 학습 데이터에서 측정된 가장 큰 시간상관 배율을 넘는 η는 측정 구조상 근거가 없다. 값: R2 held 11.33, R4 held 5.70, R5 held 11.33.
- 보수 규칙 MED: 같은 집합의 중앙값. R2 2.98, R4 3.09, R5 3.37.
- 검토 후 기각한 규칙: "train L2 bias비 ≤1.0인 최대 η"는 R4에서 η=1.5의 1.4% 악화만으로 η_max=1(적응 불가)이 되어, 잡음 수준 차이가 결정을 좌우하므로 쓰지 않는다.
- 주의: D1 ACT/SHUF는 GT 기반 진단값이며 같은 복도의 데이터다. 상한 설정에만 쓰고, 온라인 추정에는 쓰지 않는다.

## 5. Arms (κ=1, COMMON)
| arm | 내용 |
|--|--|
| FIX_1 | η=1 (= POWER_DIAG 기준) |
| FIX_2, FIX_3, FIX_4, FIX_6, FIX_8 | 고정 η (feedback 곡선용, open-loop \(\hat\eta^{\rm raw}\) 기록) |
| FIX_MED | 고정 η = MED 규칙값 (적응 없는 상수 대조군) |
| ADAPT_RS_MAX | 적응, r·s 두 채널, η_max=MAX |
| ADAPT_S_MAX | 적응, s 채널만으로 \(\hat\rho\), η_max=MAX |
| ADAPT_RS_MED | 적응, r·s, η_max=MED |
| ADAPT_RS_NOCAP | 적응, r·s, η_max=24 (feedback 폭주 진단용) |
| REF_POWER1 | 원래 POWER1 (\(C_{rs}\) 포함) |
조건: 7 case × {Full B0, Full L2, LoS B0}, 평가 t≥30 s.

## 6. 보고 규칙
모든 지표는 기준선 통과 여부와 별도로 크기(중앙값, case별 값, 개선/악화 개수)를 그대로 보고한다. 아래 목표 수준은 해석의 참조점이며, 미달이라도 개선 크기와 원인을 함께 서술한다.
- Q1 일관성: Full 14의 median heading NEES(목표 0.67–1.5), median coverage(목표 ≥0.85), |ln NEES|가 FIX_1보다 작은 개수.
- Q2 정확도: median RMSE비(대 FIX_1, 목표 ≤1.0), 개선 개수, >10% 악화 개수(목표 ≤2).
- Q3 L2 gyro bias RMSE비 median.
- Q4 LoS: RMSE비 ≤1.10 개수(목표 ≥6/7).
- Q5 적응 대 상수: ADAPT_RS_MAX가 FIX_MED보다 |ln NEES| 작고 RMSE 5% 이내인 case-bias 수.
- QA: FIX_1, REF_POWER1이 기존 점수 재현(|ΔRMSE|<1e-9).

## 7. 진단
- D-F feedback 곡선: 고정 arm(η=1,2,3,4,6,8)에서 open-loop \(\overline{\hat\eta^{\rm raw}}\)(t≥30) 대 η. 기울기 \(d\hat\eta/d\eta\)<1이면 고정점 안정, ≥1이면 폭주 경향.
- D-V 추정기 타당성: FIX_1의 \(\overline{\hat\eta^{\rm raw}}\)와 case별 D1 ACT/SHUF의 Spearman(7 case).
- D-T 궤적: 적응 arm의 η_k 시계열(CSV 저장), case별 평균/최소/최대, case별 "NEES≈1이 되는 고정 η"(이전 92-arm 결과의 기술값)와 비교.
