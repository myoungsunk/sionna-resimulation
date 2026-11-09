# B-MCG v1 실행·재현 Runbook

이 문서는 **최종 동결 소스의 재실행 순서와 실제 CLI**를 설명한다. 아래 명령은 이번 문서 작성 중 새로 실행한 실험이 아니다. 완성된 결과 디렉터리를 덮어쓰지 않고, 재실행에는 새 작업 디렉터리를 사용한다.

**기본 정책은 OFF다.** `ACTIVE_R/S/RS`는 고정 τ=2 진단 대조군이며, P4가 선택한 운영 정책이 아니다. 이번 데이터의 최종 P4는 두 보정 조건의 세 fold 모두 OFF를 선택했다. 실행 성공·수치 재현·보고서 생성은 유용성·회복·실시간 통과를 뜻하지 않는다.

## 0. 고정할 버전과 결과의 계보

| 대상 | 고정 식별자 |
| --- | --- |
| 실행 코드 commit | `e3ddc9fa4371d899a08a2a873d2ee5cf32074a01` |
| 원본 입력·SourceFFD 계보 | `c141839093d1a2e4a76f91eea632cb6467163e28` |
| 과거 Native/B 인과 감사 수리 | `beb845665661ad8c68d07c88f6d268da4832e493` |
| 과거 B 보정·archive 계보 | `a8e76620b9f805b8e16d4525312c7a69b247306e` |
| 최종 `mcg.py` SHA256 | `8f58b7c412e54ca5fa308e61aa16c59c0fec30f05e482c505cb5cdea11099faf` |
| 최종 `experiment.py` SHA256 | `e4abd56b3224782efb2f4c861d61e0bd724e0e3687a8e06d8b81f0520229ed28` |
| 실행된 `ci_route.py` SHA256 | `c0d50dad15db88f8726c1840b938a7b91dcffb31df2e8036ee9f3d525c582837` |

후속 문서/reporting commit은 위 runtime 세 파일을 바꾸지 않는다. 실행 commit만 checkout하면 뒤에 추가한 보고서·runbook·reporting 파일이 없을 수 있으므로, 전체 보고서 재생성에는 동반 최종 문서 commit도 필요하다. Runtime은 위 SHA로 확인한다.

### Prototype과 최종 결과를 섞지 않는다

초기 finite profile, 중간의 blanket boundary veto, 최종 numerical validity amendment가 존재한다. 수정은 **최종 P4 lock 전에** 이루어졌다. `profiles`, `profiles_v0_undercoverage`의 과거 출력·`*_PARTIAL.npz`·`*_RUNNING.json`을 `profiles_final`에 합치지 않는다. 최종 보정은 `profiles_final/{B_FROZEN,B_BIAS_COV}/{R2,R4,R5}.npz` 여섯 개와 해당 완료 metadata만 사용한다. `source_adversarial`, `source_adversarial_v1`, `recovery_v1`은 수정 이력의 증거다. 최종 성능·회복 판정은 `*_final` 결과를 사용한다. 자세한 수치 수정은 [AMENDMENT_001_PROFILE_VALIDITY.md](AMENDMENT_001_PROFILE_VALIDITY.md)에 있다.

NPZ에는 처리시간, JSON에는 실행 시각이 기록된다. **새 실행의 결과 파일 SHA가 역사적 결과 SHA와 같아야 한다는 조건은 없다.** 원본 입력·코드 SHA는 고정하고, 새 결과 SHA를 새 receipt에 기록한 뒤 배열·의사결정·오차 허용치로 대조한다. 제공한 역사적 snapshot을 검증할 때만 그 snapshot의 파일 SHA를 요구한다.

## 1. 작업 디렉터리와 환경

아래는 최종 소스가 `BMCG_ROOT/repo`에 checkout되어 있다고 가정한다. 경로를 실제 새 작업 디렉터리로 바꾼다. Python은 3.12, 수치 패키지는 CI와 같은 NumPy 2.3.5·SciPy 1.17.0이다. 실제 로컬과 CI의 Python patch/compiler는 달랐으며, 수치 대조는 그 차이를 포함한다.

