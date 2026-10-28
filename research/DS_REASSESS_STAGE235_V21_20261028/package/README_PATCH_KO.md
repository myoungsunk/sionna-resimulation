# DS 재진단 Stage 2·3·5 수정 패치 v2.1 — 적용 및 직접 실행 설명서

## 0. 적용 대상과 불변조건

**반드시** GitHub `myoungsunk/sionna-resimulation`의 실행 커밋 `450a21fd38cf6be510d55352ae3741c8e808bc0a` 체크아웃에 사용한다. 이 커밋의 `research/DS_REASSESS_1_TO_6_20261027/code/`가 원본 기준이다. 초기 `DS_REASSESS_1_TO_6_CODE_20261027.zip`의 `io.py`는 wrap import가 빠진 **이전 버전**이므로 패치 기준으로 사용하지 않는다. `APPLY_PATCH.py`는 `450a21f`와 Python 소스 파일별 SHA-256이 일치하지 않으면 적용하지 않는다.

이 패치 실행 동안 원본 Git 저장소와 모든 기존 results, 입력 및 manifest는 **읽기 전용**이다. 패치는 `CodeOut`이라는 새 폴더의 복사본에만 적용된다. 새 실행 결과는 `OutputRoot`라는 **다른 새 외부 폴더**에 저장된다. 원래 Stage 1, 4, 6의 실행과 모든 기존 결과는 그대로 보존한다. 이번에 변경하는 것은 Stage 2의 통계, Stage 3의 공분산 모집단 비교, Stage 5의 독립 수치 검산뿐이다. 시간상관 상태 추가, 장기 인과 CUT, Q 조정은 범위 밖이다.

### 패치 파일 구성

- `STAGE235_V21_450a21f.patch`: 코드 디렉터리 기준의 통합 Git unified diff. 변경·추가 Python 파일 11개만 포함. 원본은 변경하지 않음.
- `APPLY_PATCH.py` / `APPLY_PATCH.ps1`: 원본 커밋, 기존 소스 해시를 검사한 뒤 **외부 폴더에 복사·패치·검사**. 기존 폴더를 덮어쓰지 않음.
- `RUN_VALIDATION.ps1`: 외부 복사본의 새 선택 실행기 호출.
- `RUN_ALL_ONCE.ps1`: 적용 → preflight → Stage 2/3/5 선택 실행 → 결과 검증을 연결하는 단일 PowerShell 엔트리.
- `BASELINE_PY_SHA256.json` / `PATCHED_PY_SHA256.json`: 적용 전후 모든 패키지 Python 소스의 체크섬.
- `PATCH_BUILD_QA.json`: 패치 제작측의 시험 근거.

## 1. 사전 준비

Windows PowerShell에서 기존 작업 디렉터리와 관계없이 명령을 실행할 수 있다. Python 3.13 및 기존 프로젝트 의존성(`numpy`, `pandas`, `scipy`, `scikit-learn`, `pytest`)과 Git 실행 파일이 필요하다. 미설치 시 원래 실행 코드의 `code/requirements.txt`를 사용한다.

```powershell
python -m pip install -r "D:\SLAM_bot\DS_REASSESS_GITHUB_450a21f\research\DS_REASSESS_1_TO_6_20261027\code\requirements.txt"
```

위의 `D:\SLAM_bot\DS_REASSESS_GITHUB_450a21f`는 **예시 경로**이므로 실제 원래 Git 체크아웃 경로로 바꾼다. `git rev-parse HEAD`가 위의 전체 40자리 SHA와 일치해야 한다. 원본 결과 `results/02_residuals/RESIDUALS.csv.gz`, `results/03_RF_R_H/SCORES.csv`, E1 `.npz`, Full RF 샘플 JSON과 SourceFFD bank가 접근 가능해야 한다. Git LFS를 사용하는 경우 필요한 객체를 미리 받아야 한다.

코드·결과를 다운로드한 Git 저장소가 더 새로운 HEAD에 있더라도, **오래된 파일로 억지 적용하거나 체크를 건너뛰지 말 것**. 별도 checkout/worktree를 정확한 커밋에 맞추어 사용한다.

## 2. 원클릭 실행 — 권장

ZIP을 원하는 폴더에 압축 해제하고 아래 변수 5개를 실제 디렉터리에 맞춰 설정한다. 코드와 결과 출력 위치는 **아직 존재하지 않는 새 폴더**로 지정한다. `D:\SLAM_bot\...` 경로는 이전 실행 기록을 따른 예시이며 현재 로컬에 자동으로 존재하지는 않는다.

