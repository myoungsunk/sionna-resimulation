# 개발자 실행 인계

이 문서의 실제 데이터 명령은 **향후 별도 승인을 받은 뒤** 사용한다. 이번 변경에서는 합성 검사와 plan만 실행했다.

## 1. 데이터 없는 검사

저장소 root, Python 3.11 이상, NumPy 환경:

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -p test_fp_sc_followup.py -v
python -m compileall -q src/qclean_uwb/fp_sc/followup scripts/fp_sc_followup.py tests/test_fp_sc_followup.py
python scripts/fp_sc_followup.py plan
```

테스트의 SyntheticAdapter는 테스트 파일 안에만 있다. 실제 실행기는 OriginalAdapter를 사용하며 원본 FFD bank가 없으면 geometric toy model로 대체하지 않는다. pytest/formatter를 설치했다고 가정하지 않는다. 표준 unittest와 compileall로 검사 가능하다.

## 2. 실제 데이터 형식과 원본 보존

`MANIFEST_TEMPLATE.json`은 미완성·미승인 template다. placeholder hash로 실행하지 않는다. 경로는 repo-relative이며 LFS pointer가 아닌 실제 payload의 SHA256이어야 한다. 원본을 덮어쓰지 않는 새 출력 폴더만 허용한다.

case별 `online.npz`:

- Hrf complex[N,257,2], t[N], pose_id 정수[N], ds/gy/dt[N]
- x0[4], P0[4,4], z/muMB/muBASE[N,2], R[N,2,2], D[N]
- archived prior[N,4], Pprior[N,4,4]
- E3-04용 trace_h/H/prior/Pprior/Reff/K/mask; mask는 bool[N]
- 선택적 clean_Hrf: 새 잡음을 만들 때 쓰는 **같은 channel의 clean waveform**, 평가용 LoS가 아니다.

별도 `evaluator.npz`: clean_H(같은 pose의 clean Native-LoS)[N,257,2], truth[N,4], t, pose_id. GT gyro bias를 모르면 0으로 채우지 않는다. 평가 자료는 selector 입력으로 전달하지 않는다.

metadata는 case_id, route, bias, channel, sensor_seed, split, noise_variance, corpus, environment_id를 모두 가진다. case_id는 영문/숫자/underscore/hyphen 128자 이하. split은 TRAIN/CAL/SEALED/EXPOSED_DEV/SYNTHETIC. 실제 실행에서 SYNTHETIC을 과학적 확인자료로 승격하지 않는다.

원 archive의 변환은 명시적 `EXPORT_SPEC_TEMPLATE.json`을 채우고 실제 payload SHA를 등록한 다음 실행할 수 있다. packet/trace/truth의 pose/time을 exact join하고 RF[:,frequency,RX,TX0]를 선택한다. controls의 EXACT_ARCHIVE/A2_REMATERIALIZED/NEW_RECIPE_REALIZATION을 구분한다.

```sh
python scripts/fp_sc_followup.py export-archive --repo . --spec frozen_export_spec.json --output new_inputs/case01
```

이는 형식 변환으로, receiver/selector/EKF/RT를 계산하지 않는다. 기존 clean archive 전용 변환이므로 noisy waveform은 별도 recipe/배열/해시를 준비해야 한다.

## 3. manifest 동결

`code_files`에는 followup/*.py 전체와 scripts/fp_sc_followup.py를 등록한다. `baseline_sources`에는 runner.SOURCES_REQUIRED의 모든 원본 파일 해시를 등록한다. `input_files`에는 두 FFD banks, case NPZ, model JSON, 선행 receipt, optional domain contract를 모두 포함한다. `environment`는 실제 Python/NumPy의 정확 버전이다.

다음 식은 manifest 작성의 보조일 뿐 실행 승인 생성이 아니다.

```python
from pathlib import Path
from qclean_uwb.fp_sc.followup.runner import code_paths, SOURCES_REQUIRED
from qclean_uwb.fp_sc.followup.contracts import sha256, digest, Policy
root = Path('.').resolve()
code_lock = {p: sha256(root / p) for p in code_paths(root)}
source_lock = {p: sha256(root / p) for p in SOURCES_REQUIRED}
code_lock_sha256 = digest(code_lock)
policy_sha256 = Policy(**policy_dictionary).sha
```

`stage_config[stage].case_ids`는 기대 목록 전부다. E3-03은 `calibration_case_ids`, `min_samples`가 추가된다. E5-01/02에는 실제 hardware_id를 등록한다. E4-01/02는 R2/R4/R5×B0/L2×Full/Native-LoS×seed0~9/40~59 격자를 요구한다. 모든 case의 t[0]=0이어야 한다. 다른 seed 집합/범위를 사용할 때는 해당 검증기와 계약을 새 버전으로 함께 수정한다.

모델 JSON은 E3-03이 생성한 F00/F01/F11 map이다. 같은 run에서는 내부 cache로 연결된다. 다른 run에서 이어서 쓰려면 `models_by_case`와 `input_files`에 등록한다. heldout route, policy SHA, bias/channel/noise domain, train sample IDs가 맞지 않으면 중단한다. E4-03은 outer_fold_policies/outer_fold_models_by_case를 따로 등록한다. E5-03은 external_environment_contract와 새로운 environment_id/corpus=external을 요구한다.

## 4. 나중의 승인·실행·재시도

승인자는 manifest 파일의 SHA256, code_lock_sha256, 허용 stage, actor/issued_utc를 새 승인에 기록한다. `execute_science=true`는 이번 코드 개발 승인에서 가져오지 않는다. 일괄 실행이 필요하면 승인된 순서로 stage를 나열하되 선행 scientific HOLD를 무시할 수 없다. exploration으로 계속 계산할 범위는 `exploratory_after_nonpass`에 명시한다. optional 단계는 optional_stages에 따로 등록한다.

```sh
python scripts/fp_sc_followup.py run --repo . --manifest frozen_manifest.json --approval signed_scope.json --output research/FP_SC_FOLLOWUP_RUN_001 --stages E1-02 E1-03 E2-01 E2-02 E2-03 E2-04 E3-01 E3-02 E3-03 E3-04
python scripts/fp_sc_followup.py audit --directory research/FP_SC_FOLLOWUP_RUN_001
```

실패 시 기존 RUN_MANIFEST/부분 출력은 보존된다. 코드·입력·정책 변경 시 새 SHA와 새 출력 경로를 사용한다. 이전 단계 성공 receipt를 실제 파일 hash로 등록하고 실패한 단계부터 재개한다. 실패한 결과를 지우거나 같은 폴더를 덮어쓰는 resume은 제공하지 않는다.

E5는 지정 기기에서 실제 arrival pacing·싱크 flush를 포함해 실행한다. 단순 fake-clock 테스트와 GitHub runner 수치로 실기기 5Hz PASS를 선언하지 않는다. 이 변경은 workflow를 추가/수정하거나 dispatch하지 않는다.


## 5. 수동 실행 사전점검 (2026-11-05 감사 패치)

**GitHub Actions는 불필요하며 이 패치는 Actions를 실행하지 않는다.** 원본 `74df3c99` 대신 별도 `audit/fp-sc-e1e5-local-readiness-20261105` 브랜치를 checkout한다. 원본 FP/EKF 정책·FFT·갱신 수식과 E0/E1-01 파일은 변경하지 않았다.

현재 테스트 환경에서 증명할 수 있는 것은 문법/계약/합성 동작이며, **실제 RF·FFD payload·실기기 성능 검증은 별개의 실행**이다. 사전점검의 PASS를 과학적 PASS로 해석하지 않는다.

### (1) 로컬 합성 회귀

Linux/WSL/macOS Bash:

```bash
export PYTHONPATH=src OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m unittest discover -s tests -p 'test_fp_sc_followup.py' -v
python -m unittest discover -s tests -p 'test_fp_sc_manual_readiness.py' -v
python -m compileall -q src/qclean_uwb/fp_sc/followup scripts/fp_sc_followup.py tests/test_fp_sc_manual_readiness.py
python scripts/fp_sc_followup.py plan
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
$env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
python -m unittest discover -s tests -p test_fp_sc_followup.py -v
python -m unittest discover -s tests -p test_fp_sc_manual_readiness.py -v
python -m compileall -q src/qclean_uwb/fp_sc/followup scripts/fp_sc_followup.py
python scripts/fp_sc_followup.py plan
```

실제 소스, FFD bank, NPZ, model은 반드시 **실제 바이트와 정확한 SHA256**를 동결한다. Git LFS pointer만 존재하면 실행을 막는다. 별도의 실험 승인 없이 `APPROVAL_TEMPLATE.json`의 `execute_science`를 자동으로 true로 바꾸는 기능은 없다.

### (2) E1-01 원본 증거를 후속 prerequisite으로 연결

원래 E1-01의 `RUN_MANIFEST.json`은 후속 실행기의 `study_id/execution_status/numerical_qa_pass` 형식을 따르지 않는다. 따라서 **원본 결과와 별도 재검산이 모두 완료된 경우에만** 아래 변환을 한다. 두 디렉터리는 repository 내부에 있어야 한다. 아래의 `...`는 예시이므로 **실제 존재하는 경로로 반드시 바꿔야 한다**.

```bash
python scripts/fp_sc_followup.py adopt-e1 \
  --repo . \
  --run-dir "research/.../E1_20261105/RUN_001" \
  --review-dir "research/.../E1_20261105/audit/REVIEW_001" \
  --output research/FP_SC_FOLLOWUP_E1_PARENT.json