```bash
export BMCG_ROOT=/absolute/path/to/new-b-mcg-workspace
export BMCG_REPO="$BMCG_ROOT/repo"
export BMCG_CODE="$BMCG_REPO/research/B_MCG_V1_20261109"
export BMCG_BASE="$BMCG_REPO/research/FP_NATIVE_B_CAUSAL_ABLATION_20261108"
export BMCG_RESULTS="$BMCG_ROOT/results"
export BMCG_ASSETS="$BMCG_ROOT/assets"
export BMCG_PY="${CODEX_PRIMARY_RUNTIME_PYTHON:-python3}"
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
mkdir -p "$BMCG_RESULTS" "$BMCG_ROOT/recovery" "$BMCG_ROOT/review"
"$BMCG_PY" -m pip install numpy==2.3.5 scipy==1.17.0
```

최종 runtime SHA 확인:

```bash
"$BMCG_PY" - <<'PY'
import hashlib, os
from pathlib import Path
p = Path(os.environ['BMCG_CODE'])
expected = {
    'mcg.py': '8f58b7c412e54ca5fa308e61aa16c59c0fec30f05e482c505cb5cdea11099faf',
    'experiment.py': 'e4abd56b3224782efb2f4c861d61e0bd724e0e3687a8e06d8b81f0520229ed28',
    'ci_route.py': 'c0d50dad15db88f8726c1840b938a7b91dcffb31df2e8036ee9f3d525c582837',
}
for name, digest in expected.items():
    assert hashlib.sha256((p/name).read_bytes()).hexdigest() == digest, name
print('FINAL_RUNTIME_SHA_MATCH')
PY
```

`repo`에는 B-MCG 패키지 외에 `FP_NATIVE_B_CAUSAL_ABLATION_20261108`, `FP_SC_RECOVERY_R0_R5_20261107`의 source hierarchy, `FP_SC_S1_RUN_20261106/RESULTS/*/ROWS.json.gz`가 필요하다. 대용량 Release NPZ를 LFS pointer 그대로 사용하면 stage가 실패한다. Actions의 실제 sparse checkout 범위는 [workflow](../../.github/workflows/b-mcg-v1-20261109.yml)에 있다.

## 2. 원본 재취득·stage·과거 archive

```bash
"$BMCG_PY" "$BMCG_BASE/acquire_inputs.py" \
  --out "$BMCG_ASSETS"

"$BMCG_PY" "$BMCG_BASE/stage_inputs.py" \
  --repo "$BMCG_REPO" --assets "$BMCG_ASSETS" \
  --out "$BMCG_ROOT/recovery"

"$BMCG_PY" "$BMCG_CODE/acquire_archive.py" \
  --out "$BMCG_ROOT/reference"

export BMCG_ARCHIVES="$BMCG_ROOT/reference/extracted/tmp/fp-b-calibration"
```

과거 Actions archive가 만료되었거나 API로 접근할 수 없으면, **동일 SHA의 보관 ZIP**을 직접 지정한다. 다른 결과로 gold archive를 재생성하지 않는다.

```bash
"$BMCG_PY" "$BMCG_CODE/acquire_archive.py" \
  --archive /absolute/path/to/fp-b-route-heldout-calibration-42483593407.zip \
  --out "$BMCG_ROOT/reference"
```

확인할 결과는 Release 입력 8개(online/evaluator NPZ 6개·FFD bank 2개), stage 11개(앞의 8개·ROWS 3개), archive ZIP 및 lock된 member 9개다. `GH_TOKEN`이 필요한 환경에서는 해당 환경의 승인된 읽기 자격을 사용한다. 토큰을 로그나 명령 인수에 기록하지 않는다.

## 3. 단위 검사와 원본 기준선 6개

아래 첫 명령은 별도 프로세스에서 27개 unit test를 실행하고, 실제 exit code·개수·전후 source SHA를 receipt로 남긴다. receipt를 수동으로 PASS라고 작성하지 않는다.

