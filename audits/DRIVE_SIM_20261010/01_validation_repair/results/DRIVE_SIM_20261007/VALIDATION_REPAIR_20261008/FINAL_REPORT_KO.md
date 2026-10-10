# DRIVE_SIM 검증 수정 및 과학적 채택 판단

작성일: 2026-10-08, 한국 표준시. 기준 revision: `991da089e0723644b244fb663b37c519b6e941e2`. 작업 브랜치: `codex/drive-validation-20261008`.

**평가 누락으로 생기는 거짓 PASS는 수정·회귀검증했다. 제한된 모델 일치 대조군은 정상 동작했다. 그러나 F01(L1/L2 실패)과 F02(공분산 불일치)는 미해결이며 `scientific_PASS=false`를 유지한다.** 저장된 R2-A-m0의 분리 평가에서 거리별 불확실성은 상수 모델보다 정확도를 개선했지만 공분산 일관성을 확보하지 못했다. 각도 상태가 한 구간에만 존재해 거리+각도 모델의 추가 효과는 식별되지 않았다. 실제 편파 매칭의 효과가 검증되었다고 부를 수 없다.

## 범위와 증거 수준

수정·실행은 다음 별도 checkout에서만 수행했다.

`D:/SLAM_bot/artifacts/DRIVE_SIM_VALIDATION_REPAIR_20261008_01a11a0b/checkout`

최초 HEAD는 위 revision과 같았고 `git status --short`는 비어 있었다. remote는 `https://github.com/myoungsunk/sionna-resimulation.git`이었다. 대상 브랜치가 이동하는지와 무관하게 이 기준을 고정했다. 전체 과거 감사를 반복하지 않았고, GSF PSD와 기존 G2/G2′ 누락 검출을 신규 구현으로 재작성하지 않았다.

원본은 다음 디렉터리에서 읽기 전용으로 재사용했다.

`D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/selected_raw`

| 파일 | shape | SHA256 |
|---|---|---|
| H_R2_aA_m0.npy | 1303×257×2×2 | `1c40aea5ab7af87223f942c0727c0f6aabe7bd60e55a70c68c74d2c115750a51` |
| freqs_hz.npy | 257 | `fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8` |
| hs_lut_2deg.npy | 46×180×180 | `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079` |
| hs_lut_meta.json | JSON | `8773e79fbb39d07fd80605339a0752e6e4e5eb0658572f091e67395ab0fd5856` |

H의 해시는 원래 `SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/results/S2/H_R2_aA_m0.manifest.json`의 output 해시와 일치했다. `S1/routes/timeline_R2_Tnone.csv`의 pose_id를 `rf_poses_R2.json`에 대응시켜 x/y/yaw 오차가 1e-6 이하임을 검사했다. 범위·finite 값·주파수 간격·shape 검사도 수행했다. 이는 데이터의 출처와 timeline 대응을 확인한 것이며 RF 물리 검증 완료의 뜻은 아니다. 상세값은 [INPUT_MANIFEST.json](INPUT_MANIFEST.json), [RAW_ORIGIN_CHECK.json](RAW_ORIGIN_CHECK.json)에 있다.

실행 전 [EXECUTION_PLAN.json](EXECUTION_PLAN.json)에 revision, seed, 분할, 비교 모델, fallback, 평가 subspace와 계산 범위를 기록했다. 구현상의 block 표기와 단계 사이 집계 소스 변경은 [PRERECORD_CLARIFICATIONS.md](PRERECORD_CLARIFICATIONS.md)에 별도로 설명했다. 원래 계획을 결과 후 덮어쓰지 않았다. 실행 환경은 설치돼 있던 Python 3.10, NumPy 2.2.4를 사용했다. 새 환경 설치, Snowball 접속, 새 RF 생성, production campaign, commit/push/merge는 수행하지 않았다.

## 1단계 — 입력 게이트와 실행 기록

**기존 방식 → 문제.** 기존 누락 검사는 G2/G2′의 missing/unusable 위치를 검사했지만, 전체 게이트 선택이 없으면 `all([])`가 참이 됐다. G4는 발견한 receipt만 평가해서 기대 pose/yaw 누락을 검출하지 못했다. FAIL이 CLI 성공 종료와 구분되지 않는 문제도 있었다.