```

변환은 E1-01 전체 6,320 waveform/12,640행, run/review 아티팩트 해시, 별도 checker의 수치 재현 여부를 재확인한다. 생성되는 prerequisite은 `execution_status=COMPLETE`, `numerical_qa_pass=true`지만 **`scientific_gate=HOLD_RESULT_REVIEW`**이다. 95% 문턱이나 경로별 실패를 임의로 PASS로 승격하지 않는다. 외부 독립승인도 표시하지 않는다.

생성된 receipt와 그 `source_files`의 네 파일을 `manifest.input_files`에 **각각 실제 SHA256**로 등록하고, `manifest.prerequisite_receipts["E1-01"]`에 receipt 경로를 등록한다. H0/E1 결과가 기술적으로 완료되지 않은 경우 변환은 차단된다.

### (3) preflight → run → audit

동결된 manifest/approval을 준비한 후 (예시는 단계 순서만 설명하며 실제 실행승인이 아니다):

```bash
python scripts/fp_sc_followup.py preflight \
  --repo . --manifest frozen_manifest.json --approval approved_scope.json \
  --stages E1-02 E1-03 E2-01

python scripts/fp_sc_followup.py run \
  --repo . --manifest frozen_manifest.json --approval approved_scope.json \
  --output research/FP_SC_FOLLOWUP_RUN_001 \
  --stages E1-02 E1-03 E2-01

