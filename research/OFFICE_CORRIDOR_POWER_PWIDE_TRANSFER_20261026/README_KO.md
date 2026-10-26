# Office -> Corridor POWER / PWIDE / polarization gate transfer — code V1

**Status: CODE IMPLEMENTED / SYNTHETIC UNIT QA PASSED / REAL RF FIT & REPLAY NOT EXECUTED.**

## What is implemented

- Pinned release names, archive SHA256, array SHA256, and audited RF row counts (O01=192, O02=207, O03=412).
- Explicit `fetch` verifies archive SHA256, and secure `prepare` extraction rejects tar links/path traversal. **Nothing downloads automatically**.
- Office source loader calls the original `research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py` at commit `034e57a...`: validates release receipts, reconstructs the entire `.25 s` motion with the original route generator, and requires public `RADIO_POSE.csv` **byte identity**. Never does timestamp-nearest joins or RF interpolation.
- `H_FULL.npy`/`H_DIRECT_LOS.npy`/`LOS_EXISTS.npy` hash checks. Blocked Office samples remain in the saved source table, but are excluded from supervised calibration (`valid_for_training=False`, GT labels NaN).
- Frozen Hann, 4× zero-padding, strongest-port 30% FP and shared two-port FP, offset `s(fp±1,2,4,8)` observer, first-path power and range. Uses original TX+ (`H[:,:,:,0]`).
- SourceFFD at **source GT only** supplies Office supervised errors `e_r`, `e_s`. `s_direct_los_audit_only` records direct-LoS parity separately. All target inference paths explicitly use only observable RF and prior state, not target LoS or GT labels.
- Source-only **POWER_BIN_JOINT**: one-dimensional power Ridge, source tertile-bin residual mean/covariance, shrinkage, covariance floors, diagonal `POWER_DIAG` inference.
- Office **LOO-route** POWER teacher for supervised residual label `delta=e_s-mu_power_inner`. Repeated physical `(x,y)` is spatially embargoed within teacher folds. Caution: 3 routes share one Office scene; not 3 independent environments.
- Frozen CIR-only PCIR and CIR+`d0` PWIDE: HistGradientBoostingRegressor matching P1R settings, 3×±20-degree source-only prior augmentation.
- Office-only gate `tau=quantile_95(|d0_GT_source|)` as a **preliminary proxy**, not independently calibrated to prior errors. D0 / state-aware gating supported.
- Target 4-state P2 recursive EKF replay at **R2/R4/R5 only**, frozen sensor-v2, SourceFFD and original P2 trace inputs. Default arms: `C_POWER`, `C_PWIDE`, `O_POWER`, `O_PWIDE`, `O_POWER_C_PWIDE`, `O_PCIR`. `--exploratory-gates` additionally enables `O_POWER_G`, `O_PWIDE_G`, `O_POWER_STATE_G`, `O_PWIDE_STATE_G`.
- True range-only 1D update when polarization is gated (99% chi2_1=6.635), otherwise joint 2D (99% chi2_2=9.210). Joseph covariance, per-arm own-prior PWIDE `d0`, normalized PSD audit.
- Existing training artifacts and target data never changed by import or `--help`.

## Two immutable checkouts

1. **AUDIT**: `myoungsunk/sionna-resimulation` commit `034e57a7209a3bd1bb8857b24fd85c64942e1258`. The exact T2 release receipt and full motion recovery must be found at `research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py`.
2. **P2**: `myoungsunk/sionna-resimulation` commit `0686b23ceeefb696bc158b32b39f8077c564ef5d`. The original R2/R4/R5 P2 paths and `V.one(...TRACE.npz)` data must be available at runtime. The frozen P2 checkout is not assumed to contain the AUDIT loader.

The checkouts are separate because the frozen P2 and T2 versions do not live together at those commits. Do not substitute `main` for either. The full historical RF assets / bank and T2 source dependencies must be mounted as in their existing workflows; this ZIP intentionally does not redistribute gigabytes of original sources.

## Explicit CLI — each command is a separate user-controlled step

```bash
python -m pip install -r requirements.txt
python office_transfer_cli.py --help
pytest -q tests/test_core.py
```