**수정 이유 → 수정 내용.** 완전한 평가 집합이 있을 때만 수치 판정이 의미를 갖는다. `scripts/drive_sim/parity_gate.py:103`에서 사전 task manifest의 기대 집합을 읽고, `:121`에서 실제 집합의 누락·추가·중복을 검사한다. `:186`의 CLI는 게이트 미선택, 빈 reference/evaluation, malformed 입력을 명시적 오류로 기록하고 FAIL이면 exit 1을 반환한다. 비정상 H shape·NaN·reference 영전력·주파수 순서도 거절한다. 기존 G2/G2′ 수치식과 임계값은 유지했다.

G4는 필수 `--g4-manifest`의 SHA256·기대 개수·trace mode를 남긴다. 사전등록의 G4 “same as G2”에 맞춰 node trace에도 엄격한 G2 기준을 적용했다. 기존 코드의 node G4가 G2′ 기준을 썼던 차이를 숨기지 않았다. `run_rf_snowball.sh`의 관련 두 호출에 manifest 인자를 추가했으나 해당 shell/RF 실행은 하지 않았다.

**실제 결과.** 10개 입력 회귀 테스트가 통과했다. 실제 무선택 CLI는 `NO_GATES_SELECTED`, `all_passed=false`, exit 1이었다. 유효한 G2/G2′ fixture 6개의 요약 객체는 기준 revision의 함수와 완전히 동일했다. 초기 테스트의 FAIL 기대값이 실제 임계값보다 작아 실패한 것은 fixture를 수정했으며 게이트 기준은 바꾸지 않았다.

**기대효과와 한계.** 테스트된 평가 누락에 의한 거짓 PASS 차단은 달성했다. 실제 G4 RF 재평가와 anchor-B geometry 검증은 미수행이다. 특히 기존 node G4 PASS를 수정 코드의 PASS로 승계할 수 없다. [STEP1_REPORT_KO.md](STEP1_REPORT_KO.md), [STEP1_REGRESSION.json](STEP1_REGRESSION.json)에 코드·수치·로그 근거가 있다.

## 2단계 — 완전히 모델이 일치하는 제한 합성 대조군

**기존 방식 → 문제.** A17/E1의 좋은 NEES만으로 필터 구현 전체의 정상성을 결론 내리면, 보수적인 R이 모델 불일치를 가린 가능성을 놓친다. legacy gyro 재사용과 wheel 근사도 그대로 남는다.

**수정 이유 → 수정 내용.** 생성기와 필터가 같은 transition·Q·측정식·R을 쓰는 대조군을 새로 구성했다. seed 3000–3199, 각 120 sample에서 process noise와 UWB noise를 독립 생성했다. bias/SF/diameter state도 필터의 random walk와 같은 법칙으로 진행한다. range와 s에는 실제 필터 R과 같은 분산의 Gaussian noise를 더한다. thermal·tap 양자화 slack을 제거했고, s sigma=0.04, range sigma=0.03으로 생성기와 R을 함께 고정했다. 비교 결과를 맞추는 tuning은 하지 않았다.

비선형 EKF의 국소 선형화는 남으므로 별도로 생산 코드의 Joseph update를 쓰는 정확한 1차원 선형 Gaussian 대조군 200개를 구성했다. 모델 일치 시험에서는 innovation truncation 효과를 제외하려고 gate를 비활성화했다. production gate는 변경하지 않았다. 공유 gyro 문제가 없는 대조군을 만들기 위해 odom-heading pseudo-measurement는 사용하지 않았다. 이는 해당 legacy 경로를 검증한 것으로 해석하지 않는다.

**실제 결과.** pose 3자유도 NEES의 seed 평균은 **3.016**, bootstrap CI는 **[2.730, 3.320]**이었다. 95% pose coverage 평균은 **0.936**, CI **[0.912, 0.957]**이었다. 양측 2.5/97.5 percentile 기준의 아래/위 tail은 **0.031/0.034**였다. 정확한 scalar 대조군의 평균 NEES는 **0.933**으로 기대값 1과 가까웠다. Jacobian finite-difference 최대 오차는 **1.43e-9**, covariance propagation 비교 오차는 **3.37e-13**, full covariance 최소 고유값은 **1.28e-9**로 PSD였다. angle wrapping도 확인했다. range Jacobian 추가 검사 오차는 [PROCESS_MODEL_LIMITS.json](PROCESS_MODEL_LIMITS.json)에 기록했다.

