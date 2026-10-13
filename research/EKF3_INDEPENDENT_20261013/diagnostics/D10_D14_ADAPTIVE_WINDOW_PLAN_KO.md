# EKF3 D10–D14 후속 진단 계획 및 사용자 직접 실행 계약

**작성 상태: 신규 진단 코드 구현 · 합성 단위 검증만. 실제 D10–D14 Frozen RF 전체 실행은 `NOT_RUN`, `scientific_PASS=false`.**

- 기준 브랜치: `research/ekf3-independent-p0-20261013`
- 부모 커밋: `e494aba049c298fe75578dc8095a0d8aea6efd45`
- 기존 D0–D9 코드/결과, frozen RF `.npy`, LUT, P0/P1/P2 및 FFD bank는 **읽기 전용**. 새 파일은 `diagnostics/`에만 추가.
- 가장 중요한 연구 질문: **unresolved multipath에서, 매우 짧은 co-reference window를 사용해 `RMS(s_Full-s_LoS)`를 단일 FP보다 줄이는가?**
- 1차 성공 판정은 **Full–LoS `s` 차이 감소**, 2차 판정은 LoS 관측모델 적합성·Heading 민감도 유지·EKF Heading/coverage. 2차 지표는 1차 결과를 대신할 수 없다.
- RX1/RX2는 물리적으로 ±45° 포트이며 무조건적인 co/cross 채널이 아니다. `co_port=auto`는 **frozen FP에서 더 강한 포트**를 데이터 기반 기준 포트로 택한다. 물리적 co를 알고 있다면 `--co-port rx1|rx2`로 별도 실험. 둘을 서로 다른 데이터 조건으로 기록하며 한쪽 결과를 유리하게 사후 선택하지 않는다.

## 1. 불완전 분리 경로의 Adaptive Window (W2)

수신기 규약: 단일 TX0(+45°), RX ±45°, 257 frequency bin, Hann, 4N IFFT. 기존 30%-leading edge 첫 tap `k_FP`는 **절대 변경하지 않으며**, 기존 range 및 W0 s의 exact parity를 확인한다.

**단계별 동작**

1. 원본 `k_FP`에서 두 포트의 전력을 확인해 기준 RX를 결정한다. 선택한 기준 포트에만 원래 30% leading-edge detector를 적용해 `k_co`를 얻는다. `auto`가 원본 FP보다 늦은 경로를 선택하면 초기 기준을 원본 FP까지 되돌려 잘못된 지연을 억제한다. 동일한 `k_co`에서 양 포트 측정 시작.
2. `P_co(k)=|CIR_co(k)|²`, `P_other(k)=|CIR_other(k)|²`. `k_co`의 상대 전력비 `q0=(P_other+floor)/(P_co+floor)`를 기준으로 삼는다.
3. 검사 tap `k`에서 단순한 다른 포트 절대 상승이 아닌, (a) 다른 포트 전력의 증가, (b) 기준 포트 펄스로 설명되지 않는 **상대 전력비 증가** `q(k)>growth_ratio*q0`, (c) 초과 전력 `P_other(k)-q0 P_co(k)`가 지정 threshold를 초과하는지 동시에 확인한다.
4. 기본값: 상대 증가비 `1.7`, 다른 포트 연속 증가비 `1.08`, 첫 기준 포트 전력 대비 초과전력 `0.025`, 연속 **2 tap** 충족, 최대 window 길이 **4 tap**, 최대 검사 구간 9 tap. 이는 성능 최적화 값이 아닌 사전 정한 *탐색 조건*이다. LoS 순수 펄스의 공동 상승에서 거짓 트리거가 나오는지 반드시 비교한다.
5. 조건이 충족되는 첫 tap `k_rise`를 찾으면 **그 전에서 종료**한다 (`[k_co, k_rise)`). 찾지 못하면 최대 4 tap에서 종료한다. 길이가 1 tap이어도 가능. 양 포트에 **완전히 동일한 window** 적용.
6. `s_W=(sum_{k in W}|CIR_RX1[k]|²-sum_{k in W}|CIR_RX2[k]|²)/(두 전력 합)`으로 계산한다. 원래 수신기의 TX0/전력비 부호 유지.
7. 첫 tap부터 반사파가 중첩되면 CIR만으로 직접파를 완벽히 분리할 수 없다. 해당 영역은 `unresolved_at_fp_unidentifiable=1` (원리적 가능성 플래그)로 표기. `cross_rise_detected=0`은 LoS 순수성 보증이 **아니다**. 실제 잡음 수준을 모르는 동결 noiseless H에서 잡음 기반 유의성 주장 금지.