When the user authorizes fetching RF files, **explicitly** execute:

```bash
python office_transfer_cli.py fetch \
  --cache /mnt/transfer/release_cache
```

Next, explicitly **prepare source records, without training**:

```bash
python office_transfer_cli.py prepare \
  --audit-checkout /work/sionna-audit-034e57a \
  --cache /mnt/transfer/release_cache \
  --extracted /mnt/transfer/source_archives \
  --out /mnt/transfer/prepared_office
```

Next, explicitly train **Office only**:

```bash
python office_transfer_cli.py fit \
  --audit-checkout /work/sionna-audit-034e57a \
  --source-table /mnt/transfer/prepared_office/OFFICE_SOURCE_LABELS.csv.gz \
  --source-qa /mnt/transfer/prepared_office/OFFICE_SOURCE_QA.json \
  --out /mnt/transfer/models
```

Last, **only after source frozen and separate approval**, target replay example:

```bash
python office_transfer_cli.py replay \
  --target-checkout /work/sionna-p2-0686b23 \
  --target-artifacts /mnt/frozen-p2-artifacts \
  --models /mnt/transfer/models/OFFICE_TRAINED_MODELS.joblib \
  --corridor-models /mnt/transfer/corridor_models/R2/R2_C_PWIDE.joblib \
  --corridor-qa /mnt/transfer/corridor_models/R2/R2_C_PWIDE_QA.json \
  --train-qa /mnt/transfer/models/OFFICE_TRAIN_QA.json \
  --source-qa /mnt/transfer/prepared_office/OFFICE_SOURCE_QA.json \
  --input-manifest /mnt/transfer/frozen/R2_aA_m45_full_B0.json \
  --input-manifest-sha256 <pre-frozen-manifest-sha256> \
  --channel full \
  --case R2_aA_m45 --bias B0 \
  --out /mnt/transfer/evaluation
```

This command requires original frozen P2 trace artifacts accessible to `V.one`, not supplied by this ZIP; it does not download or generate those target assets.

## Interpretation guards

### 3단계: 같은 정의의 C_PWIDE 대조군

`fit-corridor`는 평가할 경로 하나를 통째로 제외하고 나머지 두 경로의 Full 관측으로 학습합니다. 예를 들어 R2 평가는 R4/R5로만 학습한 파일을 사용합니다. 학습 경로가 서로 같은 장면에 있으므로 평가 경로의 모든 case 좌표와 거리 `1e-4 m` 이하인 학습 행을 먼저 제외합니다. 평가 경로 좌표는 이 공간 제외에만 사용하며, 해당 경로의 관측·라벨로 모델을 학습하거나 조정하지 않습니다.

Office와 Corridor는 같은 `PowerTransfer.fit`, `ResidualTransfer.fit`, 특징 전처리 및 HGB 구현을 공유합니다. 목표는 두 환경 모두 `delta = (s_full - h_s(GT)) - mu_POWER_inner`입니다. Corridor 내부 OOF에서는 검증 경로를 제외한 나머지 한 학습 경로로 POWER teacher를 학습하고, 여기에도 `1e-4 m` 공간 제외를 적용합니다. 행이 부족하면 임계값을 완화하지 않고 중단합니다. 특징 중앙값은 학습 자료에서만 구하며, ±20° 균일 prior 증강 3회와 HGB 설정·난수 시드는 Office와 같습니다. Corridor 증강에는 각 case의 실제 anchor/mount/height를 사용합니다.

| 암 | 유지하는 POWER 평균·분산 | PWIDE 학습 자료 | 비교 목적 |
|---|---|---|---|
| C_POWER | 고정 Corridor OOF | 없음 | 기존 기준선 |
| C_PWIDE | 고정 Corridor OOF | 평가 경로 제외 Corridor | Corridor 내 PWIDE 효과 |
| O_POWER | Office | 없음 | POWER 환경 전이 |
| O_PWIDE | Office | Office | Office 전체 보정 전이 |
| O_POWER_C_PWIDE | Office | 평가 경로 제외 Corridor | POWER를 고정하고 PWIDE 학습 환경 비교 |