```bash
"$BMCG_PY" - <<'PY'
import hashlib, json, os, re, subprocess, sys
from pathlib import Path
code = Path(os.environ['BMCG_CODE'])
out = Path(os.environ['BMCG_RESULTS'])/'independent_unit_audit_final'
out.mkdir(parents=True, exist_ok=True)
assert not (out/'UNIT_TESTS.json').exists(), 'Use a fresh output'
names = ['mcg.py', 'test_mcg.py', 'stress_source.py', 'audit_source_alignment.py']
hashes = lambda: {n: hashlib.sha256((code/n).read_bytes()).hexdigest() for n in names}
before = hashes()
run = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_mcg'],
                     cwd=code, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(out/'UNIT_TESTS.log').write_text(run.stdout)
match = re.search(r'Ran (\d+) tests in ', run.stdout)
count = int(match.group(1)) if match else 0
record = {'scope': 'synthetic API/algebra/causality; no empirical utility certification',
          'command': [sys.executable, '-m', 'unittest', '-v', 'test_mcg'],
          'exit_code': run.returncode, 'source_sha256': before, 'test_count': count,
          'entry_exit_runtime_hash_match': before == hashes()}
(out/'UNIT_TESTS.json').write_text(json.dumps(record, indent=2)+'\n')
assert run.returncode == 0 and count == 27 and before == hashes(), record
PY

"$BMCG_PY" "$BMCG_CODE/test_calibration.py"

for BMCG_ROUTE in R2 R4 R5; do
  "$BMCG_PY" "$BMCG_CODE/experiment.py" baseline \
    --route "$BMCG_ROUTE" --archives "$BMCG_ARCHIVES" \
    --out "$BMCG_RESULTS/baseline"
done
```

`baseline` 한 번이 두 strata를 모두 실행하므로 위 세 호출은 **6개 기준선**이다. `R2/R4/R5_PARITY.json` 모두 PASS이고 기존 archive 대비 최대 scaled 오차가 `1e-10` 이하여야 한다. 이후 `--traces` 인수에는 이번 baseline 출력 폴더 대신 **원본 archive root**를 전달한다. 해당 진단은 `R2/R2_B_FROZEN.npz`와 route별 SHA manifest 같은 원본 계층을 읽기 때문이다.

## 4. 구현 전 유용성·잘못된 기준의 원인 검증

### 4.1 운동 형태, 생성 계보, 같은 prior의 기회 상한

```bash
"$BMCG_PY" "$BMCG_CODE/precheck_motion.py" \
  --assets "$BMCG_ASSETS" --archives "$BMCG_ARCHIVES" \
  --out "$BMCG_RESULTS/precheck_motion"

"$BMCG_PY" "$BMCG_CODE/audit_controls.py" \
  --assets "$BMCG_ASSETS" --archives "$BMCG_ARCHIVES" \
  --p2 "$BMCG_RESULTS/precheck_motion/P2_MOTION.json" \
  --out "$BMCG_RESULTS/precheck_motion/CONTROL_PROVENANCE_AUDIT.json"

"$BMCG_PY" "$BMCG_CODE/precheck_oracle.py" \
  --traces "$BMCG_ARCHIVES" --assets "$BMCG_ASSETS" \
  --input-lock "$BMCG_BASE/RELEASE_INPUT_LOCK.json" \
  --out "$BMCG_RESULTS/precheck_oracle"
```

P1은 evaluator가 선택한 same-prior 기회 상한이다. 구현 가능한 selector의 성능이 아니다. P2의 true-pose 시작·zero-bg 비교는 진단이며 runtime에 truth를 넣는 설정이 아니다. `gy`는 이미 적분된 rad, `ds`는 m, `dt`는 s다. 독립 wheel heading은 이 archive에 없다.

### 4.2 RF → bias → 운동 기준, 관측 개입 재귀, 시간 전개