**지연 분해능:** 499.2 MHz 대역 → 약 2.00 ns, 약 0.60 m 거리 상당의 명목 분해능. 4N IFFT grid 약 0.499 ns/0.15 m는 **보간 간격**이며 4 tap이 독립 물리경로 4개가 아니다. 1–4 tap 선택은 샘플링된 펄스의 어느 부분을 사용하느냐의 선택일 뿐 분리된 반사 경로를 복원한다는 주장이 아니다.

**실험 비교군**

- `W0_FP`: 기존 공통 FP 한 tap. 모든 P2 parity 기준.
- `W0_CO_FP`: co-reference port가 검출한 FP **한 tap**. 포트/시점 변경과 window 적분 효과 분리.
- `W1_EARLY3`: co-reference FP부터 고정 3 tap 양 포트 적분.
- `W2_ADAPTIVE_CROSS`: 다른 포트의 상대적 초과 상승 직전까지만 적분, 기본 최대 4 tap.
- `W3_PULSE_TEMPLATE`: co RX만으로 Hann pulse leading-edge time shift를 선택하고, 같은 복소 템플릿으로 두 RX 진폭 추정. 검증 전 **탐색적 대조군**, LoS oracle tap 사용하지 않음.
- `W4_TOTAL_ENERGY`: 전체 CIR 에너지 비, 반사파 오염에 취약한 음성 대조군.

서로 다른 window의 `s`를 기존 FP 전용 LUT와 비교·업데이트하면 **관측모델이 불일치**한다. W1/W2/W3/W4 및 co FP는 동일 연산을 LoS FFD 합성에도 적용해야 한다.

## 2. D10 — 기존 데이터로 RF error ↔ Ranging/Heading 상관

코드: `d10_multipath_correlations.py`. D7 온라인 특징과 오라클 평가 label을 key(case/channel/sample_index/pose_id/t_s)로 정확히 결합하되, **진단 파일에서만 결합**한다. Full RF에서 `e_r_mp`, `e_s_mp`, tap selection / same-tap 성분을 이용하고 원래 D2 gain trace는 선택 입력으로 받는다.

출력: `D10_RANGE_S_CORRELATION.csv`, `D10_CIR_ERROR_ASSOCIATIONS.csv`, `D10_TEMPORAL_DEPENDENCE.csv`, 선택적 `D10_ORIGINAL_D2_HEADING_GAINS.csv`, `D10_RF_HEADING_CORRELATION.csv`, `D10_RANGE_MODEL_CROSS_COV.csv`. Pearson/Spearman, signed/absolute/squared correlation, case/route/distance 조건부, lag-1, D2 heading squared-error change. **단일 RF scene/time correlation**으로 독립 유의확률 주장 금지.

## 3. D11 — Frozen H로 W0–W4/F0 비교

코드: `d11_adaptive_window.py`. 모든 수신 방식은 원본 `H`, 원본 `OBS.cir_batch`, 원본 FP receiver를 유지한 뒤 별도 관측을 계산한다. W0는 기존 s와 `atol=1e-12`의 receiver parity. 결과를 분리 저장:

- `D11_ONLINE_WINDOW_S.csv`: 실제 한 채널에서 사용 가능한 `s`/검출/포트/window 특징. **truth/LoS counterfactual 없음**.
- `D11_ORACLE_PAIR_EVAL.csv`: paired Full–LoS 차이. **offline 전용**.
- `D11_CASE_SUMMARY.csv`: 각 방법의 RMS·편향·95% 절대 편차·window 길이/선택 모호성.

동일 case/pose/time을 정확히 짝짓고 route별로 개선되는지 비교. W2는 처음부터 겹친 경로를 분리할 수 없으므로 **조건부 혜택**으로 보고한다.

## 4. D12 — 대응 LoS 관측모델 및 One-step A/C

코드: `d12_los_window_model.py`. 기존 W0에 대해서는 고정 FP LUT와 frozen P2 (`A`, `C`) 비교로 기준선 parity. 새로운 W 후보는 **동결 FFD bank에서 측정 위치 추정치 x,y,ψ만 이용해 LoS H를 직접 합성**하고 같은 W 추출기를 적용한 `h_s,W(x)`와 수치 미분 Jacobian을 만든다. 이는 새 관측모델의 직접 계산 기준(reference implementation)이며, **대규모 4D angle+distance LUT 가속화는 아직 구현하지 않았다.**