`C_PWIDE`도 매 시점 자신의 prior로 `d0`를 다시 계산합니다. POWER의 `mu_s`는 유지하고 예측 잔차만 관측에서 추가로 뺍니다. `Vs`는 다시 보정하지 않습니다. `O_PWIDE`와 `O_POWER_C_PWIDE`를 비교하면 Office POWER를 고정한 PWIDE 학습 환경 차이를 볼 수 있습니다. `O_PWIDE`와 `C_PWIDE`의 차이에는 POWER 학습 환경 변경도 함께 포함됩니다. 경로 수·표본 수·mount 분포 차이까지 통제한 인과 효과나 독립 장면 반복시험이라고 해석하지 마십시오.

```bash
python office_transfer_cli.py fit-corridor \
  --target-checkout /work/sionna-p2-0686b23 \
  --target-artifacts /mnt/frozen-p2-artifacts \
  --held R2 \
  --input-manifest /mnt/transfer/frozen/R2_control_inputs.json \
  --input-manifest-sha256 "<pre-frozen-manifest-sha256>" \
  --out /mnt/transfer/corridor_models/R2
```

학습 입력 manifest는 `schema: CORRIDOR_CONTROL_INPUTS_V1`, `held: R2`, 고정 `target_commit`, `files`를 가집니다. `files`에는 `observations`(OBSERVATION_FEATURES_LABELS), `packets`(HP_PACKETS), `cases`(P0_INPUT_MANIFEST), 그리고 R2/R4/R5 전체 case마다 `<case_id>/samples` 키와 해당 파일 SHA-256이 있어야 합니다. 예측용 OOF 파일을 residual teacher 라벨로 재사용하지 않습니다. teacher는 각 내부 fold에서 공유 POWER 구현으로 새로 학습합니다.

평가 명령에는 다음 두 인자가 추가로 필수입니다. 모델과 QA의 해시·held 경로·학습 경로·lock·정의가 맞지 않으면 중단합니다.

```bash
--corridor-models /mnt/transfer/corridor_models/R2/R2_C_PWIDE.joblib \
--corridor-qa /mnt/transfer/corridor_models/R2/R2_C_PWIDE_QA.json
```

기본 평가는 위 5개 암과 `O_PCIR`의 총 6개입니다. 탐색 gate를 켜면 기존 Office gate 4개가 더해져 총 10개입니다. Full B0/L2와 Direct-LoS B0에서 같은 동결 모델을 사용하며 평가 명령은 학습하지 않습니다. **실제 RF 학습·평가는 아직 실행하지 않았고, 이하 1·2단계의 보류 항목은 단계 당시의 기록입니다.**

### 2단계 보완 사항 (2026-10-26)