```bash
"$BMCG_PY" "$BMCG_CODE/audit_bias_feedback.py" \
  --traces "$BMCG_ARCHIVES" --assets "$BMCG_ASSETS" \
  --input-lock "$BMCG_BASE/RELEASE_INPUT_LOCK.json" \
  --control-provenance "$BMCG_RESULTS/precheck_motion/CONTROL_PROVENANCE_AUDIT.json" \
  --out "$BMCG_RESULTS/bias_feedback"

"$BMCG_PY" "$BMCG_CODE/audit_ideal_residual.py" \
  --repo "$BMCG_REPO" --traces "$BMCG_ARCHIVES" \
  --control-provenance "$BMCG_RESULTS/precheck_motion/CONTROL_PROVENANCE_AUDIT.json" \
  --out "$BMCG_RESULTS/bias_causal" \
  --model-truth-out "$BMCG_RESULTS/model_truth"

"$BMCG_PY" "$BMCG_CODE/audit_horizons.py" \
  --repo "$BMCG_REPO" --traces "$BMCG_ARCHIVES" \
  --p1 "$BMCG_RESULTS/precheck_oracle" \
  --model-truth "$BMCG_RESULTS/model_truth" \
  --out "$BMCG_RESULTS/horizons"

"$BMCG_PY" "$BMCG_CODE/audit_projection.py" \
  --repo "$BMCG_REPO" --assets "$BMCG_ASSETS" \
  --archives "$BMCG_ARCHIVES" --out "$BMCG_RESULTS/projection"
```

`model_truth`의 `htruth`는 SourceFFD가 truth pose에서 계산한 **관측 모델 진단값**이다. 물리적으로 측정한 clean CIR라는 뜻이 아니다. P3는 3,061개 5초 window를 검사하지만 선형 unbounded projection을 실제 bounded nonlinear 허용해로 간주하지 않는다. Horizons는 hindsight로 고른 사건의 1/5/10초 전개이며 population 성능 추정이 아니다. 세 route의 공유 gyro noise prefix·초기오차와 과거 secondary 보정의 비중첩 검증 한계는 유지한다.

## 5. 최종 offline profile 6개 → P4 lock

아래 여섯 개가 모두 끝나야 최종 양-strata P4를 실행한다. `--limit`은 smoke용이므로 여기서는 사용하지 않는다. `profiles` 단계는 실제 구현상 `config_for(span=...)`의 기본 τ=3 설정을 기록한다. `experiment.py --tau`는 **active 단계**에 적용된다. 여기서 `--tau 2`를 붙여 profile config를 바꿀 수 있다고 안내하면 틀린다. P4는 저장된 점수에 사전 후보 τ를 별도로 적용한다.

```bash
for BMCG_STRATUM in B_FROZEN B_BIAS_COV; do
  for BMCG_ROUTE in R2 R4 R5; do
    "$BMCG_PY" "$BMCG_CODE/experiment.py" profiles \
      --route "$BMCG_ROUTE" --stratum "$BMCG_STRATUM" \
      --archives "$BMCG_ARCHIVES" --span 5 \
      --out "$BMCG_RESULTS/profiles_final/$BMCG_STRATUM"
  done
done

"$BMCG_PY" "$BMCG_CODE/calibrate_policy.py" \
  --profilesdir "$BMCG_RESULTS/profiles_final" \
  --archivesdir "$BMCG_ARCHIVES" --assetsdir "$BMCG_ASSETS" \
  --strata B_FROZEN --out "$BMCG_RESULTS/policy_primary_precheck"

"$BMCG_PY" "$BMCG_CODE/calibrate_policy.py" \
  --profilesdir "$BMCG_RESULTS/profiles_final" \
  --archivesdir "$BMCG_ARCHIVES" --assetsdir "$BMCG_ASSETS" \
  --strata B_FROZEN B_BIAS_COV --out "$BMCG_RESULTS/policy_calibration_final"
```

첫 호출은 primary 단계의 명시적 scope 기록이다. 기본 인수는 두 strata다. 최종 P4는 τ=`1.5,2,3,4` × R/S/RS의 12개 후보를 사용한다. 두 학습 route 각각의 train/dev support, 양 손실 축의 순이득, 실제 accepted 개입, 좋은 갱신 lost-gain budget을 모두 요구한다. Empty split이나 빈 분모를 완화하지 않는다. 후보가 없으면 OFF다.