bank `LP_plus45_bank.npz`, `LP_minus45_bank.npz`와 bank manifest에 담긴 SHA-256이 필요하다 (`git lfs pull`). 파라미터에 따라 window 선택과 sub-tap fractional delay가 달라지므로 기존 각도 전용 FP LUT가 그대로 적용된다는 가정은 금지.

출력: `D12_WINDOW_ONE_STEP.csv`, `D12_WINDOW_SUMMARY.csv`, `D12_WINDOW_GATES.json`. P2에 저장된 공통 xminus/Pminus, 원본 range, R0를 고정한 A/C same-prior 비교. 온라인 predictor로는 **prior x만** 사용하고 truth 기반 `h_s,W(truth)`는 오차 scoring 및 Heading 민감도 분석에만 사용.

**1차 gate (탐색적, 변경 금지):** Full–LoS RMS 비 ≤0.95, 3개 route 중 2개 개선, 최악 route 비 ≤1.05; 동시에 LoS 모델 RMS 비 ≤1.25, 평균 |∂h_s/∂ψ| 비 ≥0.80, 두 유한차분 간 Heading Jacobian 정합 샘플 비율 ≥0.95, Full Joint-C Heading RMSE 비 ≤1.05. 모든 7조건·stride1·비절단일 때만 `EXPLORATORY_GATE_PASS/FAIL`; 그보다 작으면 `SMOKE_ONLY`. Scientific PASS 불가.

## 5. D13 — 높은 Heading 불확실성 × Gyro bias × D0/A/B/C

코드: `d13_heading_uncertainty_bias.py`, `d13_d14_filter_core.py`.

- Initial yaw 표준편차: 5°, 10°, 17°, 20°, 30° (동일 초기 표준정규 draw 재척도); covariance Pψψ도 동일하게 변경.
- 동일 기본 sensor-v2 노이즈에 gyro bias만 추가하는 paired 실험(`d6_bias_observability.generate_paired`).
- D0(아무 RF 없음), A(s only), B(range only), C(joint) 분리.
- `EKF3`, `UT_PRED`, `UT_BOTH`(추가 UKF 측정 update), `BIAS4`, `BIAS4_UT_PRED` 비교. `BIAS4_UT_PRED`는 **prediction만 UT**, 관측 update는 EKF임을 명시.
- 기존 원본 `EKF3`, noise_pair, 초기 yaw 5°, bias off 비교 cell은 원래 D5의 RMSE·NEES·coverage·update count와 절대 허용치 `1e-8`로 parity. 원본 참조가 없는 조건은 별도 판정; 오류 허용치 완화 금지.
- 출력: `D13_ARM_NONLINEARITY_BIAS.csv`, `D13_PAIRED_BIAS_EFFECT.csv`, 선택적 전체 시점 trace. 샘플 단위 신뢰구간과 RF scene 일반화를 구분.

## 6. D14 — W2와 필터 개선의 독립 교차검증

코드: `d14_window_fusion_ablation.py`.

- F0: 기존 W0 + EKF3
- F1: W2 + EKF3
- F2: W0 + UT prediction+measurement
- F3: W0 + Bias4
- F4: W2 + UT prediction+measurement
- F5: W2 + Bias4
- F6: W2 + Bias4 + UT prediction (measurement EKF)

Range는 모든 팔에서 원래 `B_OLD`로 유지하고 `R_s/R_r`는 R0 고정한다. **D8에서 실패한 Full RF 품질 공분산 Q3는 사용하지 않는다.** D12 W2 gate가 FAIL/SMOKE_ONLY이면 신규 window method는 기본적으로 실행 거부하고 명시적인 `--exploratory-allow-failed-gate`에서만 실행한다(후속 성능 개선 주장 금지).

1차 지표는 D11의 Full–LoS RMS, 2차 지표는 재귀 Heading/XY RMSE, pose/heading 95% 포함률, NEES, NIS lag1, bias 수준별 paired delta. 모든 F0가 D5와 일치해야 하고, 그 외 cell은 `NOT_RUN`/탐색적 비교임을 명시한다.

## 7. 사용자 직접 실행 예시 (PowerShell)

프로젝트 repository root에서, 별도 출력 폴더 이름을 사용한다. **아래 명령은 안내이며 이 커밋 작성자는 실행하지 않았다.**

