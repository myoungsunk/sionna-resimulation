# D7.1 및 G1-MODEL-003 v3 consider 검산

2026-11-15 · DIAGNOSTIC_ONLY

D7.1 동결 커밋은 6cc0a6dd4515f313690aa74be9777508ad918e05이다. 검산에 사용한 diag_jc.py의 Git blob 505893a2a61a622c8b344cad7b63fffe90ae58ab는 게시 커밋과 일치한다. 별도 v3 구현은 22e1cfc7f8abd4357f0ed9a2c40cf60c6c82b6c2에서 확인했다. 실제로 불러온 v3 소스 6개의 SHA-256을 results_v3.json에 기록했다.

## Schmidt 공분산 검산

동결 D7 갱신을 독립 블록식과 비교했다. 2개 consider 상태를 포함한 6차 상태, 비대각 측정 공분산, 16개 갱신 중 채택 12개·기각 4개 조건에서 갱신 평균의 최대 절대차는 2.03e-16, 전체 P는 3.90e-18, 활성–consider 교차공분산은 4.34e-19, NIS는 0이다. 채택된 갱신에서 교차공분산은 변했고 consider 평균과 P_cc는 고정됐다. 보고에 사용한 물리 상태 P는 이 증강 갱신이 끝난 뒤의 주변 공분산이다. [NASA Navigation Filter Best Practices §8.4.1](https://ntrs.nasa.gov/api/citations/20250002787/downloads/20250002787.pdf?attachment=true)

## 상수 편향 합성 시험

각 조건은 독립 경로 20,000개, 경로당 30 packet이다. 각 경로 안에서 consider 편향을 상수로 유지하고 경로 사이에서는 필터와 동일한 영평균 정규분포로 표집했다. D7 seed는 811007, v3 seed는 923418이다. gate-off에서 끝점 heading·XY·gyro bias의 95% 포함률이 각각 95% ±0.6%p 이내면 통과한다. gate-on은 원래 NIS 문턱을 그대로 사용했다. CI는 경로 끝점을 단위로 한 Wilson 95% 구간이다.

| 구현과 arm | gate-off heading | gate-on heading (95% CI) |
|---|---:|---:|
| D7 +K | 94.845% | 94.850% [94.535, 95.148]% |
| D7 AR 상수 한계 +K | 95.170% | 95.100% [94.792, 95.391]% |
| v3 J-V+K, R4 | 95.000% | 95.065% [94.756, 95.357]% |
| v3 J-C+K, R-MC | 95.060% | 95.145% [94.838, 95.434]% |
| v3 J-CS+K, R-MC, 5차 운동·4개 반복 site | 94.825% | 94.960% [94.648, 95.255]% |

모든 gate-off 시험이 통과했다. v3는 실제 초기화·예측·거리/편파 갱신과 checkpoint 점수식을 사용했다. 각 packet에서 consider 평균과 P_cc의 비트 일치, 활성–consider 교차공분산의 형성을 검사했다. v3 J-V+K의 gate-on XY 포함률은 94.140% [93.806, 94.457]%였다. J-CI 및 Student-t arm의 보정은 이 시험 범위 밖이다.

같은 방향 +3σ 편파 편향이 모든 경로에 고정된 스트레스 조건에서 gate-on heading 포함률은 D7 +K 21.140%, v3 J-V+K 23.225%였다. D7 +K의 이 조건에서 heading RMSE는 12.036°, 같은 합성 운동의 DR은 5.827°였다. 이 검사는 실제 RF의 편향 크기를 추정하지 않는다.

## 저장된 D7.1 B0 체크포인트 재집계

| Case | 비교 | 평균 P_ψψ (rad²) | heading 포함률 | heading RMSE |
|---|---|---:|---:|---:|
| R2_aA | JC_upper → JC_K_upper | 0.001675 → 0.003104 | 93.55% → 54.84% | 2.57° → 7.16° |
| R5_aB | JC_upper → JC_K_upper | 0.000362 → 0.001057 | 86.15% → 60.52% | 2.07° → 3.56° |
| R2_aB | JC_upper → JC_K_upper | 0.000674 → 0.002028 | 75.65% → 53.55% | 2.33° → 7.13° |
| R2_aB | JC_upper → JC_infinite | 0.000674 → 0.003183 | 75.65% → 60.65% | 2.33° → 7.68° |

이미 게시된 체크포인트별 결과로 계산했다. R2_aA와 R2_aB는 각각 620행, R5_aB는 960행이다. 각 case에서 동일 RF 경로에 센서 잡음 seed 20개를 적용했다. R2_aB의 JC_infinite는 유색 상태를 고정 consider로 바꾼 arm이고 JC_K_infinite와 동일하다. 유한 상한 +K를 비교하면 packet joint gate 기각률도 R2_aB에서 2.64%에서 19.45%로 변한다. 저장된 결과는 오차가 평균 분산 증가 폭을 앞선 점을 보여 준다. 편향, 선형화, gate 변경의 개별 인과 효과는 이 집계에서 식별되지 않는다. [D7.1 공개 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/6cc0a6dd4515f313690aa74be9777508ad918e05/research/G1_PACKET_EKF_20261114/DIAG_A/D7/REPORT_KO.md)

## 판정 범위

검사한 공분산 구현에서 누락을 발견하지 않았다. 95%는 편향의 분포와 필터 가정이 일치하는 경로 집단에 대한 결과다. +K는 고려 편향을 추정하지 않지만 물리 상태의 갱신 이득과 혁신 판정은 바꾼다. 동일 RF 경로의 조건부 포함률이나 DR 대비 RMSE에는 그 값이 보장되지 않는다.

v3 C2 편파 척도는 원래 잔차의 |e_s|에서 적합하고 C5 K_s는 5 m 창 평균의 분산에서 산정한다. 지속 편향이 두 항에 반영될 수 있다. 실제 중복량과 그 영향은 확인하지 않았다. 합성 시험은 두 편파 오차 성분을 독립적으로 생성했다. 실제 RF에서 +K만 후보로 둘 근거는 이 결과로 확보되지 않았다. v3 S3-R은 DEV_FAIL_RANGE이며 S3-J 진입은 계속 막혀 있다. S2′ STOP (FULL_6)과 Step 3 보류를 유지했다.

## 재현 기록

PowerShell에서 Windows Python 3.13.15, NumPy 2.2.4, SciPy 1.15.2를 사용했다. 저장소 루트에서 아래 명령을 실행하면 별도 임시 폴더에 재현 결과를 쓴다. D7 입력은 이미 게시된 4개 B0 case의 NPZ·JSON과 동결 소스다. 원 RF ZIP이나 FFD bank는 필요하지 않다. [D7 게시 입력 해시](../PUBLISH_MANIFEST.json)

~~~powershell
$d7 = (Resolve-Path 'research/G1_PACKET_EKF_20261114/DIAG_A/D7').Path
$audit = Join-Path $d7 'CONSIDER_CHECK_6cc0a6d'
git lfs pull --include='research/G1_PACKET_EKF_20261114/DIAG_A/D7/main/*/B0_+0.npz'

$tmp = (New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("g1-consider-" + [guid]::NewGuid()))).FullName
$run = Join-Path $tmp 'd7_run'
$code = Join-Path $tmp 'diag003_work/code'
New-Item -ItemType Directory -Force -Path "$run/evidence/main", $code | Out-Null
Copy-Item -LiteralPath "$d7/diag_jc.py" -Destination "$run/evidence/"
Copy-Item -LiteralPath "$d7/frozen_code/diag_replay.py","$d7/frozen_code/diag_mechanism.py" -Destination $code
foreach ($case in 'R2_aA_m0','R2_aB_m0','R4_aB_m0','R5_aB_m0') {
    $target = New-Item -ItemType Directory -Path "$run/evidence/main/$case"
    Copy-Item -LiteralPath "$d7/main/$case/B0_+0.json","$d7/main/$case/B0_+0.npz" -Destination $target.FullName
}
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
python "$audit/check_consider.py" $run "$tmp/d7_results.json"