Heldout truth pose는 lock 전의 **offline geometry splitter**에서 사용한다. Heldout loss 평가와 runtime 입력에서는 분리되지만, 이를 “lock 전에 heldout truth를 전혀 사용하지 않음”이라고 쓰면 안 된다. `POLICY_LOCK.json`은 heldout loss 평가 전에 기록된다. 과거 제공된 `POLICY_LOCK.json`(primary)과 `POLICY_LOCK_ALL_STRATA.json`은 역사적 결과이며, 새로운 P4 출력과 혼동하지 않는다.

## 6. 독립 재귀 42개: 기본 OFF와 고정 diagnostic 구분

두 호출에서 각각 `3 routes × 7 modes = 21`개, 총 **42개**를 실행한다. Primary는 primary lock, secondary는 양-strata lock을 기록하여 실제 실행의 scope 구분을 유지한다. Worker 수는 1–9 범위다. 병렬 부하가 latency에 영향을 주므로 실시간 수치 비교에는 실행 환경·동시 실행 수를 함께 기록한다.

```bash
"$BMCG_PY" "$BMCG_CODE/run_arm_grid.py" \
  --archives "$BMCG_ARCHIVES" \
  --policy-lock "$BMCG_RESULTS/policy_primary_precheck/POLICY_LOCK.json" \
  --strata B_FROZEN --out "$BMCG_RESULTS/active" \
  --workers 3 --name PRIMARY_FINAL

"$BMCG_PY" "$BMCG_CODE/run_arm_grid.py" \
  --archives "$BMCG_ARCHIVES" \
  --policy-lock "$BMCG_RESULTS/policy_calibration_final/POLICY_LOCK.json" \
  --strata B_BIAS_COV --out "$BMCG_RESULTS/active" \
  --workers 3 --name SECONDARY_FINAL
```

기본 modes는 `OFF OBSERVE_ONLY ACTIVE_R ACTIVE_S ACTIVE_RS DR_ONLY NAIVE_YAW_CLIP`이다. 각 mode는 자신의 상태·공분산을 다음 시점으로 넘기는 별도 재귀다. `NAIVE_YAW_CLIP`은 기존 CLI 이름이며 실제 출력 heading clip이 아니다. Trial 보정각 문턱으로 양 관측을 감쇠하는 부정 대조다.

완료 metadata가 이미 있으면 `experiment.active`는 덮어쓰지 않는다. 실패 시 GRID manifest와 해당 log를 확인하고 새 output에 실패한 scope만 명시적으로 다시 실행한다. 성공한 일부 파일만으로 42개 완료를 선언하지 않는다.

## 7. 잘못된 기준·정상 복귀에 대한 적대적 진단

```bash
"$BMCG_PY" "$BMCG_CODE/stress_source.py" \
  --archives "$BMCG_ARCHIVES" --model-truth "$BMCG_RESULTS/model_truth" \
  --tau 3 --out "$BMCG_RESULTS/source_adversarial_final"

"$BMCG_PY" "$BMCG_CODE/audit_stress_policy.py" \
  --archives "$BMCG_ARCHIVES" --model-truth "$BMCG_RESULTS/model_truth" \
  --stress "$BMCG_RESULTS/source_adversarial_final" \
  --out "$BMCG_RESULTS/source_adversarial_final/R5_CLEAN_RETURN_TAU_SENSITIVITY.json"

"$BMCG_PY" "$BMCG_CODE/synthetic_adversarial.py" \
  --out "$BMCG_RESULTS/synthetic_adversarial_final"

"$BMCG_PY" "$BMCG_CODE/audit_recovery.py" \
  --archives "$BMCG_ARCHIVES" --model-truth "$BMCG_RESULTS/model_truth" \
  --out "$BMCG_RESULTS/recovery_final"

"$BMCG_PY" "$BMCG_CODE/audit_recovery_cause.py" \
  --recovery "$BMCG_RESULTS/recovery_final" \
  --out "$BMCG_RESULTS/recovery_cause"

"$BMCG_PY" "$BMCG_CODE/audit_recovery_balance.py" \
  --recovery "$BMCG_RESULTS/recovery_final" \
  --cause "$BMCG_RESULTS/recovery_cause" \
  --out "$BMCG_RESULTS/recovery_cause/UPDATE_BALANCE.json"

"$BMCG_PY" "$BMCG_CODE/audit_recovery_feasibility.py" \
  --archives "$BMCG_ARCHIVES" --recovery "$BMCG_RESULTS/recovery_final" \
  --out "$BMCG_RESULTS/recovery_feasibility/R4_FIRST_CLEAN_FEASIBILITY.json"
```