**기대효과와 한계.** 제한된 국소 EKF·Joseph update·단위·Jacobian·전파의 구현 검증은 달성했다. 전역 관측성, cold start, 물리 RF, IEKF/UKF 전체 일관성까지 증명하지 않는다. 공유 gyro 교차공분산의 계산값은 **1.365e-8**, 해석값은 **1.371e-8**로 0이 아니지만 legacy 갱신은 이 항을 생략한다. 정확한 wheel 무잡음 식은 `ds_o=ds+eps_d*b*dtheta/4`, `dtheta_o=(dtheta+eps_d*ds/b)/(1+e_b)`이다. legacy 근사는 여기에 완전히 일치하지 않는다. F07의 구현/모델 한계는 남고, 그 영향 비율은 UNKNOWN이다. 코드 근거: `validation_repair.py:93,143`, `filters.py:206`, `sensors.py:77`. [STEP2_MATCHED_CONTROL.json](STEP2_MATCHED_CONTROL.json).

## 3단계 — LUT부터 full RF까지 관측 오차 분해

**기존 방식 → 문제.** full RF–LUT 잔차를 mismatch sigma에 넣어도 LUT 자체의 L1/L2 실패는 해결되지 않는다. 거리 기준·tap 전환·다중경로의 원인을 하나로 묶으면 수정 위치를 특정하지 못한다.

**수정 이유 → 실제 실행.** 동일 저장 H·timeline·주파수·single-TX first-path chain에서 full RF s와 LUT 예측, range와 기하학적 거리의 차이를 계산했다. range에서는 기존 bank 기반 offset **−0.531598390625 m**를 그대로 적용했다. mean, centered population variance, RMS를 별도로 계산했다. 이 분산 추정에 시간 표본 독립성이나 신뢰구간을 주장하지 않는다.

| t≥30s의 829 sample | 평균 편향 | 평균 제거 분산 | RMS | lag-1 상관 |
|---|---:|---:|---:|---:|
| s full RF−LUT | 0.04651 | 0.029915 | 0.17910 | 0.92711 |
| range−기하거리−offset [m] | 0.05194 | 0.012470 | 0.12316 | 0.80398 |

range–s 잔차 상관은 **0.52263**이었다. first-path index가 바뀐 189 sample의 s RMS는 **0.17632**, 안 바뀐 640 sample은 **0.17992**였다. tap 변화만으로 잔차를 설명할 수 없으며, 이 비교는 상관/연관 진단이다. 하위 집합에서 lag-1은 원래 timeline에서 서로 인접한 sample 쌍만 계산했다.

**독립 실행하지 못한 항목.** local FFD bank 파일은 모두 134-byte LFS pointer다. 같은 pose의 Sionna LoS-only H와 raw Jones trace도 선택 원본에 없다. 따라서 LUT↔직접 LoS(L1), LUT↔Sionna LoS(L2), D_REF=10m↔실제 거리에서의 직접 LoS, LoS↔다중경로의 원인별 차이는 **UNKNOWN / NOT INDEPENDENTLY VERIFIED**다. 이를 이상적인 가짜 pattern이나 flat-channel 실험으로 대체하지 않았다.

원본 L1은 max **0.023972>0.01**, median **0.000530**으로 FAIL이다. 원본 L2도 max 약 **0.0104>0.005**로 FAIL이다. 두 값은 저장 보고서의 관찰이며 이번에 독립 재실행한 수치가 아니다. 원래 기준과 FAIL을 유지했다. L2 원본 경로와 해시는 [STEP3_OBSERVATION_LAYERS.json](STEP3_OBSERVATION_LAYERS.json)에 있다.

**기대효과와 한계.** 편향·분산·시간 상관·range–s 상관·tap 연관의 분리는 달성했다. 정확한 계산 계층의 원인 분해는 원본 부족으로 부분 달성이다. 코드 근거: `validation_repair.py:194`, `hs_lut.py:24,39`, `observation.py:64`. 모든 sample 잔차는 [STEP3_RESIDUALS.csv](STEP3_RESIDUALS.csv)에 보존했다.

## 4단계 — range × s의 2×2 원인 분리

**기존 방식 → 문제.** 두 관측을 함께 합성화한 A17 대조만으로 각각의 원인과 결합 효과를 완전히 분리할 수 없다.