1. **준비→학습→평가 연결**: `fit`은 `--source-qa`의 고정 소스 커밋, lock 해시, O01/O02/O03 개수·자료 해시·LoS parity 및 실제 CSV 해시를 확인합니다. 학습 모델 안에도 이 연결 정보를 저장합니다. `replay`는 모델을 역직렬화하기 전에 `--train-qa`, `--source-qa`, 모델 SHA-256을 확인하고, 로딩 후 모델 내부 연결 정보까지 대조합니다. 예전 코드로 생성한 QA 없는 모델은 재사용하지 않습니다.
2. **고정 입력 목록**: `--input-manifest`와 그 사전 고정 SHA-256이 필수입니다. 실험 실행기는 입력을 보고 자동 승인 목록을 만들지 않습니다. 아래 형식의 목록을 원본 P2 자료의 출처·조건을 확인하는 자료 준비 단계에서 확정하십시오. 실제 파일은 기존 `V.one`의 유일 경로 조건으로 찾고 해시를 대조합니다.
3. **C_POWER 기준선**: 원본 `strict_common.score_extra`로 `t>=30 s`의 heading RMSE·heading NEES·95% coverage·XY RMSE(cm)·anchor-range RMSE(cm)를 계산합니다. 원본 `results_strict/SB_SCORES.csv`의 같은 case/channel/bias, `BASE` 행과 비교하며 다섯 오차가 모두 **`1e-7` 미만**이어야 합니다. 실패하면 차단 QA만 기록하고 정상 결과 CSV는 저장하지 않습니다. 통과 시 C_POWER 상태·공분산 시계열도 보관합니다. 이 gate를 추가했다는 사실은 실제 RF 기준선이 통과했다는 뜻이 아닙니다.
4. **Direct-LoS 대조 조건**: `--channel los --bias B0`를 지원합니다. 고정 P2의 `los_features`, LoS TRACE·관측·OOF를 사용하고 원본 LoS RF와 pose ID 목록도 입력 manifest에 포함합니다. `los/L2`는 원본 P2 평가 조건에 없어 거부합니다. Full 평가에서는 LoS 관측을 모델 입력으로 사용하지 않습니다. LoS 대조는 별도의 이상적 채널 조건이며 실제 로봇에서 사용 가능한 입력이라는 주장이 아닙니다.
5. **gate 해석 분리**: 기본 실행은 `C_POWER`, `O_POWER`, `O_PWIDE`, `O_PCIR`만 평가합니다. `--exploratory-gates`를 선택한 경우에만 네 gate 암을 추가하고 QA에 `EXPLORATORY_GT_PROXY`를 기록합니다. 실제 source-only 재귀 prior를 이용한 임계값 보정은 미완료이며, 이 단계에서 임계값을 새로 맞추거나 보정 완료로 간주하지 않습니다.
6. **검증·기록**: pose ID 중복·누락, 시간 순서, 비정수 ID, 비유한 관측·특징을 차단합니다. 출력은 새 디렉터리에만 작성합니다. QA에는 명령, UTC 시각, Python·주요 패키지 버전, 구현·입력·산출물 해시가 포함됩니다. 실험 완료 직전 입력과 모델 해시를 다시 확인합니다. 원본 T2 함수를 사용하는 합성 자료 통합시험과 원본 P2 갱신·채점 함수를 사용하는 기준선 회귀시험을 추가했습니다.

입력 목록 예시입니다. 아래 해시는 실제 자료의 값으로 채워야 하며, 예시 자체로 실행할 수 없습니다.

```json
{
  "schema": "TRANSFER_TARGET_INPUTS_V1",
  "target_commit": "0686b23ceeefb696bc158b32b39f8077c564ef5d",
  "condition": {"case": "R2_aA_m45", "channel": "full", "bias": "B0"},
  "files": {
    "R2_aA_m45_full_B0_TRACE.npz": "<sha256>",
    "OBSERVATION_FEATURES_LABELS.csv.gz": "<sha256>",
    "OOF_PARAMETERS.csv.gz": "<sha256>",
    "HP_PACKETS.csv.gz": "<sha256>",
    "SB_SCORES.csv": "<sha256>"
  }
}
```

LoS 조건은 condition/channel과 TRACE 이름을 `los`로 바꾸고 `files`에 `los_path`, `samples_path` 두 키와 해당 실제 파일 해시를 추가합니다. manifest 파일 자체의 SHA-256을 `--input-manifest-sha256`으로 전달합니다. 해시 일치는 내용의 동일성을 확인하며 학습 누수 없음이나 원본 출처의 진위를 단독으로 증명하지 않습니다.

**검증 한계**: 실제 Release와 RF로 학습·평가하지 않았습니다. T2 통합시험은 완전한 motion CSV가 들어 있는 합성 아카이브를 사용하므로 원본 경로 생성기로 motion을 복원하는 분기까지 검증한 것은 아닙니다. 기존 `reconstructed_motion`이 남은 추출 디렉터리는 원본 T2의 재사용 영수증 문제로 차단될 수 있으므로 자료 준비 재실행에는 새로운 `--extracted` 경로를 사용하고 기존 자료를 보존하십시오. C_PWIDE는 3단계에서 추가하며 모든 단계 종료 전에는 커밋하지 않습니다.

### 1단계 주요 결함 수정 (2026-10-26)

