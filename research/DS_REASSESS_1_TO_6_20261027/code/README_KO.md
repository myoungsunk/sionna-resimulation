# Δs–Range–Heading 재진단: 독립 코드 패키지 v1.0

**목적:** 기존 `myoungsunk/sionna-resimulation`, `research/ds-x1-x2-results-20261026`, 고정 증거 커밋 `2ee731336fc2b37ffcd67f96a07bdaf3dccc2898` 기반으로 단계 1–6의 원인을 분리하는 코드를 제공한다. **여기에 실제 RF 실험 결과는 없다.** 새로운 논문 결론이나 성능 개선을 주장하지 않는다.

## 0. 중요한 구분

- **새로 작성함:** 비선형 4상태 EKF 전파/갱신, 5상태 range bias 확장, Joseph covariance, 고정 mask replay, 통계 검산, 정보행렬, 앵커 배치 진단, FP transition 검사, 실행·해시·판정 로직.
- **의도적으로 동결하여 사용함:** 원래 `SourceFFD` 복소 FFD/FP 관측 물리 모델, 원래 gyro/odom 합성 입력 생성기 `build_positive_bias_controls`, 기존 EX/EXDS HGB 예측값, E1 NPZ, POWER 평균/분산과 기존 수용 mask `A_B`. 이 부분까지 무단 재작성하면 과거 결과와의 인과 비교가 무효가 될 수 있다.
- **금지:** 타깃 GT를 비오라클 온라인 관측/게이트/캘리브레이션 결정에 사용하기. 가상의 앵커에서 현재 RF 관측값을 재사용하기. 테스트 패킷의 오차를 사용해 자기 `R`을 보정하기. B0/L2를 독립 RF 두 번으로 세기.
- **의도적으로 고정한 기준:** `t>=30s`, 동일 source E1 mask, 원래 FFD 보간/검출, 원래 `B_OLD`, 원래 센서 제어 seed, 원래 `R` (별도 stage 3 제외), 원래 `Q` (명시된 stage 6 제외).

## 1. 설치 요구사항

1. Git 작업 복제본: **필요한 Git LFS 객체가 모두 materialize** 된 증거 커밋 `2ee7313` 또는 이를 포함하는 브랜치의 체크아웃.
2. 원본 동결 snapshot `D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2`, 그리고 옆의 `p2_artifacts`, `BANK_MANIFEST.json`, `LP_plus45_bank.npz`, `LP_minus45_bank.npz`. 원래 실행의 정확한 snapshot을 요구한다. 이름만 비슷한 최신 모델이나 bank로 조용히 대체하지 않는다.
3. Python 3.13 및 `requirements.txt`의 원래 수치 패키지 버전 권장. `pytest` 테스트는 현재 환경에서 별도 검증한다.
4. 출력 폴더는 **원본 Git 체크아웃 / p2 / p2_artifacts 외부의 새 폴더**여야 한다. 그 폴더의 같은 stage 이름이 이미 존재하면 덮어쓰지 않고 중단한다.

동결된 전체 입력 자산이 없으면 코드가 시작 전 또는 일치성 검사에서 실패하는 것이 정상이다. 원래 snapshot은 Git 저장소 전체와 다를 수 있다. `--skip-source-hash`는 안전성을 낮추므로 재현 검증에서는 사용하지 말 것.

### Windows PowerShell 예시

패키지를 원하는 경로에 압축 해제한 뒤 그 디렉터리에서 실행:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q tests

$Repo = 'D:\SLAM_bot\sionna-resimulation'
$Frozen = 'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849'
$Out = 'D:\SLAM_bot\DS_REASSESS_RUN_20261027'
$Inputs = @(
  '--repo-root', $Repo,
  '--source-root', "$Frozen\p2",
  '--artifacts-root', "$Frozen\p2_artifacts",
  '--output-root', $Out
)

