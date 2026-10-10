# POST_A23 요청 보완 자료 보고서

이번 요청에 따라 이전 게시에서 빠진 자료를 실제로 확보했다. 이전 원자료와 보고서는 그대로 보존하고, 이 하위 디렉터리에 보완 자료를 추가했다. 실행 source는 `f81b42d541fdf9a37b6868d4901c2a3bb9d8090e`, 게시 기준은 `9c1492a`이다. 측정모델·Q/R·gate·prior·센서 설정을 바꾸지 않았다. 원 입력은 읽기 전용 Docker mount로 사용했다.

## A. 요청한 trace와 실제 J3 블록 인덱스

질문은 기존 동일 run의 세부 입력·상태를 seed 0–4에서 볼 수 있는가였다. 기대값은 기존 지표와 seed 0–1 trace가 변하지 않는 것이다. 15 arm × 3 drift × 5 seed = **225 run**을 동일 source·입력으로 제한 replay했다. A0 fingerprint 게이트를 먼저 대조했으며, A0·M0·S3·S8 및 모든 Q2/joint arm을 포함했다.

- [225개 trace](REPLAY_ATTEMPT2/TRACES/)
- [replay 지표 차이](REPLAY_ATTEMPT2/REPLAY_METRIC_DIFFERENCES.csv)
- [검증 결과](REPLAY_ATTEMPT2/VERIFICATION.json)
- [A0 fingerprint 재확인](REPLAY_ATTEMPT2/A0_GATE_RECHECK.json)

실제 결과: heading·위치 RMSE 및 NEES 차이 최대는 `{'heading_rmse_deg': 1.7763568394002505e-15, 'pos_rmse_m': 2.220446049250313e-16, 'nees_mean': 2.842170943040401e-14}`로 모두 1e−9 이내였다. 기존 seed 0–1의 모든 trace 배열은 NaN을 같은 위치로 취급해 정확히 일치했다. `est, cov6, err, nees, s_log, r_log, obs_s, obs_range, e_s, e_r, truth, t, gyro, ds_odom, dth_odom, keep`를 저장했다. 15개 J3 trace에는 **실제로 소비한** `block_indices`, `block_start_positions`, `block_start_indices`, `block_length`, `residual_series_length`를 추가했다. 독립 RNG 구현으로 전 인덱스가 일치함을 확인했다.

판정은 동일 실행의 계측 보완 완료이다. 원 Q2 1,200·joint 450행 및 통합 3,300행은 [기존 OUTPUT](../Q2_JOINT_L2/retrieved/OUTPUT/)에 그대로 있다. [PAIRED_CONTRASTS.csv](../Q2_JOINT_L2/PAIRED_CONTRASTS.csv)는 OUTPUT 하위가 아니라 기존 보고서 디렉터리 바로 아래에 있다. trace 추가는 원 50-seed 표본 수를 늘리는 실험이 아니므로, joint의 효과 방향이 불확정이라는 기존 결론을 자동 변경하지 않는다.

## B. L2 중간값과 호출 단위의 정확한 의미

질문은 8개 광대역 관측의 phase/tap/보간 검토에 필요한 중간값을 복원할 수 있는가였다. 원래 기대값은 저장 `s`와 원 정수 tap 규칙의 일치이다. 저장된 H·direct H·direct10 H에 독립 NumPy Hann/IFFT/30% leading-edge 계산을 적용했다.

- [8개 pose 광대역 행](BLOCK_B/BROADBAND_POSES.csv): 좌표·거리·yaw·mount, snap 전 각도와 cell 시작 각도, 3종 s, 선택 branch, 공통 선택 tap, branch별 임계 교차와 P1/P2
- [64개 인접 vertex](BLOCK_B/LUT_VERTICES.csv): pose당 8점, tap·가중치·저장/직접 vertex s
- [2,056개 주파수 호출 행](BLOCK_B/SOLVER_CALLS.csv): pose·bin·Hz·복소 H·delay 및 대응 광대역 행
- [분위수·최대 3행 및 계산 정의](BLOCK_B/VERIFICATION.json)

원 관측에는 연속 sub-tap 추정기가 없다. 요청한 tap 이하 위치는 branch별 크기가 자기 peak의 30%를 최초 교차하는 두 정수 tap 사이를 **선형 보간한 신규 오프라인 진단값**이다. `branch_subtap_offset`은 그 위치에서 최초 교차 정수 tap을 뺀 값이다. 이 값을 원 관측 또는 원 PASS/FAIL에 대입하지 않았다. LUT vertex는 원 생성기의 명시적 phi_rx 규약을 따라 계산해 저장 LUT와 1e−11 이내 일치를 확인했고, 8점 가중합도 저장 보간값과 일치했다. 극점 convention도 이 검산에서 임의로 고치지 않았다.

