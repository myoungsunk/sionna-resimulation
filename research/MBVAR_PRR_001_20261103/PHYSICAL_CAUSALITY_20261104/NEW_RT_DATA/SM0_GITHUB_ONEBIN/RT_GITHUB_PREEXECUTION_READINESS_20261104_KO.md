# MBVAR-PRR-001 / RT-PREEXEC-001 — GitHub Actions 실행 직전 검증 패키지

**기준:** 2026-11-04 · **상태:** `STATIC_READY / NATIVE_NOT_REEXECUTED / USER_RT_BUDGET_NOT_GRANTED`  
**계산 방식:** `USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY` 자체 검증. GitHub 별도 감사자 승인 불필요, 과학적 독립 검증이라고 주장 금지.  
**원본 보호:** PR #28 SM0 R4-B194의 기존 `STOP_MISMATCH` 및 C3V5 SHA 오류/기존 G5 실패 불변.

## 1. 실패 원인 및 수정

[기존 1-bin Native RT #41795360279](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41795360279)의 실행은 source SHA PASS → Sionna 2.0.1·Mitsuba 3.8.0·Dr.Jit 1.3.1 설치/로드 PASS → FFD 두 bank SHA PASS → **`ModuleNotFoundError: No module named 'corridor_sionna_run'`** 순으로 실패했다.

- checkout된 `scripts/corridor_sionna_run.py`가 Python import 경로에 포함되지 않음.
- `run_onebin.py`에서 `scripts/`, `scripts/g2_completion/`, `src/` 경로를 **고정된 저장소 위치에서만** 주입하고, 모듈의 실제 위치가 해당 소스인지 확인하도록 수정함.
- 실패 이전에 `rt.PathSolver(...)`는 **0회 호출**됐다. Native RF 문제나 LoS parity 실패의 재현으로 오해하지 말 것.
- 이전 원본 SM0 257-bin은 별도로 `float64 direct relative L2=2.4708055e-5 > 1e-5`여서 `STOP_MISMATCH`가 유효하다. 이 기준을 완화하거나 재라벨링하지 않음.
- **기존 1-bin workflow도 푸시 자동실행을 제거하고 수동 `RUN_ONE_BIN_CPU_RT` 확인 후만 solver 1회 허용**.

## 2. 실행 직전까지 구현한 코드

| 구성요소 | 위치 | 책임 |
|---|---|---|
| 1-bin source fix | `run_onebin.py` | 원본 R4-B194 중앙 주파수 Native 직접파 1회 재생; 소스/FFD SHA와 실행 증거 보존 |
| 4-scene 사전잠금 | `P3_NATIVE_CONTROLLED_SCENE_PREEXECUTION_LOCK_DRAFT.json` | 원본 source·port bank SHA, 4개 R4-B pose, C00/C01/C10/C11 geometry, 계산 호출수, 257-bin/2×2 port 규약 |
| 완성 실행기 | `native_rt_batch.py` | `--static`은 **Sionna import조차 하지 않음**. 수동 승인 시 한 configuration 당 최대 257회 Native PathSolver, 복소 H·경로 원시 계수/지연/유효성·CIR·FP/r/s/예외/해시 저장 |
| 직접파·장면 집계기 | `native_rt_aggregate.py` | C00 8개 키 전체 source parity PASS 후 C01/C10/C11 24개 키의 paired complex-H 등 비교, missing/실패 모두 STOP |
| 전체 수동 Actions | `.github/workflows/mbvar-prr-native-rt-manual-8224-20261104.yml` | 명시적 사용자 token + 8224 호출 승인 없이는 실행 불가. C00 4 pose×2회, 4 CPU job 병렬 → strict QA → 성공한 경우에만 반사 장면 4 pose×3 scene×2회, 4 CPU job 병렬 → QA |
| 1-bin 수동 Actions | `.github/workflows/mbvar-prr-sm0-onebin-sionna-rt-20261104.yml` | `RUN_ONE_BIN_CPU_RT` 수동 확인 후 original middle bin만 호출, 실패 증거 보존 |
| Read-only static CI | `.github/workflows/mbvar-prr-native-rt-static-ready-20261104.yml` | SHA·기하·수량·함수·artifact·실행 게이트 음성 테스트, 두 수동 workflow YAML 문법 및 자동 실행 금지 검사 |

**과학적 주의:** C00/C01/C10/C11은 원래 R4-B 257-bin 재생이 아니라, 원본 R4 pose·anchor·양 편파 bank를 사용하는 **새로운 floor/plate 통제 장면**이다. C00/C01은 고정 floor mesh, C10/C11은 여기에 미리 정한 두 각도의 두께 0.2 m `concrete` plate를 추가한다. **금속 반사판 실험이라고 주장하지 않는다.** 원래 6개 표면 전체의 Corridor Full과 동일하다는 주장도 금지한다. 장면 변경 효과는 covariance-only intervention이 아니다.

## 3. GitHub에서 실제 실행할 정확한 방법 (현재 실행하지 않음)

RT 실행 workflow 이름: `MBVAR PRR P3 Native RT 8224 calls EXPLICIT APPROVAL gated C00→paired`.

**권장: 연구 feature 브랜치에서 직접 실행 승인 파일을 커밋**한다. `RT_EXECUTION_APPROVAL_TEMPLATE.json`을 복사해 실제 승인할 때에만 `RT_EXECUTION_APPROVAL_EFFECTIVE.json`이라는 새 파일로 만들고, `approved_actor=myoungsunk`, `confirmation=I_APPROVE_8224_NATIVE_CPU_CALLS`, `budget_calls=8224`, `wall_seconds_per_key=1200`, `approval_method=EXPLICIT_GITHUB_APPROVAL_COMMIT`, `expected_source_blob_sha` 및 `expected_lock_blob_sha`를 정확히 유지한다. **그 정확한 파일 경로의 커밋만** workflow의 push 실행을 발생시킨다. 현재 이 GO 파일은 존재하지 않는다.

해당 workflow가 저장소 기본 브랜치에 등록된 후에는 **Actions → Run workflow**의 수동 입력으로도 같은 승인 조건을 적용할 수 있다. feature 브랜치에만 있는 새로운 workflow는 GitHub UI에서 `workflow_dispatch`가 보이지 않을 수 있으므로 승인 파일 방식을 준비했다.

| Actions input | 승인 시 입력값 | 의미 |
|---|---|---|
| `confirmation` | `I_APPROVE_8224_NATIVE_CPU_CALLS` | C00 2056 + 반사 6168 (총 8224) PathSolver 호출의 사용자 직접 승인 |
| `budget_calls` | `8224` | 정확한 전체 frequency-bin 호출 상한 (자동 증액 금지) |
| `wall_seconds_per_key` | 예: `1200` | 한 configuration의 벽시계 하드 상한, 수동 120~3600초 선택 |

승인값이 정확하지 않으면 GUARD FAIL로 계산이 진행되지 않는다. **소스 코드 변경·일반 push·schedule로는 RT가 자동 실행되지 않는다**. 신규 **`RT_EXECUTION_APPROVAL_EFFECTIVE.json` 한 파일의 명시적 사용자 승인 커밋**만 별도 push 트리거다. `C00_DIRECT` 4 pose×2회, 총 **2056 calls**의 직접파 source 상대 L2 `<=1e−5`·해시·경로 산출이 모두 PASS여야 3개 반사 arm으로 자동 진입한다. 8개 중 하나라도 FAIL이면 원시 아티팩트와 STOP 판정을 남기고 **다음 6168 calls를 실행하지 않는다**.

**원본 257-bin SM0 parity 실패를 고려하면 C00의 실제 통과를 보장할 수 없다.** 값이 높더라도 threshold를 사후 완화하지 않고 원인을 별도로 조사한다. 본 스레드에서 전체 Native RT workflow는 DISPATCH하지 않았다.

## 4. GitHub 시간·호출 수량 근거

[기존 성공 Native RT #41395666117](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41395666117) Actions 실제 시간:

| 작업 | 실제 범위 | 계산 단계 |
|---|---|---|
| Smoke | 3 pose×257 bins×LoS/Full = 1542 PathSolver calls | 11분 45초 |
| R2 | 13 pose×257 bins×LoS/Full = 6682 calls | 24분 53초 |
| R4 | 위와 같음 | 24분 7초 |
| R5 | 위와 같음 | 24분 7초 |
| 전체 | Smoke 다음 3경로 병렬, 집계 | **38분 15초** |

성공한 13-pose RT job은 약 4.5 calls/s (평균 **0.216~0.224 s/call**). 이는 **다른 장면·다른 경로 수에서의 관찰된 처리량**일 뿐 RT 신규 4-scene의 보장 성능이 아니다.

| 신규 전체 설계 | 호출수 | 기존 처리량의 단순 환산 |
|---|---:|---:|
| C00 4 pose×257×2 | 2,056 | 약 7.4분 직렬 CPU 순수 solver 계산 |
| C01/C10/C11 3 scene×4pose×257×2 | 6,168 | 약 22.4분 직렬 |
| 합계 | **8,224** | **약 29.8~30.7분 직렬** |
| GH runner 4개, C00와 paired 각각 병렬 | 8,224 | 계산 자체는 이상적 조건 약 7.5분, setup·통신·mesh·QA 별도 |
| 최대 288 구성×257 bin (1회) | 74,016 | 약 4.5시간 직렬 (본 요청엔 해당 없음) |
| 288 구성×257 bin×2회 | 148,032 | 약 9시간 직렬 (본 요청엔 해당 없음) |

현실적인 추정은 CPU runner 4개가 즉시 배정된다면 **약 10~30분부터**, 장면별 경로 수·I/O·해시·대량 bank 다운로드에 따라 더 길 수 있다. 전체 run이 GitHub queue에 머무르면 **별도의 30~60분 이상**이 추가될 수 있다. 기존 실패 #41795360279는 생성 07:53:08Z, 실제 checkout 08:29:56Z, 종료 08:30:39Z로 **대기 약 37분, 실제 job 약 40초**, solver 호출 0회였다. 이 대기시간을 RT compute throughput으로 나누면 안 된다. 4-way 병렬 runner를 실제로 받지 못하면 wall time이 증가한다.

**주의:** 앞선 문서의 “16 configs×2 repeats=32 solver calls”는 주파수별 PathSolver 호출을 누락한 잘못된 예산 표기다. 현재 코드·계약은 **8224**로 정정했고, 숫자가 정확히 맞지 않으면 manual workflow에서 계산을 거부한다.

## 5. 검증 판정과 미완료 구분

- `STATIC_READY`: 소스·bank manifest·4 pose·scene/plate geometry·stage order·budget fail-closed 및 YAML parse 테스트 PASS. **solver 실행 결과가 아님**.
- `ONEBIN_NATIVE_PROBE_NOT_REEXECUTED`: 한-bin import 수정은 구현했지만 수정 SHA에서 새 실제 PathSolver 출력을 아직 검증하지 않았다.
- `C00_257BIN_STRICT_PARITY_PASS`: 지정된 8개 실제 복소 H data + original LoS relative error 모두 PASS일 때만. 과거 첫 pose의 STOP을 지우지 않는다.
- `PAIRED_257BIN_TECHNICAL_PASS_NOT_SCIENCE`: 24개 (C01/C10/C11) 실제 등록 key가 모두 있고 정합한 경우에만. 4 pose의 한 Corridor 장면이 통계학적 scene-level 독립 증거는 아니다.
- `A010_C3`: 전혀 다른 synthetic DEV3 과학 검증. R4B 물리 scene 실행으로 C3 1080 Batch G5/H-CAL 결과를 대신할 수 없다.
- `HOLDOUT2`: 별도 허가 전 NO-GO.
- `INDEPENDENT_AUDITOR_SIGNED`: false. 자체 계산으로 독립인 양 표시 금지.

실행 전 소스 인프라/원본 FFD bank artifact가 삭제되거나 timeout되면 preflight STOP. 실제 계산 실행 예산은 위 수동 dispatch를 통해 명시적으로 선택할 때에만 승인된 것으로 기록한다.