```powershell
$PatchDir = 'D:\SLAM_bot\STAGE235_V2_PATCH_EXTRACTED'
$Repo     = 'D:\SLAM_bot\DS_REASSESS_GITHUB_450a21f'
$Source   = 'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2'
$Artifacts= 'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2_artifacts'
$CodeOut  = 'D:\SLAM_bot\DS_REASSESS_PATCH_V2_CODE'
$Output   = 'D:\SLAM_bot\DS_REASSESS_PATCH_V2_RESULTS'

& "$PatchDir\RUN_ALL_ONCE.ps1" -RepoRoot $Repo -CodeOut $CodeOut `
  -SourceRoot $Source -ArtifactsRoot $Artifacts -OutputRoot $Output
```

Windows에서 스크립트 실행 정책이 차단될 경우 현재 세션의 PowerShell 실행 정책만 임시 변경해 실행한다. 또는 `APPLY_PATCH.py`와 `run_selective.py`를 Python에서 직접 실행할 수 있다.

## 3. 단계별 실행 — 문제 분리 시

원클릭 대신 아래 순서대로 수행할 수 있다. **같은 단계를 동일 `Output`에 다시 실행하면 기존 결과 폴더가 있으므로 중단**하도록 만들었다. 실패 시 원인을 기록한 뒤 새로운 output-root를 사용한다. 원본 결과에 덮어쓰기하지 않는다.

```powershell
& "$PatchDir\APPLY_PATCH.ps1" -RepoRoot $Repo -CodeOut $CodeOut

& "$PatchDir\RUN_VALIDATION.ps1" -RepoRoot $Repo -CodeRoot $CodeOut `
  -SourceRoot $Source -ArtifactsRoot $Artifacts -OutputRoot $Output -Step preflight

& "$PatchDir\RUN_VALIDATION.ps1" -RepoRoot $Repo -CodeRoot $CodeOut `
  -SourceRoot $Source -ArtifactsRoot $Artifacts -OutputRoot $Output -Step 2

& "$PatchDir\RUN_VALIDATION.ps1" -RepoRoot $Repo -CodeRoot $CodeOut `
  -SourceRoot $Source -ArtifactsRoot $Artifacts -OutputRoot $Output -Step 3

& "$PatchDir\RUN_VALIDATION.ps1" -RepoRoot $Repo -CodeRoot $CodeOut `
  -SourceRoot $Source -ArtifactsRoot $Artifacts -OutputRoot $Output -Step 5