실제 direct–Sionna s 차이 최대는 8.56934571525e-07이며 **8개 pose별 광대역 관측**의 최대이다. 2,056 = 8 pose × 257 주파수 호출이다. per-frequency s를 만들거나 반복값을 독립 표본으로 계산하지 않았다. 원 L2 max 0.010448905755, 4/8 위반, 기준 0.005의 FAIL은 유지한다. 기존 [L2 오차 분해 표](../Q2_JOINT_L2/L2_ERROR_DECOMPOSITION.csv)와 [원 CHANNELS.npz](../Q2_JOINT_L2/retrieved/L2_ATTEMPT3/CHANNELS.npz)를 함께 사용하면 된다.

## C. 전체 timeline/pose 집합의 native LoS H

질문은 저장 full H와 같은 좌표·yaw·mount·주파수축의 LoS H를 제공할 수 있는가였다. native Sionna PathSolver를 수정하지 않고 여러 receiver를 한 scene에 넣어 계산했다. full RF 채널은 새로 생성하지 않았다. 사전 고정한 8-pose pilot의 native 단일 receiver 원자료와 native 배치 receiver 출력 차이는 복소 H·s·delay 모두 **0**이었다. [pilot 검산](BLOCK_C/PILOT_VERIFICATION.json)을 통과한 다음 요청한 7개 케이스를 실행했다.

| 케이스 | pose 수 | pose × 주파수 평가 수 |
|---|---:|---:|
| R2_aA_m0 | 1303 | 334871 |
| R2_aB_m0 | 1303 | 334871 |
| R5_aA_m0 | 1883 | 483931 |
| R5_aB_m0 | 1883 | 483931 |
| R4_aA_m0 | 922 | 236954 |
| R4_aB_m0 | 922 | 236954 |
| R2_aA_m45 | 1303 | 334871 |

각 케이스에 `BLOCK_C/H_LoS_<case>.npy`, `BLOCK_C/<case>/PATHS_LoS.npz`, `MANIFEST.json`, `SAMPLES.json`이 있다. H shape는 원본과 동일한 `[pose,257,rx2,tx2]`, RX/TX 포트 순서는 LP+45/LP−45이다. `PATHS_LoS.npz`는 모든 pose·257 bin의 native a·tau·theta_t/phi_t/theta_r/phi_r(rad)와 path count, interaction count=0을 담았다. **모든 요청 pose를 보존**했으며 P0만 골라 저장하지 않았다. `rf_poses`에 대응하는 timeline의 pose_id로 필요한 구간을 선택할 수 있다.

[FULL_RF/](BLOCK_C/FULL_RF/)에는 원본 stored H 7개를 복사했다. [INPUTS/](BLOCK_C/INPUTS/)에는 route별 전체 timeline·rf_poses, case별 S6 CSV·manifest 및 H manifest가 있다. 원본 S6는 재실행하지 않았다. frequency axis, LUT와 bank hash, source hash는 원·신규 manifest에서 추적한다. 원본 입력 해시 유지와 7개 H finite·path count=1을 확인했다. 로컬에서는 native a·tau로 H를 재합산하고 geometry delay를 별도로 검산했다. [LOCAL_VERIFICATION.json](LOCAL_VERIFICATION.json)에 전체 결과가 있다.

R2-A m0의 권장 추가 자료로 [원 Jones traces](BLOCK_C/STORED_PATH_TRACES_R2_aA/)도 제공한다. 이 자료의 `signature`는 저장 당시 image-method 대응 결과이며, native solver의 interaction face/type readback으로 승격하면 안 된다. [중심 bin의 경로별 a·tau·각도](BLOCK_D/STORED_FULL_PATHS_R2A_m0_CENTER_BIN.npz)와 [첫째·둘째 경로 지연·진폭비](BLOCK_D/FIRST_SECOND_PATH_R2A_m0_CENTER_BIN.csv)는 원 Jones trace에서 오프라인 복원했다. 1,303 pose에서 경로 합산 H와 원 stored H의 중심 bin 차이는 최대 0이다. `offsets`로 pose별 flat path를 구분한다. 이는 신규 native full RF 실행이 아니며, 중심 bin 계수라는 범위를 명시했다. 전 주파수의 원 Jones node와 presence 정보는 원 trace에 있다. native full-RF per-interaction 종류·면 정보 자체는 원본에 없으므로 제공했다고 주장하지 않는다.

판정은 요청한 대응 H 확보 및 계산·전송 검산 완료이다. 이 자료로 동일 pose의 algebraic 잔차 분해를 수행할 입력은 갖추었다. 이번에는 원인 기여율 계산, 측정모델 수정 또는 full RF 물리 정확성 인증을 수행하지 않았다.

## Native 채널 재합산의 정밀도 검산

