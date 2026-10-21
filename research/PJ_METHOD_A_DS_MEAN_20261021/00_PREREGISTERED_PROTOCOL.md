# 방법 A — Δs 조건부 편파 평균 \(\hat\mu_s=f(\Delta s,q)\) (사전등록, 2026-10-21)

결과를 보기 전에 등록한다. 상태 \(x=[x,y,\psi,b_g]\), 관측 \(z=[r,s]\), EKF 구조, gate(\(\chi^2_2(.99)\), 패킷 R), η=1, κ=1은 그대로. range 평균·분산은 POWER1 그대로, \(C_{rs}=0\). **바뀌는 것은 편파 평균 \(\hat\mu_s\)(와 일부 arm에서 \(V_s\))뿐.**

## 1. 왜
usage map: 편파 편향 \(e_s\)의 held-route 설명력이 POWER1 \(\hat\mu_s\)는 pose 0.02 / 저주파 0.03인데, 부호 Δs는 선형 0.41 / 0.30, 기존 특징+Δs 비선형은 0.52 / 0.58. heading 오차 \(\delta\psi\approx\sum_kc_{k,s}(e_{s,k}-\hat\mu_{s,k})\)의 입력이 줄어드는지 재귀에서 확인한다.

## 2. 구현
온라인 innovation: \(\nu_s=s-h_s(\hat x^-)-\hat\mu_s(\Delta s_k,q_k)\). Δs는 현재 패킷 CIR에서 계산(GT 불필요, 인과적). Δs 추출은 Step 1과 동일(o=±1,±2,±4,±8).

평균 모델 (held route H마다 다른 두 route의 Full pose로 학습, 라벨 \(e_s=s-h_s(\mathrm{GT})\)):
- LIN: 표준화 Ridge(α=1), 입력 [Δs 8개, log_fp_power].
- DS_LIN: 표준화 Ridge(α=1), 입력 Δs 8개.
- HGB: HistGradientBoosting(max_iter=200, lr=0.05, max_leaf_nodes=15, l2=1.0, random_state=0), 입력 기존 특징 16개 + Δs 8개.

분산 재추정(V_s|Δs): train 두 route 사이 교차적합으로 OOF 잔차를 만든다(한 route로 학습→다른 route 예측). train log_fp_power tertile별 잔차 분산을 global로 \(n/(n+100)\) 수축, floor 0.1·R0_s. held pose는 자기 tertile 값. (OOF는 한 route로만 학습하므로 보수적)

## 3. Arms
| arm | \(\hat\mu_s\) | \(V_s\) |
|--|--|--|
| BASE | POWER1 | POWER (= POWER_DIAG) |
| REF_POWER1 | POWER1 | POWER1 (\(C_{rs}\) 포함) |
| A_LIN_PV | LIN | POWER (평균 효과만) |
| A_LIN | LIN | 재추정 |
| A_HGB_PV | HGB | POWER (평균 효과만) |
| A_HGB | HGB | 재추정 |
| A_DS_LIN | DS_LIN | 재추정 |
조건 7 case × {Full B0, Full L2, LoS B0}. LoS는 LoS 패킷의 Δs·특징에 Full 학습 모델을 적용(진단용).

## 4. 보고 (크기로; 참조 수준은 해석용)
- 측정 수준: held-route \(e_s\) 설명력 \(R^2_{nc}\) (pose, timeline 저주파), 패킷 s95(\(V_s\) calibration).
- 재귀 Full 14: median heading RMSE비(대 BASE; 참조 ≤1.0), 개선/>10%악화/최악, median NEES·coverage, L2 bias비, xy비. LoS는 진단.
- 귀속: _PV 대 재추정 arm 차이 = 분산 효과, BASE 대 _PV 차이 = 평균 효과.
- QA: BASE, REF_POWER1 기존 점수 재현(|ΔRMSE|<1e-9).