python .\run.py @Inputs --step preflight
python .\run.py @Inputs --step 1
python .\run.py @Inputs --step 2
python .\run.py @Inputs --step 3
python .\run.py @Inputs --step 4
python .\run.py @Inputs --step 5
python .\run.py @Inputs --step 6
```

위 경로 세 개는 **예시**이며 현재 사용자의 실제 로컬 파일 존재 여부는 검증되지 않았다. `run_windows.ps1`에는 같은 절차가 들어 있다. 모든 단계를 한번에 실행하려면 `--step all`을 쓸 수 있지만, 처음에는 단계별 출력 확인을 권장한다.

부분 사례 검사: `--cases primary --biases B0` (단, Stage 3의 held-route R 보정은 Stage 2에 R2/R4/R5 세 route 데이터가 있어야 한다. 따라서 **Stage 2만큼은 기본 all 케이스로 실행하는 것이 안전**하다). default는 7 case × B0/L2.

### Linux Bash 예시

```bash
python -m pip install -r requirements.txt
export DS_REPO_ROOT=/work/sionna-resimulation
export DS_SOURCE_ROOT=/work/execution_33e9849/p2
export DS_ARTIFACTS_ROOT=/work/execution_33e9849/p2_artifacts
export DS_OUTPUT_ROOT=/work/DS_REASSESS_RUN_20261027
bash run_linux.sh
```

## 2. 단계별 입출력

| Step | 수행 | 주요 결과 | 과학적으로 허용되는 해석 |
|---|---|---|---|
| 1 `01_range` | 동결 mask에서 BASE / EX / EXDS / range GT oracle replay | `SCORES.csv`, `HEADING_CONTRASTS.csv`, `PREDICTION_DECOMPOSITION.csv`, arm별 NPZ | EX/EXDS를 혼동하지 않고 점진적 보정 효과 비교. EXDS−EX는 모델간 비교지 Δs의 무작위 인과 효과 아님 |
| 2 `02_residuals` | 원래 Full Sionna CIR에서 FP tap 재산출, GT measurement error, 잔차 평균/공분산/시차/블록 bootstrap | `RESIDUALS.csv.gz`, `RESIDUAL_STATS.csv`, `MEASURED_FP_SHIFT_STRATA.csv` | 보정 후 평균·분산·교차 공분산의 오지정 가능성 탐색. 측정 tap과 모델 tap 구분 |
| 3 `03_RF_R_H` | R2/R4/R5 route-heldout B0 기반 R 추정 (기본 R과 shrink), 4-state replay, FFD analytic vs FD H | `SCORES.csv`, `LORO_COVARIANCE.csv`, `FFD_FINITE_DIFFERENCE.csv` | R 변경이 나쁜지/좋은지 **절대 RMSE와 BB 비악화**로 판단. FD 불연속은 H 버그와 구분 |
| 4 `04_CUT_RT_factorial` | prior/GT tangent 축 × 첫 통과/전체 적용 2×2 동일 평가창 | `SAME_WINDOW_GAP_REDUCTIONS.csv`, `SCORES.csv`, `GEOMETRY_SERIES.csv.gz` | 정의가 다른 기존 CUT_RT 수치를 한 표에서 혼용하지 않기. GT는 oracle |
| 5 `05_full_observability` | F 포함 4/5-state 누적 Fisher, RANGE_ONLY vs RANGE_PLUS_POL, GT/prior linearization, data-only/prior-aided | `FULL_STATE_FISHER.csv` | rank 및 약한 고유모드 확인. 독립 packet Gaussian 가정이므로 낙관적인 정보 상한에 가까움 |
| 6 `06_layout_bias_Q` | 실제 RF 생성 **없이** range-only 앵커 relocation/addition Fisher, 별도로 기존 RF를 이용한 5-state range bias + 통과 후 tangent Q replay | `LAYOUT_GEOMETRY_ONLY_FISHER.csv`, `SCORES.csv`, `BIAS_STATE_Q_TRIGGER.csv` | 가상 앵커 RMSE를 주장 금지. 5-state 성능은 원래 RF에서만 평가 |

## 3. 필수 QA와 실패 처리

- **Stage 1**, 그리고 재귀 경로를 재사용하는 Stage 3/4/6의 OFF arm은 E1 `A0/A1`의 `x/P/prior/Pprior/h/H/K/nu/mu/R/acc`를 각 조건 **절대오차 1e-10, rtol=0**로 맞추지 못하면 FAIL. 실패 시 새 실험 결론을 읽지 말 것.
- Stage 2 원시 CIR의 포트 첫 경로 편파비를 재계산해 저장 `z_s`와 1e-9 이내 확인. 가공된 모델 FP tap은 실제 measured FP tap과 다른 열로 저장.
- 모든 고정 `A_B` 거절은 `x+/P+ == prior/Pprior` 정확. 공분산 대칭·PSD, Joseph 갱신, range tangent projection 모두 검사.
- 이전 단계 `RUN_STATUS.json` 미존재/미완료 시 필요한 후속 단계 중단. Stage 3의 Stage 2 residual CSV SHA가 달라지면 중단.
- `OUTPUT_SHA256.json`은 기존 내용을 overwrite하지 않으며 stage의 체크·출력 파일을 기록한다. `RUN_STATUS.json`의 code SHA와 input SHA로 재현 근거를 기록한다.
- `RUN_STATUS.json`의 `CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION`은 수치/코드 단계 완료일 뿐 특정 기전이 증명되었다는 뜻이 아니다.
- 실패 시 stage 폴더에 `RUN_FAILURE.json`; 같은 폴더에 재실행하여 덮어쓸 수 없다. 원인 해결 후 **새 output-root**를 쓰거나 실패한 새 stage 디렉터리만 별도 백업/이동하고 실행한다. 원본 E1/결과는 절대 삭제하지 않는다.

## 4. 사전등록 판정 원칙

Primary는 3 case 그룹 `R2_aA_m45`, `R4_aA_m0`, `R4_aB_m0`이고 route ID는 R2/R4 두 개뿐이다. B0/L2는 같은 RF의 쌍. 평가 구간(전체 `t>=30`, 첫 pass post)은 반드시 별도 열로 유지한다. 결과를 검토할 때:

1. **절대 Heading RMSE** 및 signed bias와 std가 모두 유효한지, 교정된 range error/XY/NEES가 어떻게 변했는지 점검한다.
2. Arm-gap이 줄어도 BB 자체가 10% 이상 악화하면 채택하지 않는다. Gap 감소는 인과 매개 비율/배포 이득이 아니다.
3. 타깃 경로에서 학습한 R, GT axis CUT, ideal new-anchor range는 각각 배포 가능성이 없는 진단이다.
4. Stage 5는 각 윈도우의 GT 또는 BB prior **시작 상태 하나만** 사용하고, 이후 동결 odometry를 연속 적분한 일관된 명목 궤적에서 FFD/Fisher를 평가한다. 매 패킷 GT·posterior를 연결하면 range-only 회전 null이 인위적으로 깨지므로 금지한다. 정보행렬 스케일 의존성도 고려한다: 상태 스케일은 `diag(1m,1m,5deg,.1deg/s,[.1m])`. 판정에서 null target 투영이 있으면 `sigma_terminal_tan_cm=inf`, 이를 finite 값으로 치환하지 않는다.
5. Stage 6 가상 앵커는 기존 Sionna 환경의 다중경로를 재계산하지 않았으므로 위치/Heading RMSE 예측은 **금지**된다. 추가 range가 기존 range/편파 오차와 독립이라는 가정의 영향도 실측으로 확인해야 한다.

자세한 문제점·수정 이유는 `IMPLEMENTATION_AUDIT_KO.md`를 참고한다.

## 5. 코드 구성

- `run.py`: 단일 CLI, 순차 단계/선행 QA guard
- `dsreassess/io.py`: LFS/파일 hash, 원래 EX residual 복원, frozen bank/source bootstrap, raw Full CIR detector, source/source output isolation
- `dsreassess/numerics.py`: 새로운 4D/5D motion EKF algebra/Joseph update/PSD, Tangent Q
- `dsreassess/engine.py`: masked replay/오라클 분리/정량 score/시계열/동일성 검사
- `dsreassess/stage12.py`: Step 1/2
- `dsreassess/stage34.py`: Step 3/4
- `dsreassess/observability.py`: dynamic transition F accumulation, rank/null/gauge, state-scale
- `dsreassess/stage56.py`: Step 5/6
- `tests/`: 독립 합성 데이터 수치·6단계 smoke test

## 6. 현재 검증 범위

작성 환경에서 `compileall`과 `pytest` 합성 테스트 **8개**가 통과했다. **실제 E1/Sionna 원본 데이터 replay 및 기준 `1e-10`의 runtime parity는 수행하지 않았다.** 사용자 로컬 frozen 소스·bank·LFS 원본을 연결하여 `preflight` 및 Stage 1을 실행해야 한다. 실제 수치가 다르면 재실행 실패로 중단하고 `RUN_FAILURE.json`을 검토한다. 이 한계를 제거한 것처럼 표현하거나 실험을 이미 진행했다고 주장하지 않는다.