최초 로컬 float64 재합산은 1e−12 허용오차를 만족하지 않았다. saved a·tau 배열을 높은 정밀도로 저장했더라도 native 원 연산은 complex64 계수·float32 지연을 사용했다. 로컬 NumPy 2.2.4와 pinned NumPy 2.4.6의 복소 지수 연산 차이도 구분했다. 원 dtype과 scalar 주파수 연산 순서를 복원한 독립 재합산을 pinned 환경에서 실행했으며, 7개 케이스 모두 최대 차이가 0이었다. `/opt/rt-env/bin/python /job/native_numeric_verify.py`는 exit 0으로 끝났다. 새 solver 호출은 없었다.

float64 진단 차이(최대 약 2.893e−7)는 [NATIVE_NUMERIC_VERIFICATION.json](NATIVE_NUMERIC_VERIFICATION.json)에 별도로 보존했다. 원 H나 허용오차를 변경하지 않았다. [검산 코드](native_numeric_verify.py)의 SHA256은 파일 manifest에 기록했다. 이 결과는 저장된 native 수치의 산술 검산이며 안테나·RF 물리의 정확성 인증이 아니다.

## D. pose 집합·환경·기존 G3의 한계

[G3_POSE_COMPARISON.json](BLOCK_D/G3_POSE_COMPARISON.json)은 8개 L2 좌표와 route timeline을 독립 대조한다. 저장 R2/R4/R5×A/B G3 파일의 station 수는 모두 0이다. 따라서 해당 stored PASS는 유효한 평가 집합의 통과 증거가 아니며, L2의 8개 random pose와 같은 집합이 아니다. 현재 코드를 사후 실행해 원 gate 순서를 복구했다고 주장하지 않았다. 이 자료 게시에서도 G3 chronology를 복구하지 않는다.

[RUNTIME.json](RUNTIME.json)의 image는 이전과 동일한 pinned `rt-dual-engine:s2-deps-r2-20260928`, image ID `sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`이다. native Sionna-RT 2.0.1, Mitsuba 3.8.0, DrJit 1.3.1, NumPy 2.4.6을 사용했다. CPU 4·memory 16 GiB·BLAS thread 1로 제한했다. 실제 Python/NumPy 및 image 정보를 manifest·inspect로 보존했다. Snowball은 KMS 계정만 사용했다.

## 실행·보존·남은 범위

실제 명령과 시작/종료 UTC·exit code는 [EXECUTION_ATTEMPT2.json](EXECUTION_ATTEMPT2.json), [EXTRA_EXECUTION.json](EXTRA_EXECUTION.json), [LAUNCH.json](LAUNCH.json)에 있다. 성공한 replay·B·LoS 단계는 모두 exit 0이며 단계 순서는 위 A→B→C이다. replay 2026-10-10T05:36:43.212301+00:00–2026-10-10T05:38:01.794495+00:00, B 2026-10-10T05:38:01.794879+00:00–2026-10-10T05:38:08.378794+00:00, LoS 2026-10-10T05:38:08.379229+00:00–2026-10-10T05:48:40.035802+00:00이다.

실패도 보존했다. host Python 3.6의 staging helper는 `subprocess.check_output(text=True)`에서 중단해 container 실행 전 실패했다. 기존 argv 그대로 container를 직접 시작했다. 첫 replay는 입력 resolve 전에 mount string을 전달해 필터 실행 전 중단했다. 별도 attempt2 harness에 원 resolve 절차를 적용했고 원 filter source는 바꾸지 않았다. [첫 실패 STATUS](STATUS.json), [실패 log](replay_supplement.log), [attempt2 상태](STATUS_ATTEMPT2.json)를 구분한다. wrapper 계측은 J3 소비 인덱스 기록과 동일-run trace 보존에 한정했다. clamp·jitter·noise tuning은 없다.

원격 원본은 `/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669` 및 `/home/KMS/COOL_DIJKSTRA_20261007_01a11582`, 신규 실행은 `/home/KMS/DRIVE_SIM_POST_A23_SUPPLEMENT_20261010_01a12449`이다. 원 실행·LUT·bank·사전등록·보고서는 덮어쓰지 않았다. [TRANSFER_MANIFEST.json](TRANSFER_MANIFEST.json)은 회수 원자료 바이트·SHA256, [PACKAGE_MANIFEST.json](PACKAGE_MANIFEST.json)은 게시 파일 바이트·SHA256·CSV 열/행·NPZ shape를 기록한다. 40 MiB 초과 개별 파일은 없고 모든 NPY/NPZ는 LFS pointer 없이 전체 바이트로 게시한다.

**F01/F02 OPEN, L1/L2 FAIL, scientific_PASS=false를 유지한다.** 이 보완은 요청 자료 제공이며, independent held-out, 하드웨어, G3 chronology, covariance model 해결 또는 scientific adoption의 PASS가 아니다. 이후 잔차 분해·필터 비교는 이 요청에서 자동 시작하지 않았다.
