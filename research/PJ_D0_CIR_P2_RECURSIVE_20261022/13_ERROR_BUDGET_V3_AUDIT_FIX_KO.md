# 오차 예산 v3 — 코드 감사 반영 (2026-10-23)

감사 대상: commit ca1f8b0의 `p2_ebudget2.py`. run 39947618558의 eb2 결과는 v2 그대로 남기고, 아래 수정은 v3(`p2_ebudget3.py`, workflow `p2-eb3.yml`)로 따로 실행한다. 같은 run의 Monte Carlo는 감사 항목과 무관하므로 유지한다.

| 지적 | 판단 | v3 조치 |
|---|---|---|
| A. `C_deg2`는 비중심 이차모멘트 M_ij | 맞음 | M(MSE 분해용), 중심화 C, 원천별 평균을 모두 출력. 몫은 MSE 몫(share_of_mse)과 분산 몫(share_of_var), 평균 부분을 분리 |
| B. w²/q는 평균제곱비 | 맞음 | 평균, 분산/q, 평균제곱/q, 평균²/q를 각각 출력. gyro 평균은 등가 bias(°/s)로도 |
| 3. `info_factor`는 EKF 정보 과대평가 배수가 아님, gate 거부 패킷 포함 | 맞음 | 커널 기반 F_ψ,corr = Σ_kl W_k Γ(k,l) W_l / Σ_k W_k² Γ(k,k). gate는 W(K=0)로 반영. Γ는 정상성 가정 ACF로 추정(원 잔차와 10 s 이동평균 제거 잔차), 편파·range 각각. AR(1) 검사: ρ=0.5에서 3.29/3.16(이론 3.0), ρ=0.8에서 8.3/8.9(이론 9.0) |
| 4. 교차 전파 입력에 arm 고유 r_pred·r_meas·c2 포함 | 맞음 | 외생 입력(initial, odom, gyro, range, c1)만의 교차 전파 추가. 결과는 "고정 선형화 아래 회계 분해"로만 기술 |
| 5. 정적 WLS 비교 미구현 | 맞음(계획 누락) | 같은 평가 시점에서 accept 패킷의 10 s·30 s 창 WLS 가중치 g/R / Σg²/R와 재귀 커널의 크기·부호·c1 예측 heading을 비교. 커널 배열 저장 |
| 6. closure는 항등식 QA일 뿐 | 맞음 | H(SourceFFD 해석 기울기), F·G(전이) 유한차분 검사. r_pred·r_meas 몫은 미설명 성분으로 별도 유지 |
| 7. bias 경로·기억은 재실행이 아닌 선형 반사실, 음수 가능 | 맞음 | 해석 문구 반영(`nobias_linear_heading_rmse_deg`) |
| (추가) 기억 경계 | 버그: t − T가 시작보다 앞서면 전체 오차를 old로 셈 | 0으로 수정 |
| 8. MC는 RF 고정 운동센서·초기화 민감도, 84개 독립 환경 아님 | 맞음 | 보고서에 명시 |
| P2. P⁻, P⁺, NIS, R 저장 | 동의 | 배열과 PATH 표(NEES, accept NIS 평균)에 추가 |