**수정 이유 → 수정 내용.** R2-A-m0/P0, low drift, seed 4000–4023의 sensor·초기 prior·noise stream·평가 구간을 네 arm에서 공유했다. 실제 관측은 저장 clean RF chain을 사용하고 range에 0.05m Gaussian noise를 추가했다. thermal H noise는 없다. 합성 range에는 `range_sigma²+range_quant_var+range_extra_sigma²`와 같은 분산을, 합성 s에는 기존 route sigma **0.16095229605409875**와 같은 noise를 사용했다. 합성 s는 필터의 additive Gaussian 모델 대조이며 bounded RF power ratio의 물리 생성기가 아니다.

초기 prior의 std는 legacy와 같지만 이번 factorial/held-out harness는 nuisance state를 포함한 6개 초기 추정 성분을 난수화한다. 원래 production의 일부 nuisance 초기 추정=0 방식과 동일 재현이라고 주장하지 않는다. 네 arm 내부의 prior는 동일하며 이 차이는 아래 제한을 만드는 공통 배경 조건이다.

| 관측 조합 | 위치 RMSE seed 평균 [m] | heading RMSE seed 평균 [°] | pose NEES seed 평균 | pose coverage95 |
|---|---:|---:|---:|---:|
| 합성 range + 합성 s | 0.21088 | 1.89254 | 4.63393 | 0.89239 |
| 실제 range + 합성 s | 0.21677 | 1.86738 | 11.95521 | 0.63872 |
| 합성 range + 실제 s | 0.92803 | 10.82030 | 95.69956 | 0.22864 |
| 실제 range + 실제 s | 0.92975 | 10.00808 | 100.76696 | 0.18481 |

**실제 해석.** 이 제한 조건에서는 실제 s가 정확도 악화의 큰 원인이고, 실제 range도 heading RMSE가 거의 같아도 NEES를 악화시킨다. 결합 효과는 단순한 합이 아니다. factorial interaction의 heading 차이는 **−0.787°**, seed bootstrap CI **[−1.276, −0.402]**였다. NEES interaction은 **−2.254**, CI **[−6.993, 2.547]**로 이 자료에서는 유의한 방향을 특정하지 못한다.

**기대효과와 한계.** range와 s의 관측 선택 효과는 통제된 비교로 분리했다. 합성+합성도 NEES=3에 정확히 맞지 않는다. 이는 legacy process/shared-noise와 국소 근사를 남긴 factorial이지 2단계의 완전 모델 일치 대조군이 아니기 때문이다. 전체 F02의 일정 비율을 각 원인에 할당할 수 없다. [STEP4_FACTORIAL.json](STEP4_FACTORIAL.json), `validation_repair.py:213,220,229`.

## 5단계 — 독립 보정과 held-out 평가

**기존 방식 → 문제.** 평가 route 자체로 sigma를 재측정하면 평가 데이터에 맞춘 결과가 될 수 있다. A22의 ν를 실제 편파 매칭으로 부르는 것은 변수의 의미를 넘는다.

**수정 이유 → 모델 정의.** 잔차 `r=s_RF−h_LUT`의 보정 mean `μ=mean(r)`, centered variance `v=mean((r−μ)²)`, RMS `sqrt(v+μ²)`를 분리했다. 분산 모델 비교의 온라인 R은 `thermal_var_s + RMS_cell²`다. RMS에는 편향이 포함되지만 편향 보정은 하지 않는다. R은 신뢰도만 바꾸며 h_LUT의 편향·불연속을 직접 고치지 않는다.

모델은 (a) 보정 전체 상수 RMS, (b) 거리 bin별 RMS, (c) 거리×각도 상태 bin별 RMS다. 거리는 추정 위치에서 anchor까지의 3D link length이고 bin 경계는 **5,10m**다. 각도 상태는 `abs(((heading_est_deg+mount_deg+45) mod90)−45)`이고 경계는 **15,30°**다. 이는 고정 world 축에 대한 antenna yaw의 90° 주기 phase다. actual received polarization overlap, Jones-vector alignment, 일반적인 매칭 정도가 아니다. A22의 ν와 같은 phase 형태를 명시적으로 정의해 사용했으며 다른 FFD에서 steep/flat 의미도 자동 승계하지 않는다.

보정은 원 timeline 앞 40% 중 t≥30s의 **241 sample**, 평가는 뒤 40% 중 t≥30s의 **392 sample**이다. 가운데 20%를 embargo로 두고 보정에 쓰인 pose_id가 평가에 있으면 제외했다. 교집합은 0개이며 독립 reviewer의 5자리 geometry 중복 확인도 0개였다. seed 5000–5023을 사용했다. table은 평가 잔차를 보기 전에 확정했다. 온라인 filter에는 추정 x/y/heading, 알려진 anchor·mount만 제공한다. truth는 보정/평가 지표 계산 및 명시한 oracle 진단에서만 사용한다. 원래 route 시작점의 좁은 prior는 모든 모델에서 공유했다.