```powershell
# 0. 최신 연구 브랜치
$P = 'research/EKF3_INDEPENDENT_20261013/diagnostics'
git fetch origin
git switch research/ekf3-independent-p0-20261013
git pull --ff-only origin research/ekf3-independent-p0-20261013
python -m pytest -q "$P/test_d10_d14.py"
python research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py

# 1. 기존 D7 출력이 이미 로컬에 있으면 사용 가능. 반드시 D7_MANIFEST.json 및 두 CSV 필요
python "$P/d10_multipath_correlations.py" --d7 artifacts/ekf3_D7_FULL --out artifacts/ekf3_D10_RUN `
  --d2 research/EKF3_INDEPENDENT_20261013/diagnostics/results/AUDITED_RUN_20261013_701b8d2/OUTPUT_D0_D4_SEED0/D2_HEADING_DECOMPOSITION.csv.gz

# 2. W2 우선 smoke (동결 H를 읽을 뿐 새 Sionna RF 생성 없음)
python "$P/d11_adaptive_window.py" --out artifacts/ekf3_D11_SMOKE --cases R2_aA_m0
python "$P/d11_adaptive_window.py" --out artifacts/ekf3_D11_FULL

# 3. FFD bank 파일이 LFS 포인터가 아니라 실제 바이너리인지 확인 후 D12
# git lfs pull
python "$P/d12_los_window_model.py" --d11 artifacts/ekf3_D11_FULL `
  --p2-dir "$P/P2_DOWNLOAD/P2_OUT" --out artifacts/ekf3_D12_SMOKE `
  --cases R2_aA_m0 --stride 20 --max-eval-per-case 10
# 완전한 D12 (계산량이 크며 다른 새 출력 경로 사용)
python "$P/d12_los_window_model.py" --d11 artifacts/ekf3_D11_FULL `
  --p2-dir "$P/P2_DOWNLOAD/P2_OUT" --out artifacts/ekf3_D12_FULL

# 4. D13 먼저 단일 경로, gyro bias off/on 및 5/17/20°
python "$P/d13_heading_uncertainty_bias.py" --out artifacts/ekf3_D13_SMOKE `
  --cases R2_aA_m0 --channels full --seeds 0 --levels 1 `
  --heading-std-deg 5 17 20 --bias-modes off on `
  --methods EKF3 UT_PRED UT_BOTH BIAS4 --save-trace

# 5. D12에서 W2 통과한 후 D14 실험
python "$P/d14_window_fusion_ablation.py" --d11 artifacts/ekf3_D11_FULL `
  --d12 artifacts/ekf3_D12_FULL --out artifacts/ekf3_D14_SMOKE `
  --cases R2_aA_m0 --channels full --seeds 0 --levels 1 `
  --heading-std-deg 5 --bias-modes off --save-trace
```

**참고:** PowerShell에서는 줄 연결에 백틱(`` ` ``)을 사용한다. 줄 맨 끝에 공백을 추가하지 않는다.

## 8. Fail-closed와 감사 상태

1. 원본 frozen P0/P1/P2/observer/RF 파일은 절대 overwrite 금지. D11 observer parity, D12 P2 parity, D13/D14 D5 F0 parity 실패 시 완료 PASS 기록 금지.
2. D11 온라인 파일에 truth/distance/oracle Full–LoS 잔차 누출 금지. Full–LoS 차이 및 LUT(truth) 오차는 별도의 평가 파일에만 저장.
3. SNR/위상 캘리브레이션 없는 위상 기반 품질 게이트는 사용하지 않는다. W3의 Hann 펄스는 검증된 다중경로 분리가 아니다.
4. `D11` window 설정이 바뀐 채 `D12`/`D14`에 연결되는 경우 입력 계약을 검사한다. 모든 결과 파일은 stage manifest에 SHA-256과 실행 config를 기록, 덮어쓰기 금지.
5. 결과를 보고 W2 임계값을 조정하면 **새로운 개발 실험**으로 취급하고 동일 scene holdout을 독립 확증으로 사용하지 않는다.
6. D12의 미구현 부분: dense 4차원 LUT acceleration / 실제 receiver noise-SNR 모델의 하드웨어 보정. D13/D14 Full multi-seed RF 실험과 독립 RF scene 검증도 **NOT_RUN**.
7. 코드 단위 smoke는 실제 프로젝트 import/FFD bank/Local P2/D5 files 전체 호환성을 대체하지 않는다. 재감사 전에는 `execution_ready=false`, `scientific_PASS=false`로 유지한다.
