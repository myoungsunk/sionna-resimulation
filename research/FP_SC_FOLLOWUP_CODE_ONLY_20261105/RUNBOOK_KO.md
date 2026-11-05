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