cell 지원 조건은 sample≥50, 20-sample timeline 구간의 occupied bin≥3이다. 이것은 독립 반복 수가 아니다. 부족한 joint cell은 distance table, 부족한 distance cell 또는 보정 거리 support 밖은 보정 scalar로 fallback한다. 정의와 사전 소스 근거는 `PRERECORD_CLARIFICATIONS.md`에 있다. **다른 route/anchor/mount의 독립성까지 확보한 분할은 아니다.** 또한 전체 route를 순차 재생하므로 보정 구간의 측정이 앞선 추정 상태에 영향을 준다.

| 구간 | n | 편향 | centered variance | RMS | lag-1 |
|---|---:|---:|---:|---:|---:|
| 보정 | 241 | 0.04073 | 0.004796 | 0.08034 | 0.75733 |
| held-out | 392 | 0.04417 | 0.046297 | 0.21965 | 0.94876 |

| 거리 bin·각도 0–15° | 보정 n | 보정 mean / variance / RMS | 평가 n | 평가 mean / variance / RMS |
|---|---:|---|---:|---|
| ≤5m | 73 | −0.00488 / 0.000362 / 0.01964 | 183 | 0.00734 / 0.000700 / 0.02745 |
| 5–10m | 132 | 0.04534 / 0.002388 / 0.06666 | 132 | 0.02647 / 0.014155 / 0.12188 |
| >10m | 36 | 0.11628 / 0.012616 / 0.16166 | 77 | 0.16204 / 0.192110 / 0.46730 |

마지막 cell은 표본 부족으로 0.16166을 table에 채택하지 않고 scalar로 fallback했다. 모든 각도 표본이 0–15° bin에 들어가고, 나머지 6개 joint cell은 비어 있다. joint table은 distance table과 같은 값만 가지므로 평가 결과도 같았다. **PHASE_EFFECT_NOT_IDENTIFIABLE**이며 편파 관련 상태의 추가 효과는 식별할 수 없다.

truth 특징을 사용한 oracle 측정 잔차 평가에서 정규화 제곱잔차는 scalar **7.474**, distance/joint **8.669**, Gaussian 95% 잔차 coverage는 **0.862 / 0.770**이었다. 평가 구간에서 table의 예측 불확실성이 과소했다. 보정 cell 평균을 빼는 oracle 진단은 RMS **0.21965→0.21427**, lag-1 **0.94876→0.94742**로만 변했다. 조건부 평균 보정은 filter에 구현·채택하지 않았다. 편향만 빼면 충분하다는 근거는 없다.

**기대효과와 한계.** 평가 데이터를 table 학습에서 분리하고 온라인 입력·fallback·편향과 상관을 추적했다. 독립 route 일반화와 각도 조건의 효과는 미검증이다. 추가 RF 조건 없이는 그 효과를 추정할 수 없다. [STEP5_CALIBRATION.json](STEP5_CALIBRATION.json), `uncertainty.py:11,15`, `filters.py:260`, `validation_repair.py:239,260`.

## 6단계 — 정확도와 일관성의 공동 평가

**기존 방식 → 문제.** RMSE가 작은 것과 공분산이 올바른 것은 별도 판정이다. NEES 상한만 검사하면 과도한 공분산도 놓친다. 시간 sample을 독립 반복으로 검정하면 상관된 RF 잔차의 정보량을 과대평가한다.

**평가 변경.** pose `[x,y,heading]`의 3자유도 NEES와 95% coverage, NEES의 2.5/97.5% 양측 tail, heading coverage, innovation NIS, worst-case를 seed별로 계산했다. seed bootstrap은 2000회, seed=20261008이다. 24seed의 CI는 고정 RF realization에 조건부인 sensor/prior randomness에 관한 CI이며, 다른 물리 환경의 CI가 아니다. full 6-state NEES로 바꾸지 않는다.

탐색적 채택 기준은 사전 plan에 기록했다. 위치/heading의 paired median 개선 CI 상단≤0, NEES seed 평균 CI에 3 포함, pose coverage 중앙값 0.90–0.99, 양측 tail 중앙값 각각≤0.05를 동시에 요구했다. 이는 승인된 production gate가 아니라 이번 채택 후보를 좁히는 탐색적 조건이다. 기존 제안 NEES≤6만을 채택 기준으로 쓰지 않았다.

