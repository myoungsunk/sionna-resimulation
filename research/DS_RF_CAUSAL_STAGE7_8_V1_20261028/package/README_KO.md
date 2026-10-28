# RF–편파 인과 검증 Stage 7–8: 직접 실행 패키지

**기준:** `myoungsunk/sionna-resimulation`, 정확한 Git SHA `4d2414a7238176b6e116cae2d10546e724b66b8d`.

**산출물:** (1) 실제 Git checkout에 적용할 **신규 파일 3개만 추가하는 독립형 패치**, (2) 원본을 보존하는 설치기, (3) Windows 실행기, (4) 테스트, (5) 과학적 판정 규칙. 기존 `4d2414a` `engine.py`/`io.py`/`run.py`, E1, Q/R, SourceFFD, 마스크, 학습, 1–6단계 결과를 수정하지 않습니다.

## 중요한 해석 경계

- 두 실험 모두 **GT를 아는 오라클 개입**입니다. 실제 배포 가능한 알고리즘 성능을 입증하지 않습니다.
- Stage 7은 **원래 4상태 EKF를 통째로 재귀 실행**하여 원래의 고정 `A_B` 수용 mask를 보존합니다. `z, R, Q, controls, SourceFFD`는 동일합니다. `mu_r`/`mu_s`의 복사본만 바꿉니다.
- Stage 8은 **첫 앵커 통과 종료 시점의 posterior x/P**를 서로 다른 원본 Arm에서 가져와, 그 뒤 60초를 동일한 측정과 평균 보정으로 재귀 실행합니다. 서로 다른 x/P를 섞은 Arm은 물리적으로 자연스럽게 관측된 state가 아닌 진단 개입입니다.
- 데이터는 R2/R4/R5의 7 case × B0/L2. **B0/L2는 동일 RF를 재사용한 쌍입니다.** 14개의 독립 RF 데이터로 계산하지 않습니다.
- 이번에 새롭게 제시된 LOS/Full 분리나 느린 오차 oracle 결과 자체를 *검증한 패키지*가 아닙니다. GT Full residual과 고정 SourceFFD를 이용해 명시된 가설을 **새로 검증**합니다.

## 설치 및 실행 (Windows PowerShell)

먼저 Git checkout이 정확히 `4d2414a`인지 확인하고, Git LFS를 가져옵니다. 이전 작업의 원본 `p2`, `p2_artifacts` 위치를 그대로 사용합니다. 결과 폴더와 복사할 코드 폴더는 둘 다 **처음부터 존재하지 않는 새 경로**여야 합니다.

```powershell
# 압축 해제한 폴더에서 실행. 경로는 사용자 PC에 맞게 변경
$PatchDir = 'D:\SLAM_bot\RF_CAUSAL_7_8_PATCH_EXTRACTED'
$Repo     = 'D:\SLAM_bot\DS_REASSESS_GITHUB_4d2414a'
$Source   = 'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2'
$Art      = 'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2_artifacts'
$CodeOut  = 'D:\SLAM_bot\RF_CAUSAL_7_8_V1_CODE'
$Out      = 'D:\SLAM_bot\RF_CAUSAL_7_8_V1_RESULTS'

# 먼저 실제 원격 SHA 확인. 별도 새 checkout을 사용하세요.
git -C $Repo rev-parse HEAD
# 정확히 4d2414a7238176b6e116cae2d10546e724b66b8d 이어야 함.
# Git LFS 파일을 갖추지 않은 경우: git -C $Repo lfs pull

& "$PatchDir\RUN_ALL_ONCE.ps1" `
  -RepoRoot $Repo -SourceRoot $Source -ArtifactsRoot $Art `
  -CodeOut $CodeOut -OutputRoot $Out -PythonExe 'python' `
  -Cases 'all' -Biases 'B0,L2'
```

실행 정책으로 `.ps1`이 차단된 PC에서는 파일 수정 없이 다음을 사용할 수 있습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PatchDir\RUN_ALL_ONCE.ps1" `
  -RepoRoot $Repo -SourceRoot $Source -ArtifactsRoot $Art `
  -CodeOut $CodeOut -OutputRoot $Out -PythonExe 'python' `
  -Cases 'all' -Biases 'B0,L2'
