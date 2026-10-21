# Step 1 — 부호 있는 fp 주변 s 변화량(Δs)이 편파 편향을 관측하는가 (사전등록, 2026-10-21)

결과를 보기 전에 등록한다. 필터 replay 없음. 기존 RF(H_Full, H_LoS, 원본 SHA 검증)와 기존 라벨만 사용.

## 1. 왜 하는가
- D1/M1–M3: heading 오차의 대부분은 저주파 편파 편향 \(d_s\)이고, 남은 문제는 편향의 **부호**다(H-A: 분산은 크기를 맞게 추종, H-E: 평균모델의 저주파 설명력 R² 0.03).
- 기존 특징 s_diff4는 \(|s_{fp}-s_{[fp,fp+4)}|\)로 **절댓값**이고 **fp 뒤쪽만** 본다. 편향 크기와는 7/7 양의 상관(+0.27~+0.57)이지만 부호와는 불일치(−0.07~+0.39).
- 두 경로 근사(위상 간섭 무시): \(s(\tau)\approx(1-w(\tau))s_a+w(\tau)s_b\). 단일 경로면 s는 tap에 무관. 따라서 \(d=s(fp)-s_a=w_0(s_b-s_a)\), \(\Delta s_{+\delta}=s(fp+\delta)-s(fp)=(w_+-w_0)(s_b-s_a)\), 늦은 경로 비중은 τ와 함께 커지므로 **sign(Δs₊) = sign(d)**. leading edge \(s(fp-\delta)\)는 \(s_a\)에 더 가깝다.

## 2. 추출 (features.py와 동일 절차)
Hann window, 4× zero-padding IFFT, 강한 RX 포트 branch, 최대 진폭 30%를 처음 넘는 tap = fp. 각 pose에서 \(s(fp+o)=\frac{P_{+45}-P_{-45}}{P_{+45}+P_{-45}}\), \(o\in\{-8,-4,-2,-1,0,1,2,4,8\}\), 해당 tap 진폭/peak 비 기록. 경계 밖 tap은 결측. QA: 내 \(s(fp)\)가 기존 OBSERVATION 파일의 s_fp와 |차| <1e-9.
\(\Delta s_{o}=s(fp+o)-s(fp)\) (부호 유지). 실제 해상도 ≈4 tap이므로 1차 분석 offset은 ±4, ±1·±2·±8은 보조.

## 3. 라벨
- \(d_{mp}=s^{\rm Full}_{fp}-s^{\rm LoS}_{fp}\) (같은 pose의 Full–LoS; 순수 다중경로 편향, 모델오차 제외).
- \(e_s=s^{\rm Full}_{fp}-h_s(\mathrm{GT})\) (필터가 실제로 보는 오차; 기존 파일).
- \(e_s^{LF}\): timeline 순서 2 s 이동평균.

## 4. 사전등록 지표와 참조 수준 (모든 값은 크기로 보고)
- M1 부호 일치: \(|d_{mp}|>0.02\) 그리고 \(|\Delta s_{+4}|>0.01\)인 pose에서 \(\Pr[\mathrm{sign}(\Delta s_{+4})=\mathrm{sign}(d_{mp})]\). 우연 0.5. 참조: ≥0.65가 ≥5/7 case. \(e_s\)에 대해서도 동일 보고.
- M2 leading edge: \(\Pr[|s(fp-4)-s^{\rm LoS}_{fp}|<|s(fp)-s^{\rm LoS}_{fp}|]\)와 두 RMS. 참조: 비율 ≥0.6, RMS 감소.
- M3 held-route 설명력: train route(다른 두 route, Full)에서 표준화 Ridge(α=1)로 라벨 ~ 부호 Δs 특징 [Δs₋₈,Δs₋₄,Δs₋₂,Δs₋₁,Δs₊₁,Δs₊₂,Δs₊₄,Δs₊₈] 적합 → held route에서
  - pose 수준 \(R^2_{nc}\) (d_mp, e_s),
  - timeline 저주파 \(R^2_{nc}\) (e_s^{LF}, 예측도 2 s 이동평균).
  대조: (i) POWER1 평균 \(\hat\mu_s\) (OOF), (ii) 같은 Ridge에 절댓값 특징만(|Δs| 같은 집합 + s_diff4/8/16, detector_s_span), (iii) 부호+절댓값.
  참조: 부호 모델의 e_s^{LF} R²가 POWER1보다 ≥0.10 높은 case ≥5/7.
- M4 비례 관계 \(d\approx\lambda\Delta s_{+4}\): case별 \(\lambda\)(원점 통과 최소제곱)와 route 간 변동.

## 5. 해석 규칙
M1이 우연 수준이면 두 경로 근사가 이 채널에서 성립하지 않음(위상 간섭 지배)으로 해석하고, 부호 정보를 다른 통계에서 찾아야 한다. M1·M3가 높으면 Step 3(편향 상태 + Δs 관측)의 근거가 된다. 결과를 본 뒤 offset·임계값 변경 금지; 추가 분석은 별도 표기.