| held-out 24seed | 위치 RMSE 평균 [m] | heading RMSE 평균 [°] | NEES 평균 | pose coverage95 | NEES 하측/상측 tail |
|---|---:|---:|---:|---:|---|
| scalar 보정 RMS | 0.65810 | 15.84427 | 532.78868 | 0.000 | 0.000 / 1.000 |
| distance | 0.46960 | 7.39779 | 320.77614 | 0.000 | 0.000 / 1.000 |
| distance×phase | 0.46960 | 7.39779 | 320.77614 | 0.000 | 0.000 / 1.000 |

distance의 paired median 위치 차이는 **−0.28548m**, CI **[−0.33944, −0.00571]**, heading 차이는 **−8.61583°**, CI **[−9.29243, −8.08555]**였다. 그러나 NEES 평균 CI는 **[297.936,344.091]**로 기대값 3에서 크게 벗어났다. 최악 sample의 위치/heading은 scalar **1.51348m/20.29780°**, distance **1.18275m/10.90072°**였다. seed별 RMSE 범위·분포·coverage·covariance trace·최소 고유값을 JSON에 보존했다.

held-out innovation NIS 평균은 range **1.330→1.029**, s **7.730→17.761**이다. 작은 distance R은 관측의 가중치뿐 아니라 rejection도 늘렸다. **전체 979sample replay 구간**의 24seed 합계 s rejection은 **2134→5145**, range rejection은 **581→499**이다. 이를 held-out rejection count/rate라고 부르지 않는다. 정확도 개선 일부가 선택적 rejection에서 왔을 가능성을 남긴다. innovation 편향·자기상관도 seed별로 보존했다.

**달성 판단.** 정확도 개선과 부정확한 공분산이 공존하는 경우를 검출했다. 두 모델 모두 공동 채택 조건은 false다. 과도한 공분산도 하측 tail로 검사했지만 이 시험의 주 문제는 큰 상측 tail, 즉 과신이었다. 독립 백색 noise의 R만으로 구조적 잔차와 range–s 교차상관을 해결했다고 말할 수 없다. [STEP6_JOINT_EVALUATION.json](STEP6_JOINT_EVALUATION.json), `validation_repair.py:107,282,298`.

## 7단계 — 수정 채택과 기존 결과에 미치는 영향

**기존 방식 → 문제.** FIXED/DOC/DIAG/PARTIAL/OPEN은 대응 작업의 상태이며 측정모델의 과학적 검증 완료를 뜻하지 않는다. GSF의 PSD 수정 후에도 legacy 행은 이전 알고리즘의 결과로 남아 있다.

**이번 채택 판단.** 입력 게이트 수정은 offline 검증을 갖춘 구현으로 채택 가능하다. 조건부 table은 재현 가능한 진단 option으로 보존하지만 default scalar를 바꾸지 않고 과학적 측정모델로 채택하지 않는다. 기존 full RF 관측+LoS-only LUT와 v1 open-loop probe를 설계 오류로 재분류하지 않는다. 그 검증 미달과 적용 범위를 보고한다.

| 대상 | 구현 상태 | 검증 실행 | 가설/지적의 재판정 | 채택 |
|---|---|---|---|---|
| 게이트 빈 집합·G4 완전성 | 수정 완료 | offline 회귀 완료, 실제 RF 미실행 | M01 해결, M02 코드 계약 정합 | 입력 검증으로 채택 |
| 모델 일치 대조 | 신규 진단 구현 완료 | 200seed+scalar200회 완료 | 제한 EKF 일관성 지지 | 검증 방법으로 보존 |
| F01 L1/L2 | 기존 모델 변경 없음 | 원본 FAIL 확인, 독립 재실행 불가 | 미해결·재검증 미완료 | scientific PASS 불가 |
| F02 공분산 | optional R 비교만 구현 | 2×2/held-out 완료 | 미해결, 정확도 개선으로 해소되지 않음 | 조건부 R의 과학적 채택 보류 |
| F06 보정/평가 혼재 | 고정 split 신규 구현 | 동일 route 안에서 실행 완료 | 부분 해결, 다른 route 미검증 | 제한 진단만 사용 |
| F07 gyro/wheel | legacy 수식 변경 없음 | 수식/교차cov 진단 | 미해결, 주요인 비율 UNKNOWN | 인과 단정하지 않음 |
| F08 GSF PSD | 기존 수정 유지 | 관련 회귀+최소 재계산 | PSD 결함 수정 확인, 기존 결과 갱신은 부분 | 알고리즘 수정 유지 |
| phase/편파 조건 | 세계좌표 phase 정의 | 유효한 다중 phase 비교 불가 | PHASE_EFFECT_NOT_IDENTIFIABLE | 일반적 유효성 UNKNOWN |