`audit_recovery.py`는 사전 고정한 OFF/τ2/τ3를 내부에서 실행하며 별도 `--tau` 인수가 없다. `audit_stress_policy`, `audit_recovery_balance`, `audit_recovery_feasibility`의 `--out`은 **JSON 파일**이다. 다른 위 진단의 `--out`은 디렉터리다.

작은 innovation·좁은 finite candidate spread만으로 올바른 절대 정렬을 선언하지 않는다. Positive feasible witness는 후보 누락의 증거가 되지만, 최적화가 witness를 못 찾았다는 사실은 전역 infeasibility의 증명이 아니다. Tau sensitivity는 진단이며 P4를 사후 재학습하는 단계가 아니다. `audit_source_alignment.py`는 amendment 조사에 쓰인 별도 evaluator-only 탐색 코드로 보존되어 있으며, 과거 결과를 final profile 생성 입력으로 쓰지 않는다.

## 8. 독립 평가·불확실도 요약

```bash
"$BMCG_PY" "$BMCG_CODE/evaluate_delivery.py" \
  --results "$BMCG_RESULTS" --repo "$BMCG_REPO" \
  --archives "$BMCG_ARCHIVES" --assets "$BMCG_ASSETS" \
  --input-lock "$BMCG_BASE/RELEASE_INPUT_LOCK.json" \
  --policy-lock "$BMCG_RESULTS/policy_calibration_final/POLICY_LOCK.json" \
  --out "$BMCG_RESULTS/delivery_evaluation" --require-complete

"$BMCG_PY" "$BMCG_CODE/reporting/audit_uncertainty.py" \
  --root "$BMCG_ROOT" --assets "$BMCG_ASSETS" \
  --input-receipt "$BMCG_ROOT/recovery/INPUT_RECEIPT.json" \
  --out "$BMCG_RESULTS/uncertainty"
```

`--require-complete`는 42개 평가의 누락을 실패시킨다. 모든 과학적 채택 조건을 통과했다는 인수가 아니다. `RESULTS.json`, `METRICS.csv`, `DEVELOPMENT_UNITS.csv`의 완결성·원본 계보·정책 유용성·회복·latency 판정을 별도로 읽는다. `audit_uncertainty.py`는 저장된 OFF/ACTIVE_RS 12개 stream의 coverage·폭/면적·연속 이탈을 평가하며 필터를 다시 실행하지 않는다.

## 9. 원격 CI 12개와 로컬 42개의 범위