git fetch origin research/g1-model003-s0-20261115
$env:GIT_LFS_SKIP_SMUDGE = '1'
git -c core.autocrlf=false worktree add --detach "$tmp/v3" 22e1cfc7f8abd4357f0ed9a2c40cf60c6c82b6c2
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
python "$audit/check_consider_v3.py" "$tmp/v3" "$tmp/v3_results.json"
~~~

v3의 첫 Windows 시도는 실행 모듈이 Windows에 없는 resource를 불러오며 종료됐다. 원본 checkpoint 점수 함수와 상수 정의를 그대로 읽도록 검산 코드를 고쳤다. 두 번째 시도는 검산 코드가 site 개수를 실수 0으로 전달해 초기화에서 종료됐다. 두 실패 로그에서 로컬 경로 접두사만 치환하고 오류와 행 번호를 보존했다. 두 성공 로그와 재현 코드, 결과 JSON은 실행 직후 파일과 바이트가 일치한다.

[SHA256SUMS](SHA256SUMS)는 게시 파일의 SHA-256이다. 결과 JSON에서 seed, 실행 조건, v3 소스 해시를 확인할 수 있다.

| 파일 | SHA-256 |
|---|---|
| check_consider.py | 1b62640b416610d677a9cd2df227611d49969b4c8139139216374b3662644bc5 |
| check_consider_v3.py | f5ad930376db2e86a32a79aa7112b8d268edc17d4abb319b515ccecc2a3f799e |
| results.json | f112e491da0c91a4aad8587f5b9214ef1ac31a33c43fc4d604a06ce433b486d3 |
| results_v3.json | f247e504e3f50b2a1cc3f4b155df24d68fabf011c6a045a20f98a072bc1a9400 |
| execution.log | d032be742af360fc9a5967f045432bc5cc35ef1f5780fc18380c8f6ae18fb39e |
| execution_v3.log | 6259a006f75364b80ca99ac15541ea8bbe4bb2dfe35d394526f341dbf8b68a4f |
| execution_v3_initial_import_failure.log | c96400aa6a74354efb7cd40a68f343859d50b7ca36a1e1028b22eb4443a83d0a |
| execution_v3_harness_type_failure.log | 7c692617b949f6128f368236121c68f31842d875adf8c4ffe96f227161ee6971 |