F03의 사전 gate 순서·승인 시점, F04의 ray 물리 동일성·전체 set-change 원인, F05의 anchor-B 최악 조건, F09의 동일 시간 대조, F10의 전역 관측성, F12의 실제 receiver/하드웨어 유효성은 미해결/미검증이다. F11의 조건부 claim 정정은 유지하며 이번 단일 route 평가로 기존 전체 route 가설을 승격하지 않는다.

**최소 GSF 재계산.** Canonical final의 R1 CSV 4개와 routes CSV 12개, 총 72000행을 식별했다. 이전 reseed의 GSF는 각 CSV 600행, 합계 **9600행**이며 baseline은 P0/T20이다. 이 GSF 출력과 이를 인용하는 표·그림·filter 비교가 갱신 대상이지만 모든 수치가 잘못됐다고 단정하지 않는다. 직접적인 수정 영향은 GSF 행이며 다른 filter 결과를 자동 무효화하지 않는다.

stage7 plan 기록 후 저장 H로 재현할 수 있는 R2-A-m0/low drift/SNR30/seed0의 P0/T20 **GSF 2행만** 원 실험의 sensor stream/prior 설정으로 재계산했다. EKF 2행도 대응 확인에 사용했다.

| GSF | heading RMSE 이전→수정 [°] | 위치 RMSE 이전→수정 [m] | NEES 이전→수정 |
|---|---|---|---|
| P0 | 6.71979→6.93253 | 1.04572→1.05494 | 78.66243→75.34226 |
| T20 | 5.21260→5.19466 | 0.62206→0.61880 | 57.59043→57.13460 |

PSD 수정이 항상 정확도를 높이지는 않는다. 두 결과 모두 공분산 문제가 남는다. P0 EKF의 이전 값과의 heading 차이는 약 2.27e-5°로 이전 독립 audit replay에서 관측한 차이와 같은 수준이며 bit-identical이라고 말하지 않는다. T20 EKF는 반올림 수준에서 일치했다. 원본 결과를 덮어쓰지 않고 [STEP7_GSF_IMPACT.json](STEP7_GSF_IMPACT.json)에 new/legacy/delta와 16개 CSV hash를 보존했다. 나머지 9598 GSF 행은 재계산하지 않았다. 선택 H 이외의 R1/R2/R4/R5×A/B×mount 원본이 필요하며 전체 RF 재생성을 시작할 근거는 없다.

## 실행·검증·보존 기록

실행 순서는 1→2→3→4→5→6→7이다. 주요 명령은 모두 위 checkout에서 실행했다.

```powershell
py -3.10 -m pytest tests/test_parity_gate_coverage.py tests/test_parity_gate_inputs.py -q
py -3.10 scripts/drive_sim/validation_repair.py prepare
py -3.10 scripts/drive_sim/validation_repair.py 2
py -3.10 scripts/drive_sim/validation_repair.py 3
py -3.10 scripts/drive_sim/validation_repair.py 4
py -3.10 scripts/drive_sim/validation_repair.py 5
py -3.10 scripts/drive_sim/validation_repair.py 6
py -3.10 scripts/drive_sim/validation_repair_adoption.py
py -3.10 scripts/drive_sim/validation_repair.py preserve
```

2–6의 각 receipt는 시작/종료 UTC, revision, command, exit 0, 실행 source SHA를 담는다. 입력 manifest 시작 UTC는 2026-10-08 06:50:43, KST 15:50:43이다. stage2 후 집계 변경은 정확한 hash 일치로 이전 source를 복원해 추적했다. stage7 초회는 receipt의 Windows 경로 구분자로 인한 KeyError/exit 1에서 GSF 실행 전에 멈췄다. 경로 읽기를 정규화한 후 재실행/exit 0을 확인했다. 실행 실패를 숨기거나 과학적 FAIL을 PASS로 바꾸지 않았다.