```

`-Step all`은 Stage 2 → Stage 3 → Stage 5만 실행한다. Stage 1·4·6은 실행하지 않는다. 변경한 `Stage 2`는 GitHub에 이미 보존된 원래 잔차 파일의 **SHA를 확인하고 그 파일을 재사용**하며, E1/Full RF의 원본 packet 위치를 매칭하여 통계만 다시 계산한다. 따라서 CIR FFT 재생성 또는 E1 재귀를 되풀이할 필요가 없다.

## 4. 강제 검산·출력 계약

| 단계 | 필수 결과 | 기술적 하드 게이트 |
|---|---|---|
| Stage 2 | `RESIDUAL_STATS.csv`, `RESIDUALS.csv.gz`, `CACHE_NATIVE_ALIGNMENT.csv`, `CACHED_INPUT_IDENTITY.json` | 450a21f 원본 캐시 SHA·E1 ID/time/mask 일치, 원본 Native RF 행 번호와 packet 순서 일치, 실제 lag-1/5 후보쌍만 집계, 8/16/32초 부트스트랩·NA 사유 존재 |
| Stage 3 | `LORO_COVARIANCE.csv`, `R_SAMPLE_CONTRASTS.csv`, `SCORES.csv`, `LEGACY_ALL_PARITY.json` | target route 제외·B0만 학습·동일 표본 내 fallback·기존 A_B 고정·E1 OFF parity ≤1e-10, 기존 ALL 모집단의 OFF/DIAG/FULL 성능 기존 원본과 ≤1e-10 일치 |
| Stage 5 | `FULL_STATE_FISHER.csv`, `FISHER_INDEPENDENT_AUDIT.csv`, `FISHER_RANK_SENSITIVITY.csv`, `H_PHI_FD_CHAIN_AUDIT.csv`, 시나리오별 `*_FISHER_AUDIT.npz` | 독립 수치미분 Phi/동역학, HΦ 타이밍·tap 안정성 구분, SVD/eigen rank 일치, Fisher PSD, 회전 null, 접선 불확실성·rank 민감도 재계산, CHECKS >0 |

Stage 2·3·5 모두 동일 코드·입력·설정으로 완료되고 누적 재검증을 통과하면 `Output/PATCH_V2_FINAL.json`의 status는 `TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION`이다. 이것은 **기술 검증 완료**를 의미하며, 가설 입증·Heading 개선 방법 채택은 별도 분석이 필요하다. 각 단계의 `OUTPUT_SHA256.json`, `CHECKS.json`, `RUN_STATUS.json`을 함께 보관한다.

### 정상적인 NA와 중단(FAIL)의 차이

8/16/32초 중 일부 블록에서 표본이 4개 미만이면 해당 블록 길이의 공분산 CI는 `NA_INSUFFICIENT_BLOCKS_OR_PACKETS`이며 정상적인 통계적 정보 부족이다. 신뢰구간 부호가 블록 길이에 따라 바뀌면 `SENSITIVE_OR_INCLUDES_ZERO`, 세 블록 길이가 충분하지 않으면 `INSUFFICIENT_8_16_32`로 표시한다. 이 정보만으로 상관성을 확정하지 않는다.

반면 E1/소스 해시 불일치, 수용 표본의 잘못된 fallback, Stage 3 기존 전체 모집단과의 parity 불일치, Stage 5 독립 수치 비교의 rank·null·감도 오차가 기준을 넘는 경우는 **실행 FAIL**이다. 이때 어떤 결과도 PASS로 보고하지 않는다.

### 기존 실험에 대한 영향

Stage 1 EX/EXDS 비교 결과와 Stage 4 CUT_RT 요인실험은 **그대로 보존**된다. Stage 6의 기존 앵커 배치 Fisher는 Stage 5에서 기초 observability 구현의 불일치가 발견된 경우에만 영향을 재검토해야 한다. Stage 6 EKF/NPA 결과를 자동으로 다시 실행하지 않는다.

## 5. 이번 패치의 한계

패치 제작 환경에서는 원래 대용량 Full RF/SourceFFD bank/E1 LFS를 직접 연결하지 못했다. 대신 **정확한 450a21f 실행 소스에 대한 Git diff 적용 검산, 패치 결과 SHA256, Python 구문 검사, 합성 회귀시험**을 수행했다. 마지막 실제 데이터 parity는 실행 환경에서 수행되는 **필수 hard gate**다. 따라서 실제 데이터로 이미 성공했다고 주장하지 않는다.

Stage 5의 비교는 동일한 SourceFFD 물리 관측모델을 사용하되, 운동 전파의 수치미분, Fisher 재구성, SVD, nullspace 투영을 독립적으로 구현한다. 이 검증이 통과하더라도 물리적 측정모델 가정의 타당성이 증명되는 것은 아니다.


## v2.1 적용 시 유의사항

- 세 수정 사항과 이번 검증의 실제 범위는 `REVIEW_FIXES_V21_KO.md`, `PATCH_BUILD_QA.json`, `SYNTHETIC_TESTS_V21.log`를 참조한다.
- 이 패치는 원래 450a21f 기준본에 직접 적용한다. v2 적용본에 재적용하지 않는다. CodeOut/OutputRoot는 기존 v2와 다른 새 경로를 사용한다.
- 단일 단계만 끝나면 `PATCH_STAGE_<번호>.json` 및 `PATCH_PROGRESS.json`을 확인한다. 최종 판정 파일은 아직 생성되지 않는 것이 정상이다.
- 단계별 2 → 3 → 5 실행도 all 실행과 같은 최종 검증을 거친다. Stage 5만 실행하면 missing_steps에 2, 3이 남는다.
- 계약이 다른 단계 결과는 결합하지 않는다. 실패 후 임계값을 완화하거나 기존 결과·receipt를 수정하지 않는다.
- 적용 명령은 그 명령에 한해서 Git 줄바꿈 변환을 끈다. 전역 Git 설정을 바꿀 필요가 없다.
- 실행 전에 `python VERIFY_PACKAGE.py`로 전달 파일 무결성을 확인한다.
