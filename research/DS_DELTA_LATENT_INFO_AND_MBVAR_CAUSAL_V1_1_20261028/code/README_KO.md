# Δs 잠재 편파 편향: 추가 정보량 실험 및 MB_VAR 미해결 조건 재귀 원인 추적

**버전** `DS_INFO_AND_VAR_TRACE_V1_20261028`  · **코드 계보** `myoungsunk/sionna-resimulation` `16eb9521e19f04fd75bdeb02abd4cc687debb944`의 Stage 7·8 baseline (후손 checkout도 허용)

## 수행 상태와 해석 경계

- **완료:** 코드 작성·Python 문법 검사·7개 합성 단위시험 및 별도 원래 EKF synthetic fixture의 `MB_VAR` gain ledger 회귀시험 **PASS**. 동일 prior 공분산에서 추가 측정의 정보 증가 단조성과, 훈련 제외 route의 무누출도 확인.
- **완료:** `--mode synthetic` 3 route 재현 실행, 결과는 `synthetic_example/`에 포함. 이 결과는 실제 RF 결과가 아님.
- **미실행:** 7개 원본 Full RF `.npy`, SourceFFD bank, 7개 원래 E1 NPZ의 **실제 물리 데이터 실행**. 해당 바이트가 이 작업 컨테이너에 없고 GitHub 연결은 `.npy`/`.csv.gz` 내용을 제공하지 못했다. 실측(시뮬레이션 원본) R²·정보증가율을 이 문서에서 만들어내지 않는다.
- **추가 정보량**은 *오프라인 GT 기반 모델 검증*이지 Heading RMSE 개선을 증명하지 않음. 새 5상태 EKF를 실제로 적용·평가하는 것은 다음 실험.

## 왜 이 실험인가

최근 GitHub PB 결과는 `MB_VAR`가 BB 원래 대비 Heading 23/28, XY 20/28 개선됨을 보여준다. XY 8개 미달은 `R2_aA_m45`×B0/L0/L1/L2 4조건(Heading·XY 모두 크게 악화)와 `R4_aB_m0`×4조건(Heading은 개선, XY 0.3–0.4cm 차)로 집중됨. `R5_aA_m0/L2`는 Heading만 약간 미달. 따라서 `MB_VAR`는 유효한 기준선이나 일괄 채택 불가. 실패를 ``모델링오차=나쁨``으로 설명하기보다 실제 `K_s` 갱신이 이전 Heading 오차를 유리하게 보정했는지 검증해야 한다.

## 입력

**필수:**
- `--repo-root`: `research/DS_MASK_CAUSAL_X1_X2_20261026/e1_e4/E1/`의 동결 실험, `PJ_DS_GATED_20261021/results_murec/`, `DS_RF_CAUSAL_STAGE7_8_V1_20261028/code/`를 가진 Git checkout. Git HEAD는 `16eb952` 후손이어야 함.
- `--source-root`: 과거 실행의 동결 `p2` (SourceFFD, bank의 원래 출처, `H_R2_aA_m45.npy` 포함 **7 Full RF**).
- `--artifacts-root`: 대응 `p2_artifacts`; `OOF_PARAMETERS` 및 bank의 원래 출처.
- `--code-root`: 동결된 `research/DS_RF_CAUSAL_STAGE7_8_V1_20261028/code/`.
- `--output-root`: repo, source, artifacts **밖에** 아직 존재하지 않는 새 디렉터리.

**Git LFS** 포인터가 아닌 `.npy/.npz` 실제 바이트가 필요. `Context`에 있는 원본 E1 NPZ/Source bank/MR 입력 SHA 검사가 동작한다. 원본파일은 수정하지 않는다.

`b17b0f5`에 새로 복원된 다른 5개 mount45 Full RF는 아직 해당 7조건의 기존 OOF/EXDS 모형·E1 trace에 포함되지 않는다. 새로운 mount45 조건을 추가하기 전에 독립 입력 잠금 및 예측/재귀 산출물이 필요하다. 현재 실험은 7개 동결 조건만 분석한다.

## 실행 (PowerShell)

압축을 새 폴더에 해제하고, 아래 경로를 실제 환경에 맞게 수정한다.

```powershell
$P    = 'D:\SLAM_bot\DELTA_S_INFO_AUDIT_V1'
$Repo = 'D:\SLAM_bot\DS_X1_X2_RESULTS_COMMIT_20261026'
$Src  = 'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2'
$Art  = 'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2_artifacts'
$Code = Join-Path $Repo 'research\DS_RF_CAUSAL_STAGE7_8_V1_20261028\code'
$Out  = 'D:\SLAM_bot\DELTA_S_INFO_AUDIT_V1_RESULTS'

python "$P\ds_info_audit.py" --mode real --repo-root $Repo `
  --source-root $Src --artifacts-root $Art --code-root $Code --output-root $Out