관련 회귀검사는 게이트·GSF PSD·filter·LUT·관측·experiment·새 uncertainty에서 **62 passed**, sensor/first-path에서 **11 passed**, 합계 **73 passed**다. 첫 10건은 62건에 포함돼 중복 가산하지 않았다. 전체 project test는 실행하지 않았다. shell 호출 수정은 차이로 확인했으며 shell/RF production은 실행하지 않았다. `git diff --check` 성공. 읽기 전용 독립 review의 필수 지적(phase 미식별, count 범위, source 추적, block 표기)은 본문과 보충 기록에 반영했다.

원래 tracked DRIVE_SIM 결과 **447파일**의 실제 파일 SHA를 시작 전후로 비교해 변경 0건을 확인했다. 원본 prereg·amendments·audit 보고서·결과를 보존했다. 독립 audit checkout은 읽기 전용으로 사용했고 선택 원본에도 쓰지 않았다. 파일 이동·삭제는 없다. Windows CRLF와 Git LF 차이는 raw와 canonical hash로 구분했다. [PRESERVATION_CHECK.json](PRESERVATION_CHECK.json), [PROTECTED_INPUT_HASHES.json](PROTECTED_INPUT_HASHES.json).

변경 파일은 `parity_gate.py`, `run_rf_snowball.sh`, `filters.py`다. 추가 파일은 `uncertainty.py`, `validation_repair.py`, `validation_repair_adoption.py`, `validation_repair_finalize_checks.py`, 두 test 파일 및 이 디렉터리의 계획·receipt·JSON·CSV·보고서다. optional table은 direct EKF에만 제한하며 미지원 GSF/UKF/IEKF에 지정하면 명시적으로 오류를 반환한다. legacy default 수치는 바꾸지 않는다. 코드/산출물의 최종 SHA는 [FINAL_OUTPUT_MANIFEST.json](FINAL_OUTPUT_MANIFEST.json), 최종 검사 기록은 [FINAL_CHECKS.json](FINAL_CHECKS.json)에 있다.

## 미실행 항목과 필요한 다음 증거

1. **L1 독립 재검증/거리·tap 분리:** SHA 확인 가능한 실제 LP±45 bank 2개(각 약 248MB)를 재사용해야 한다. 고정 각도 500개의 direct 평가와 selected pose 거리 비교는 CPU로 제한 실행할 수 있다. bank 확보 이외에 대규모 RF 생성은 필요 없다. 소요 시간은 환경 미확인으로 UNKNOWN이다.
2. **L2/LoS↔full RF 분리:** 같은 pose/frequency/chain의 저장 LoS-only H를 우선 확보한다. 없으면 원래 L2 seed20261007/8pose×257bin, max_depth=0의 제한 Sionna 실행과 selected pose subset이 후보이다. 원 run guide의 약 5분은 환경 의존 참고값이며 이번에 측정한 비용이 아니다. 추가 계산은 이번에 실행하지 않았다.
3. **실제 G4와 anchor-B 최악 위치:** 원 manifest, A receipt/H, 대응 Jones trace, 검증 bank가 필요하다. 저장 원본으로 평가할 수 있으면 새 RF는 필요 없다. 원 입력 부족을 합성 fixture PASS로 대체하지 않는다.
4. **독립 조건 일반화/phase 식별:** R1 또는 별도 route를 보정, R2/R4/R5를 평가로 고정하고 anchor/mount도 분리할 실제 H가 필요하다. 각 phase cell의 지원과 시간 상관을 평가하기 전에는 편파 관련 조건의 유효성을 주장할 수 없다. 추가 24seed CPU 평가는 제한 가능하지만 현재 입력 부족으로 미실행이다.
5. **F02/F07:** range–s 교차상관, 시간 상관, 공유 gyro, wheel 근사를 포함한 후보에는 별도 모델 일치 대조군이 필요하다. 이번 정확도 개선만을 이유로 상태 확장이나 noise tuning을 채택하지 않는다.
6. **전체 legacy GSF 갱신:** 위 부족 H를 재사용한 9598행 CPU replay와 GSF를 인용하는 표/그림만이 대상이다. 전체 RF 생성이나 72000행의 무조건 재계산은 시작하지 않는다.

본 작업의 완료는 7단계의 변경·실행·미실행 이유와 필요한 증거를 기록했다는 뜻이다. 구현 수정 완료, 검증 실행 완료, 가설 지지, 과학적 채택은 나눠 판정했다. F01/F02 미해결, phase 효과 미식별, 독립 route 미검증을 유지하고 종료한다.