python scripts/fp_sc_followup.py audit --directory research/FP_SC_FOLLOWUP_RUN_001
```

`preflight`는 계산 결과를 저장하지 않는다. 코드·원본·입력 파일의 SHA, 환경 버전, 선행 receipt, case ID/표본수, 단계 순서, 120/240 case 메타데이터, E3-03 학습 표본, 모델 파일·SHA·대상 route/domain, E4/E5 NPZ 시간/pose_id를 확인한다. 실질적인 RF/FFD·EKF 계산은 `run`에만 있다. `preflight=PASS_LOCAL_PREFLIGHT_NO_SCIENCE`는 실행 준비 형식 점검 결과일 뿐이다.

E4/E5를 포함하여 모든 단계에서 원본 CFR case들을 **case 단위로 읽고 직후 해제**한다. E4 seed 집계에는 trace 전체가 아니라 필요한 지표만 남긴다. 메모리가 급격히 늘어나는 문제를 줄이지만, 단일 case 자체의 메모리 사용과 E5 실제 도착속도 처리 시간까지 보증하지 않는다.

작업 도중 실패하면 파일을 지우거나 같은 output에 다시 쓰지 않는다. `RUN_MANIFEST.json`은 `FAILED_PRESERVED`로 남고 생성된 파일의 hash index도 저장된다. 이 경우 `audit`는 `HOLD_INCOMPLETE_RUN`만 반환하며 PASS하지 않는다. 다시 실행하려면 원인 수정 후 새 계약/새 output 경로를 사용한다.

### (4) 실전 데이터에만 남는 미검증 항목

- E1-01 후보 가용성이 95% 이상인지, 누락 후보 episode가 안전한지는 실제 원본 결과 재검산 필요
- R2/R4/R5의 입력 시간축과 source FFD(native detector)가 본 실험 조건과 일치하는지 실제 데이터에서 검증 필요
- E3 보정모델의 각 stratum 최소 표본, route-heldout, covariance 효과는 실제 수치 결과 검증 필요
- E4 720/1,440개 arm-trajectory의 전체 실행 시간·메모리·성능은 실행 전까지 미확정
- E5의 5 Hz 시간 규약·장애·실제 출력 sink flush는 해당 실기기에서만 판정 가능

별도의 과학적 조건 변경·새 모델 재학습·실제 RF 계산은 이번 수동 실행 준비 패치의 범위가 아니다.