[Actions 실행 #42600632209](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209)은 R2/R4/R5 matrix에서 **두 strata × OFF/ACTIVE_RS = 12개**와 원본 baseline 6개를 실행했다. 로컬의 42개 arm 전체를 원격에서 실행한 것이 아니다. 실제 workflow에 쓰인 한 route의 CLI는 다음과 같다.

```bash
"$BMCG_PY" "$BMCG_CODE/ci_route.py" \
  --route R2 --archives "$BMCG_ARCHIVES" \
  --policy-lock "$BMCG_CODE/POLICY_LOCK.json" \
  --out "$BMCG_ROOT/ci-replay-R2"
```

이 명령 자체는 로컬 replay다. 원격 실행은 해당 workflow의 matrix 또는 `workflow_dispatch`로 수행한다. 새로운 원격 실행에는 새 run ID와 artifact metadata를 사용한다. 과거 `CI_REMOTE_AUDIT.json`을 새 실행 receipt로 재사용하지 않는다.

이번 원격 대조는 12개 × 총 12,544행의 gate/status/채널 사용·감쇠 분류가 로컬과 정확히 같고, 전체 float 최대 scaled 차이가 약 `3.13e-12`였다. CI success는 활성 정책 채택이 아니며, 현재 ACTIVE_RS total p99 334–446ms는 200ms 관측 주기를 초과한다.

## 10. 독립 감사 소스의 byte 보존과 역사적 snapshot 재검사

[reporting/INDEPENDENT_AUDIT_SOURCE_LOCK.json](reporting/INDEPENDENT_AUDIT_SOURCE_LOCK.json)은 `check_final_policy.py`, `audit_ci_remote.py`를 원래 review script와 **byte 동일하게 복사했음**을 기록한다. CI receipt에는 checker 자체 SHA가 내장되어 있다. Policy receipt에는 checker 자체 SHA가 원래 내장되지 않았으므로 copy manifest가 원본 script와 기존 receipt의 SHA를 연결한다. 이를 소급해서 receipt에 내장된 증거라고 표현하지 않는다.

두 코드는 범용 `--root` CLI가 아니다.

- `check_final_policy.py`: 원래 workspace의 `BASE`가 고정되고 CLI 인수가 없다. 같은 역사적 snapshot에 대한 144개 집계·12개 mask 재계산 감사다.
- `audit_ci_remote.py`: `review/`에 놓인 파일의 부모에서 ROOT를 계산한다. 특정 run `42600632209`·commit과 3개 ZIP/API evidence/원본 local traces를 대조한다. Reporting 폴더에서 직접 실행하면 ROOT가 틀린다.

제공한 역사적 snapshot을 다른 작업 경로에 복원해 감사할 때는 다음처럼 **경로 변수만** 연결할 수 있다. 코드 bytes·threshold·판정·자료는 바꾸지 않는다. 이미 검증된 snapshot을 복사한 별도 작업 폴더에서 수행한다. 새 profile 생성 결과를 과거 ZIP/lock과 억지로 SHA 일치시키는 용도가 아니다.

```bash
cp "$BMCG_CODE/reporting/check_final_policy.py" "$BMCG_ROOT/review/check_final_policy.py"
cp "$BMCG_CODE/reporting/audit_ci_remote.py" "$BMCG_ROOT/review/audit_ci_remote.py"

"$BMCG_PY" - <<'PY'
import importlib.util, os
from pathlib import Path
root = Path(os.environ['BMCG_ROOT'])
path = root/'review/check_final_policy.py'
spec = importlib.util.spec_from_file_location('preserved_policy_checker', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.BASE = root
module.FINAL = root/'results/policy_calibration_final'
module.PRIMARY = root/'results/policy_primary_precheck'
module.PROFILES = root/'results/profiles_final'
module.ARCHIVES = Path(os.environ['BMCG_ARCHIVES'])
module.ASSETS = Path(os.environ['BMCG_ASSETS'])
module.PACKAGE = Path(os.environ['BMCG_CODE'])
module.run()
PY

"$BMCG_PY" - <<'PY'
import importlib.util, os
from pathlib import Path
root = Path(os.environ['BMCG_ROOT'])
path = root/'review/audit_ci_remote.py'
spec = importlib.util.spec_from_file_location('preserved_ci_checker', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ARCHIVES = Path(os.environ['BMCG_ARCHIVES'])
module.run(False)
PY
```

CI checker에는 `results/github_ci`의 ZIP 3개·정확한 추출 tree·`DOWNLOAD_RECEIPT.json`·`API_EVIDENCE.json`·`COMMITTED_RELEASE_LOCK.json`이 필요하다. 최종 ZIP 근거 묶음은 원격 numeric evidence와 감사 receipt를 보관하지만 원 GitHub artifact ZIP 전체와 중복 source tree를 모두 포함하지 않는다. 전체 CI 무결성 재검사에는 GitHub에서 원 artifact를 다시 받거나 별도 보관본을 복원해야 한다. Artifact ID는 R2 `13666845152`, R4 `13665704068`, R5 `13665868091`; API상 만료일은 모두 `2027-02-07T10:24:20Z`다. 없다면 `NOT_VERIFIED`로 남기고 가짜 receipt를 만들지 않는다.

## 11. 최종 보고·근거 포장

보고서 생성에는 **완료된 42-stream 독립 평가, 12-stream CI 대조 receipt, 12-stream uncertainty 평가**가 필요하다. 최종 적대적 논평은 `review/FINAL_ADVERSARIAL_VERDICT_KO.md`에 별도 검토로 작성한다. 프로그램 출력만으로 이를 대신하지 않는다.

보고 환경에는 Matplotlib·ReportLab·Pillow가 추가로 필요하다. 이번 문서 환경은 각각 3.10.8·4.4.9·13.0.0이었다. `build_report.py`는 다음 폰트 파일을 요구한다: `BMCG_ROOT/tmp/report_fonts/NanumGothic-Regular.ttf`, `NanumGothic-Bold.ttf`와 `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. 폰트 파일을 준비하고 존재를 확인한 뒤 실행한다.

```bash
test -f "$BMCG_ROOT/tmp/report_fonts/NanumGothic-Regular.ttf"
test -f "$BMCG_ROOT/tmp/report_fonts/NanumGothic-Bold.ttf"
test -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

"$BMCG_PY" "$BMCG_CODE/reporting/build_report.py" --root "$BMCG_ROOT"
"$BMCG_PY" "$BMCG_CODE/reporting/package_evidence.py" --root "$BMCG_ROOT"
```

PDF는 `output/pdf/B_MCG_V1_IMPLEMENTATION_VALIDATION_KO_20261109.pdf`, Markdown은 패키지의 `REPORT_KO.md`, 근거 ZIP은 `deliverables/B_MCG_V1_EVIDENCE_20261109.zip`에 작성된다. `--figures-only`는 그림만 만드는 옵션이며 최종 보고서 완료로 세지 않는다. PDF는 렌더링하여 표·한글·축·페이지 넘침을 확인하고, ZIP은 member별 SHA 검증 receipt를 확인한다. Packaging은 필요한 결과 폴더·review evidence가 이미 준비되어 있어야 하며, 과거 누락 증거를 재실행 없이 만들어 주는 도구가 아니다.

## 마지막 판정 기준

| 개발 단위 | 필수 확인 | 성공으로 대신할 수 없는 것 |
| --- | --- | --- |
| 입력·원본 | 8 acquisition·11 stage·archive SHA, 기준선 6개 | 실행 종료 코드만으로 계보 확인 |
| Runtime | 최종 SHA, 27 unit·5 calibration test, truth whitelist | 실제 데이터의 utility·전역 feasible-set 완전성 |
| P4 | split support·양 축 train/dev gain·lost-gain budget·개입 | OFF fallback을 활성 guard 성공으로 해석 |
| 42 재귀 | 14 mode/stratum group 각각 3,136행, actual/trial 구분 | 같은 prior oracle을 재귀 성능으로 해석 |
| 회복 | 정상 복귀 오감쇠, raw legacy gate, censoring, feasible witness | 작은 innovation·candidate spread를 정확성으로 해석 |
| CI | 원격 12개·baseline 6개, 코드/입력/array 대조 | 로컬 42개 전체를 원격 검증했다고 표현 |
| 보고 | coverage와 폭·연속 이탈, latency, 미검증 범위, trace SHA | 실행 완료를 운영 채택으로 표현 |

이 runbook을 다시 따라 실행해도 데이터는 같은 세 route·같은 seed의 재생이다. 새로운 scene·sensor realization·독립 noise seed의 외적 검증이 추가되는 것은 아니다.