```

필요한 Python 패키지는 **기존 실행본과 동일**합니다. 권장: 기존에 검증된 `.venv\Scripts\python.exe`를 `-PythonExe`에 지정합니다. `pytest`, `numpy`, `pandas`가 설치돼 있어야 합니다.

### 실행기가 순서대로 하는 작업

1. `VERIFY_PACKAGE.py`: 전달 ZIP 파일의 SHA256 검사.
2. `APPLY_PATCH.py`: Git HEAD와 `PATCH_V2_FINAL.json`, 핵심 소스 10개 SHA 대조 후, **새 CodeOut에만** `4d2414a/code`를 복사하고 신규 3파일을 삽입; 복사본 Python 파일 SHA lock 생성.
3. `--step preflight`: frozen source와 E1 원본 해시 검증, SourceFFD bank·첫 통과 정보 검증. 실제 실험 실행 없음.
4. `--step all`: Stage 7 → 해시·parity 검증 → Stage 8 → 해시·parity 검증.
5. `--step verify`: 두 결과 디렉터리·SHA·QA 및 최종 영수증 재검증.

**재시도 정책:** 실행 중 실패하면 완료 상태를 위조하거나 결과 폴더를 덮어쓰지 않습니다. 기존 실패 폴더를 보존하고, 완전히 새로운 `CodeOut`/`OutputRoot`를 사용합니다. Stage 7만 완전 PASS 후 Stage 8에서 실패한 경우에는 원본 성공 Stage 7 디렉터리·영수증이 그대로라면 **기존 CodeOut을 이용해 Stage 8만 새 환경에서 재실행**할 수 있으나, 실패 Stage 8 폴더는 새 OutputRoot를 쓰거나 명시적으로 별도 복사·복구하여야 하므로 임의 삭제하지 마십시오.

## Stage 7: 느린 Range 오차와 편파 오차의 2×2 개입

관측모델: `z = h(x) + mu + residual`. GT에서 원래 BASE range 잔차 `e_r,B=z_r-h_r(GT)-mu_r,B`, 편파 잔차 `e_s=z_s-h_s(GT)-mu_s`를 얻습니다. *GT는 개입의 목표 생성에만 사용합니다*. Filter가 보는 source prediction / R / gate는 그대로입니다.

**시간 분리:** 기존 첫 통과 episode `[start_s,end_s]`에 ±10초를 붙인 구간에서 BASE `e_r,B`에 **중심 정렬된 2초**(±1초) 이동 평균 `L_r`을 적용합니다. 해당 구간 안의 Range 느린 오차 제거 Arm은 `mu_r'=mu_r,B+L_r`; 구간 밖은 원래 BASE입니다. 이 실험은 미래 GT를 이용하는 offline 진단입니다.

- **A:** BASE Range + 원래 편파 오차 → `BASE__POL_REAL`
- **B:** BASE Range + 편파 전체 oracle → `BASE__POL_CLEAN` (`mu_s'=z_s-h_s(GT)`)
- **C:** BASE Range 느린 잔차 제거 + 원래 편파 → `NO_SLOW_R__POL_REAL`
- **D:** BASE Range 느린 잔차 제거 + 편파 oracle → `NO_SLOW_R__POL_CLEAN`

모든 기준에서 `Y`를 heading **signed bias**, heading RMSE, XY RMSE, anchor range RMSE, heading NEES로 각각 계산합니다.

`interaction = Y_A - Y_B - Y_C + Y_D`

이는 고정된 오라클 개입 사이의 **차이의 차이**이며, 독립 매개 인과율이나 오차 분해의 유일성을 입증하는 수치는 아닙니다.

**반드시 함께 실행할 대조군**: EXDS Range × 편파 REAL/CLEAN, 전체 Range oracle × 편파 REAL/CLEAN, 편파 잔차의 중심정렬 5초 느린 성분만 유지/빠른 성분만 유지, 첫 통과 core 양 채널 oracle의 BB/MB donor. 2초/5초는 결과 확인 후 변경하지 않는 사전 고정 진단 폭입니다. 가까운 경계는 해당 정의된 구간 안에서만 계산합니다.

**출력:** `07_rf_pol_factorial/SCORES.csv` (각 Arm × `scoring` / `first_pass_core` / `first_pass_extended` / `first_pass_post60`), `FACTORIAL_INTERACTIONS.csv`, `PASS_WINDOW_CONTRACT.csv`, `GT_RESIDUAL_DECOMPOSITION.csv.gz`, 15 Arm별 상세 NPZ, `CHECKS.json`, `OUTPUT_SHA256.json`, `RUN_STATUS.json`.

## Stage 8: 통과 종료 상태 × 통과 후 편파 오차

원래 GT 첫 통과의 `end_s` 직후부터 60초 (다음 통과가 있으면 그 이전까지) 재귀 추정을 계속합니다. 이때 통과 이전 출력은 frozen baseline Stage 7 NPZ에서 읽고 해시를 검사합니다.

- 첫 통과 **완료 후** 상태 donor: BASE / EXDS의 `x`.
- 공분산 donor: BASE / EXDS의 `P` (x와 독립적으로 교체).
- 통과 이후의 **동일** Range 평균 입력: BASE 또는 EXDS.
- 통과 이후의 편파: 실제 관측 / GT oracle.
- 추가 비교: 첫 통과 안에서만 r,s를 GT-oracle로 교체한 donor 2종(BB/MB).