```

**합성 테스트:**

```powershell
cd $P
python -m unittest -v test_ds_info_audit
python ds_info_audit.py --mode synthetic --output-root D:\SLAM_bot\SYNTHETIC_DS_INFO_NEW
```

이미 존재하는 output-root는 실수로 덮어쓰지 않는다. 재실행 시 다른 새 폴더를 사용한다.

## 정보량 검증의 엄밀한 정의

편파 잔차 `e_s = z_s - h_s(GT) - μ_s`를 5초 **centered** 이동평균한 저주파 진단 라벨 `b`를 사용한다. 여기는 미래/GT가 포함되어 **훈련·진단 전용**이다.

원시 Δs 관측은 Full CIR에서 뽑은 `s(fp+1)-s(fp)`이며 LOS 모델 SourceFFD의 동일 파형 특성을 빼 `d = Δs_full - Δs_LOS(GT)`를 만든다. **학습**: 2개 다른 route의 `d = c_0 + a b + ε_d` 회귀, `R = Cov([ε_r, ε_s, ε_d])`의 부호 있는 3×3 교차공분산을 경로·case 균등가중으로 추정. `ε_s=e_s-b`, `ε_r`는 EXDS Range mean 보정 후 GT 잔차. 오차 공분산은 SPD화하되 교차항을 0으로 만드는 단순 DIAG가 아니다.

**테스트 route에서는 학습을 일절 변경하지 않는다.** 모든 case에서 `P^-_4`와 기존 SourceFFD Jacobian은 frozen E1 **EXDS prior**에서 평가하며, `h_Δ`는 SourceFFD의 FP+1 차이에서 x,y,ψ로 유한차분한다. FP tap이 인근 perturbation에서 바뀐 샘플은 비매끄러움으로 분리하여 제외한다. 

상태 `[x,y,ψ,b_g,b_s]`를 두고 새로운 선형화 관측을 정의한다.

\[
H_{2} = \begin{bmatrix}H_r &0\\H_s&1\end{bmatrix},\quad
H_3=\begin{bmatrix}H_r&0\\H_s&1\\H_\Delta&a\end{bmatrix},
\quad R_2=R_3[0:2,0:2].
\]

동일한 `P^- = diag-block(P^-_4, \sigma_b^2)`와 train-only `R_2/R_3`에 대해

\[
P^+_j=P^- -P^- H_j^T(H_jP^-H_j^T+R_j)^{-1}H_jP^-,\quad
G_\psi=\frac{[P^+_2]_{\psi\psi}}{[P^+_3]_{\psi\psi}}-1.
\]

`Gψ >= 0`는 **R3가 유효할 때 수학적으로 거의 자동인 성질**이므로 과학적 성공이 아니다. 중요한 것은 `Gψ`의 크기, out-of-route **bias 예측 R²**, `3D residual whitened χ² 평균` 및 `train/held 분산비`, 비매끄러운 FP 전환 비율이다. 이들 중 일부라도 불안정하면 3채널 EKF 확대를 보류한다.

**주의:** `Cov(b,x)`를 0으로 둔 초기 후보이며 포즈 prior는 이미 원래 RF 업데이트 이력을 포함한다. 또 하나의 새로운 측정을 같은 정보로 중복계산하지 않으려면 3×3 오차공분산과 시간상관 진단이 필요하다. Δs와 s의 동일 CIR 유래 상관은 `R3[1,2]`에 보존한다. 이를 전역 정규화해 소거하지 않는다.

## MB_VAR 원인추적 정의

원래 MB와 `R_ss += σ_b(rho_hat)^2`를 frozen `A_B`로 재귀 실행한다. `MB_ORIG`는 원본 E1의 x/P/h/H/K/ν/μ/R과 **최대 1e-10** parity gate에 통과해야 후속 분석을 수행한다. 다음 두 측정은 구별한다.

1. **동일한 MB_ORIG prior**에서 `R`만 `R_VAR`로 바꾸어 한 번 갱신: `sameprior_delta_head_mse_deg2` (직접 가중치 효과, 후속 상태 영향 제외).
2. **각각 자유재귀**한 MB_VAR와 MB_ORIG의 `full_recursive_heading_gap_deg`, XY 오차 차 (과거 상태·공분산 효과 포함).

더해 `orig_s_contribution_head_mse_deg2` 및 `var_s_contribution_head_mse_deg2`는 한 갱신에서 range 채널 갱신량을 반영한 뒤 **편파 증분의 Heading 제곱오차 변화**이다. 음수는 그 한 패킷의 Heading을 보정한 경우, 양수는 악화시킨 경우. 하지만 이 값의 전체 합을 최종 RMSE의 인과 기여라고 주장하지 않는다.

경로별 `VAR_GAIN_TRACE_<case>_B0.csv.gz`에 실제 packet 시계열과 `VAR_FAILURE_SUMMARY.csv`를 기록한다.

## 출력 설명

- `HELD_ROUTE_BIAS_PREDICTION.csv` — route-excluded Δs의 저주파 편향 예측 R²/상관.
- `TRAINED_COVARIANCES.csv` — 3×3 부호 있는 R의 모든 성분, β–Δs 회귀 계수, train case 목록.
- `HELD_ROUTE_COV_CALIBRATION.csv` — held-route 공분산/화이트닝 보정의 실제 적합도.
- `INFORMATION_SUMMARY.csv` — Heading posterior precision gain의 case별 중앙값/10% quantile, 미분 불안정 제외 개수.
- `FROZEN_PRIOR_INFORMATION.csv.gz` — 패킷별 동일 prior 2 vs 3 채널 정보량.
- `INPUT_GT_DECOMPOSITION.csv.gz` — B0 실RF GT 진단 라벨의 packet별 값.
- `VAR_FAILURE_SUMMARY.csv` — MB_VAR 재귀 비교 vs MB_ORIG.
- `VAR_GAIN_TRACE_<case>_B0.csv.gz` — packet별 K_r·K_s, 동일prior direct effect/자유재귀 누적 비교.
- `INFORMATION_AUDIT_STATUS.json` — 입력 해시, 코드/실험 경계, 결과 SHA.

**성공 판정은 추후 사전 정의**: 모델 정보증가는 항상 >=0인 성질이므로 `Gψ>0`만으로 PASS 처리하지 않는다. 최소 한 경로의 held R²가 음수이거나 calibration ratio가 심하게 어긋날 경우 정보량 예측이 실제로 실현된다고 해석할 수 없다. 이번 패키지는 *측정수준 정보량 검증*이고 새 EKF 성능은 아직 검증하지 않았다.
