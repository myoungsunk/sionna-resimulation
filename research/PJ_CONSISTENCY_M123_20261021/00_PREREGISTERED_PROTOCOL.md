# 정확도–신뢰도 일관화 EKF 수정(M1–M3) replay + H-A·H-D·H-E 판정 — 사전등록 (2026-10-21)

결과를 보기 전에 등록한다. 입력: run 39376076166의 불변 산출물(OOF_PARAMETERS, OBSERVATION_FEATURES_LABELS, TRACE), 동일 SourceFFD, 동일 Sensor-v2 seed0 제어. 새 RF 학습/재적합 없음.

## 목표
현재: 정확도는 높고 신뢰도는 낮다(heading NEES≫1, coverage≪95%). 목표는 두 지표가 같은 양상(NEES≈1, coverage≈95%)이 되게 하는 것이고, 정확도 비악화를 조건, 동시 개선을 상위 목표로 둔다.

## 수정안 (확정 사항 F1–F7에서 도출)
- M1: 평균 POWER1, 분산 POWER의 대각, \(C_{rs}=0\) (= 기존 POWER_DIAG).
- M2: gate는 패킷 \(R\)로, 업데이트는 \(R^{\rm eff}\)로. \(\nu^\top(HPH^\top+R)^{-1}\nu\le\chi^2_2(.99)\); \(K=PH^\top(HPH^\top+R^{\rm eff})^{-1}\); Joseph \(P^+=(I-KH)P(I-KH)^\top+KR^{\rm eff}K^\top\). \(R^{\rm eff}=\mathrm{diag}(\eta_rV_r,\eta_sV_s)\), \(\eta\)는 q 비의존 전역 상수.
- M3: bias 행 s-열 이득 축소 \(K_{b,s}\leftarrow\kappa K_{b,s}\) (Joseph 유지 → P는 사용한 이득에 대해 일관).
- 계열: S_ONLY(\(\eta_r=1,\eta_s=\eta\)), COMMON(\(\eta_r=\eta_s=\eta\)), MU_S0(S_ONLY + \(\hat\mu_s=0\); H-E 조건부 계열).
- 격자: \(\eta\in\{1,1.5,2,3,4,6,8,12,16,24\}\), \(\kappa\in\{1,0.5,0\}\) → 90 arms + 기준 REF_POWER1, REF_JOINT4.
- 조건: 7 case × {Full B0, Full L2, LoS B0}; 평가 t≥30 s.

## 선택 규칙 (held route 결과를 보지 않음)
held route H마다 train case = 다른 두 route의 case, Full B0·L2.
1. 각 (계열, κ)에서 \(\eta^\star=\arg\min_\eta \mathrm{median}_{\rm train}|\ln \mathrm{NEES}_\psi|\).
2. 최종 M = (S_ONLY 또는 COMMON, κ, η*) 중 train median heading95 ∈[0.90,0.99]인 것 가운데 train median RMSE비(대 POWER_DIAG) 최소. 없으면 median |ln NEES| 최소.
3. MU_S0 계열도 같은 방식으로 M_E를 선택하되, H-E가 PASS일 때만 채택 후보.
한계: train route replay의 OOF 파라미터 학습에는 held route가 포함되어 있어 약한 간접 누설이 있다. held route의 RF 레이블은 η/κ 선택에 직접 쓰지 않는다.

## 성공 기준 (held route, Full 14 case-bias, 대 POWER_DIAG)
- S1 일관성: \(|\ln\mathrm{NEES}_M|<|\ln\mathrm{NEES}_{PD}|\) 이 ≥10/14, median heading95 ∈[0.85,0.99].
- S2 정확도 비악화: median RMSE비 ≤1.00, >10% 악화 ≤2/14.
- S3 동시 개선: S1 ∧ S2 ∧ RMSE 개선 ≥8/14.
- S4 LoS 보존: LoS B0 RMSE비 ≤1.10 이 ≥6/7.
- 보고: POWER1 대비 동일 지표, L2 bias RMSE, η*·κ 선택값, 고정 η*에서 κ=0 대 1의 bias RMSE비.
- QA: S_ONLY η=1 κ=1 = POWER_DIAG, REF_POWER1, REF_JOINT4가 기존 점수를 재현(|ΔRMSE|<1e-9, heading95 차 <1e-12).

## 가설 판정 (Full B0, 기존 trace; 학습 없음)
- H-A 이득–잔차 정렬: \(k_k=a_kK_{\psi s,k}\)(기존 trace prior에서 재계산), \(d_k\)=u_s의 2 s 이동평균. \(\rho_A\)=Spearman(\(k\), \(|d|\)), t≥30. PASS: (i) \(\rho_A\)(SEP_BIN) > \(\rho_A\)(POWER_DIAG)가 ≥5/7 case, (ii) SEP_BIN의 \(V_s\) 최저 tertile이 평균 \(|d|\) 최대인 case ≥5/7. 보고: case별 \(\Delta\rho_A\)와 D1 ln(ACT/PHASE) 차이의 Spearman.
- H-D 공간 기원: whitened \(u_s\)(POWER_DIAG), 30 s 비중첩 block, block 평균 속도 v(>0.02 m/s만). 검정 가능 조건: block 속도 P90/P10 ≥1.5, 아니면 "기존 데이터로 검정 불가". PASS: pooled Spearman(τ_block, 1/v) ≥0.3 ∧ case 수준 CV(\(\ell_c=\bar v\tau\)) < CV(τ). 보고: block |ω|와의 Spearman.
- H-E 부호 불충분: \(e_s\)의 2 s 이동평균 \(e^{LF}\), 평균모델의 이동평균 \(\hat\mu^{LF}\). \(R^2_{nc}=1-\overline{(e^{LF}-\hat\mu^{LF})^2}/\overline{(e^{LF})^2}\). PASS: POWER1, SEP_BIN 모두 \(R^2_{nc}\le0.10\)인 case ≥5/7. 탐색 보고: 가용 특징량과 \(e^{LF}\)의 Spearman 상위.

결과를 본 뒤 기준·격자·선택 규칙 변경 금지. 추가 분석은 별도 표기.