`2×2×2×2 + 2×2×2 = 24`개 후속 Arm/조건. 원본과 동일한 x/P + post Range + original pol Arm은 **원본 full replay의 suffix를 1e-10 내에 재현해야 통과**합니다. Mixed donor는 causal localization diagnostic만입니다.

**출력:** `08_post60_handoff/POST60_HANDOFF_SCORES.csv`, `HANDOFF_STATE_P_INTERACTIONS.csv`, `EXIT_DONOR_STATES.csv`, `POST60_GAIN_LEDGER.csv.gz`, **각 Arm의 x/P/prior/Pprior/H/K/innovation/GT 및 gain 기여를 저장한 24개 시계열 NPZ/조건**, `CHECKS.json`, `OUTPUT_SHA256.json`, `RUN_STATUS.json`.

**검산:** 4-state x/P 원본 후속 재현; Q/R/mask 불변; `K_r ν_r+K_s ν_s=Kν` 갱신 분해; 동일 시점의 반경·접선 제곱 RMS 분해와 XY RMSE 일치; 모든 입력·산출물 해시. Gain ledger의 `K_r nu_r`/`K_s nu_s`는 갱신 시점의 직접 기여이며 전체 후속 재귀적 매개 효과와 같지 않습니다.

## 결과 읽기 및 사전 판정

- **최종 기술 QA**: `$Out\CAUSAL_FINAL_QA.json`이 `TECHNICAL_QA_PASS_NOT_SCIENTIFIC_CAUSAL_PROOF`이고 두 Stage의 CHECKS 및 NPZ 해시를 모두 검증해야 합니다. 실패 또는 `CAUSAL_STAGE7.json` 하나만 있으면 최종 성립하지 않습니다.
- **공통 gate**: 모든 case의 E1 OFF/EXDS parity ≤`1e-10`, original mask/R/Q/controls 불변, GT oracle 잔차 ≤`3e-12` (계산기오차), suffix parity ≤`1e-10`, 7 case × B0/L2 전체 결과.
- **물리적 원인**: 편파 oracle 성능 개선이 재현되어도 이 개입만으로 반사 경로별 기여율·현실 보정기 성능·다른 환경으로의 일반화는 입증되지 않습니다.
- **상쇄 가설**: signed bias interaction `Y_A-Y_B-Y_C+Y_D`를 B0/L2 쌍에서 같은 부호인지 확인하고, 개별 Range 변동의 방향과 크기를 함께 검토합니다. **유의성·검정력·효과 기준을 사후에 정하지 않습니다.** 표본은 3개 독립 주 route 수준이며 추론 통계를 주장하지 않습니다.
- **통과/이후 분리**: Stage 8에서 *같은 post Range/편파* 아래 상태 donor만 교체한 경우, *같은 exit donor* 아래 post 편파만 교체한 경우를 각각 비교하고, x/P 교차항 및 GT-clean pass donor를 점검합니다. 이를 확인하지 않고 모든 오차를 통과 상태 또는 원거리 편파로 단정하지 않습니다.
- **실제 개선 후보의 채택**: Heading RMSE 절대값뿐 아니라 XY RMSE, anchor range RMSE, Heading NEES, BB 대비 10% 이상 악화 여부를 함께 판정해야 합니다. 이번 단계는 오라클/반사 물리 진단이지 온라인 알고리즘의 채택 실험이 아닙니다.

### GitHub에 올릴 때

새 브랜치/새 결과 디렉터리를 사용합니다. 원본 `research/DS_REASSESS_STAGE235_V21_20261028`와 지난 1–6 결과에 overwrite하지 마십시오. `CodeOut`, `OutputRoot`, `CAUSAL_FINAL_QA.json`, 체크섬, 결과 NPZ 및 로그를 **새로 만든 경로**에 넣고 푸시하십시오. 대용량 NPZ는 LFS 추적을 확인합니다. 패치 작성 단계에서 커밋·푸시·실제 RF 실험은 수행하지 않았습니다.

## 필요 조건 / 알려진 한계

1. 원본 Git checkout은 `4d2414a` SHA 정확히 고정; 다른 HEAD는 실패합니다.
2. frozen p2 source, bank, E1 LFS NPZ, GT/odometry, `P2_PASSES_GT.csv` 및 4d의 원본 검증 파일 필요.
3. 기존 E1 reference와 SourceFFD의 의미가 유지되는 4상태 EKF만 지원; covariances are 4×4. `B0/L2` 쌍을 독립 표본으로 취급하지 않음.
4. **코드 실행을 동반한 실제 RF 독립 재현은 사용자 환경에서 수행해야 합니다.** 본 전달물 자체는 합성 계약 시험과 구문/적용 검증까지만 포함합니다.