- `prepare`: 원본 T2가 요구하는 `data/` 하위 파일과 루트의 `ARCHIVE_CONTENTS_AND_SHA.json`을 생성합니다. 영수증은 추출 성공 후 마지막에 기록합니다. 기존 추출 자료는 아카이브 SHA-256, 파일 목록, 크기, SHA-256을 다시 확인합니다. 불완전한 디렉터리는 덮어쓰지 않습니다.
- `replay`: `--target-artifacts`가 필수입니다. `--target-checkout`, `--target-artifacts`, `--out`을 각각 `PJ_SOURCE_ROOT`, `PJ_ART`, `PJ_OUT`에 연결한 뒤 원본 P2를 가져옵니다. 기존 환경변수가 다른 경로를 가리키면 중단합니다. 새 프로세스에서 해당 변수를 해제하거나 같은 경로로 설정하십시오.
- 가져온 모듈의 실제 경로와 Git blob을 확인합니다. 다른 체크아웃의 모듈이 메모리에 남아 있으면 중단합니다. 검증용 체크아웃은 저장소 루트이고 고정 HEAD여야 하며, 추적 파일의 수정·삭제·스테이징 변경 및 추적되지 않는 실행 소스가 없어야 합니다. 추적되지 않는 RF 데이터는 허용합니다.
- 평가 출력 디렉터리는 소스와 입력 자료 디렉터리와 분리합니다. 실제 경로, 모듈 blob, 사용한 TRACE/관측/OOF/HP 파일 경로와 SHA-256을 평가 QA에 기록합니다. 이 기록은 입력의 사전 승인 또는 학습 누수 검증을 대신하지 않습니다.

검증 범위는 합성 자료와 임시 Git 저장소를 사용하는 회귀시험입니다. 원본 T2 `receipt_index` 함수의 고정 커밋 사본으로 추출 계약을 확인합니다. 전체 T2 자료 준비, 실제 Office RF 학습, Corridor 재귀 평가는 아직 수행하지 않았습니다.

후속 단계는 준비→학습→평가 증거 연결, 기존 C_POWER 결과 일치, 추가 검증 보완, 같은 정의의 Corridor 학습 C_PWIDE 대조군입니다. 모든 수정이 끝난 뒤 커밋하며 1단계에서는 커밋하지 않습니다.

### 해석 범위

- Only source `LOS_EXISTS=true` examples get ground-truth labels; O03 `false` is preserved and not silently synthesized.
- Source labels depend on source GT and SourceFFD. Target GT is allowed in the preexisting sensor builder (to reproduce synthetic motion) and **offline scoring only**, not prediction, fit, gate, or parameter decisions.
- POWER+PWIDE retains POWER's packet-wise `Vs`, as in frozen Ladder3, to isolate correction-mean impact. A new source-calibrated `R_s` and R-only/update-only ablation would require a separate pre-registered extension.
- Gate uses **raw** `d0=z_s-h_s(x^- )` consistently for POWER and PWIDE. Office source GT residual quantile is not proven to be a correct online prior gate threshold. Treat gated results exploratory until source-only prior calibration is performed.
- `O_POWER` trained on Office, `C_POWER` originally held-corridor Power from P2; the two have different training inputs. Do not train on Corridor to improve Office-transfer candidate.
- This code *has not been integration tested with downloaded O01/O02/O03 assets or P2 frozen traces*. Unit tests use synthetic arrays and exercise the math/API gates. The published release and original official receipt were verified using GitHub metadata, not re-downloaded in this turn.
- Report case-level paired Heading RMSE and NEES and route-level scorecards, not packet-based independent significance.

## Frozen upstream sources

- Office T2 manifest: https://github.com/myoungsunk/sionna-resimulation/blob/034e57a7209a3bd1bb8857b24fd85c64942e1258/research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/MANIFEST.json
- Office T2 loader: https://github.com/myoungsunk/sionna-resimulation/blob/034e57a7209a3bd1bb8857b24fd85c64942e1258/research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py
- Frozen P2: https://github.com/myoungsunk/sionna-resimulation/tree/0686b23ceeefb696bc158b32b39f8077c564ef5d/research/PJ_D0_CIR_P2_RECURSIVE_20261022
- POWER: https://github.com/myoungsunk/sionna-resimulation/blob/0686b23ceeefb696bc158b32b39f8077c564ef5d/research/R5_N4B_20261015/n4b_rf_errors.py
