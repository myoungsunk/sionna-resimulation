# Office Mount 0° / 45° 학습 입력 준비

2026-10-27, Snowball KMS에서 **입력 준비와 검증까지 완료**했다. 모델 학습, 재귀 평가, RF 재시뮬레이션은 실행하지 않았다. 기존 45° 코드와 `lock.json`, 원본 RF 및 시간순 자료는 보존했다.

## 데이터 범위와 실제 검증 결과

| 경로 | 각 Mount의 RF 표본 | 각 Mount의 시간순 위치 표본 | 각 Mount의 유효 학습 후보 | 각 Mount의 차폐 표본 |
|---|---:|---:|---:|---:|
| O01 | 192 | 461 | 192 | 0 |
| O02 | 207 | 521 | 207 | 0 |
| O03 | 412 | 1,175 | 176 | 236 |
| **0°와 45° 합계** | **1,622** | **4,314** | **1,150** | **472** |

차폐된 472행도 삭제하지 않았다. 해당 행의 `e_r`, `e_s`, `d0_gt_source`, `h_s_gt_source`는 결측값이며 `valid_for_training=False`다. 따라서 **두 Mount 모두 준비됐다는 의미는 모든 표본이 현재 보정 학습에 유효하다는 의미가 아니다.**

6개 케이스 모두 원본 해시, 주파수·배열·LoS 마스크, 시간 순서와 RF-전체 위치의 정확한 조인, 장착각, Full 관측 재현, Direct-LoS 일치 검사를 통과했다. SourceFFD의 편파 관측과 독립 Direct-LoS 관측의 최대 절대 차이는 **2.65492463599748e-6**, 동결된 허용치는 **0.05**다.

기존 M45 검증 영수증에는 `mount_deg` 필드가 없다. 이 구형 형식만 명시적으로 지원하며, 케이스 ID 및 RF/전체 위치의 `yaw_antenna_deg - yaw_body_deg = 45°`를 함께 검증한다. M0는 명시적인 장착각 필드가 필요하다.

## 산출물

이 문서와 같은 폴더의 [`mount_inputs_20261027/`](mount_inputs_20261027/)에 저장했다.

| 파일 | 용도 |
|---|---|
| `PREPARED_FINAL/FEATURES.csv.gz` | GT를 제외한 Full 관측 특징, 식별자, 시간, 장착각 |
| `PREPARED_FINAL/LABELS_GT_SOURCE_ONLY.csv.gz` | Office source GT 라벨, 유효 마스크, 감사 전용 값 |
| `PREPARED_FINAL/OFFICE_SOURCE_LABELS.csv.gz` | 향후 기존 보정 코드에 전달할 통합 표. GT가 포함되어 있으므로 전체 열을 입력 특징으로 사용하면 안 됨 |
| `PREPARED_FINAL/MOTION_TIMELINE.csv.gz` | 0.25초 간격의 전체 위치 4,314행과 `rf_sample`. RF가 없는 시점에 RF 특징을 생성하지 않음 |
| `PREPARED_FINAL/SPLIT_GROUPS.csv.gz` | Mount/재방문에 공통인 공간 그룹과 경로/공간 식별자 |
| `PREPARED_FINAL/FEATURE_CONTRACT.json` | 허용 특징 열과 결측 처리·분할 계약 |
| `PREPARED_FINAL/OFFICE_SOURCE_QA.json` | 케이스별 검사, 원본 모델 모듈 Git blob, 구현/산출물 해시, 실행 인자와 라이브러리 버전 |
| `PREPARED_FINAL/VALIDATION_RECEIPT.json` | `PREPARED_DATA_VALIDATION_PASS`, 학습/평가 미실행 |
| `INPUT_MANIFEST.json` | 6개 RF 입력, 전체 위치 파일, 원본 은행과 코드의 동결 계약 |
| `FROZEN_MANIFEST_SHA256.txt` | 외부에서 고정해 전달할 입력 매니페스트 해시 |
| `prepare_final.log`, `validate_final.log`, `tests_final.log` | 실제 생성·재검증·11개 회귀 검사 기록 |
| `DELIVERY_RECEIPT.json`, `SHA256SUMS.txt` | 실행 환경, 보존 확인, 전달 파일의 해시 |

RF 표는 각 케이스 안에서 원래 `pose_id` 및 `t_s` 순서를 유지한다. 조인 키는 `case, route, mount_deg, pose_id, t_s`다. Mount를 빼고 조인하면 같은 경로의 두 관측이 혼합될 수 있다.

## 특징과 라벨

Full 채널에서 TX 인덱스 0을 선택하고, 두 RX의 강한 포트에서 Hann 창·4N IFFT·30% 문턱으로 첫 경로 탭을 정한다. 두 RX는 같은 탭을 사용한다. 기존 `observe_port`를 재사용하며 native `FIRST_PATH.csv`의 탭·거리·편파 관측과 대조한다.

- POWER 입력: `log_fp_power`.
- PWIDE 입력: 기존 `P_FEATURES` 19열. 첫 탭의 `sF_+0`, 전력, 탭 번호와 ±1/2/4/8탭의 편파값·차이값이다.
- `range_m`, `s_fp`는 Full 관측이다. `mount_deg`는 식별/관측 모델 설정이며 기존 19열 정의를 임의로 변경하지 않았다.
- `e_r = range_m - h_r(GT, mount_deg)`.
- `e_s = s_fp - h_s(GT, mount_deg)` 및 `d0_gt_source = e_s`.

`h_r`, `h_s`는 동결된 SourceFFD이며 케이스별 **실제 Mount 0° 또는 45°**를 전달한다. 거리 모델의 기존 바이어스 `-0.5315983906250129 m`도 유지한다. GT와 Direct-LoS 값은 라벨/감사 표에만 둔다. SourceFFD의 원본 은행 보간 초기화는 수행하지만 보정 회귀기·스케일러·결측 대체값을 데이터에 맞추는 학습은 실행하지 않는다.

## 향후 학습 시 지킬 경계

`valid_for_training=True`인 1,150행만 현재 source 보정 라벨 정책에 해당한다. Office는 현재 Office→Corridor 프로토콜의 source이며, target GT를 특징·학습·임계값 선택에 사용하지 않는다.

분할은 **`UNASSIGNED_NO_TRAINING`**으로 남겨두었다. 동일 위치의 두 Mount/재방문을 무작위로 나누면 누수가 발생하므로 공간 그룹을 공유시켰다. 실제 학습 전에 기존 공간·경로 embargo를 적용해 fold를 정해야 한다. 동일 좌표의 그룹만으로 거리 기반 embargo 전체를 대체할 수 없다. 결측 대체, 표준화, 모델 선택은 정해진 학습 fold 안에서만 수행한다. 이번 1,150행은 준비된 후보이며 성능 검증이나 학습 완료 결과가 아니다.

## 실행과 재검증

새 진입점은 [`office_mount_inputs.py`](office_mount_inputs.py)다. 기존 45° 진입점과 lock을 수정하지 않는 별도 입력 준비 경로다. `freeze`, `prepare`, `validate`만 제공하며 학습 명령은 없다. 출력 경로가 이미 존재하면 덮어쓰지 않고 중단한다.

실행 당시 컨테이너 경로:

```text
/rf0  <- /home/KMS/OFFICE_M0_RF_20261026_01a17631          (읽기 전용)
/rf45 <- /home/KMS/ROUTE_FULL_RF_20261019_R01             (읽기 전용)
/work <- /home/KMS/OFFICE_MOUNT_INPUTS_20261027_01a17631
/work/audit_source_034e <- SourceFFD의 실제 Git checkout
/work/LP_plus45_bank.npz, /work/LP_minus45_bank.npz       (읽기 전용)
/work/BANK_MANIFEST.json
```

SourceFFD Git revision은 `034e57a7209a3bd1bb8857b24fd85c64942e1258`이다. 매니페스트의 `folder`, `motion_path`가 컨테이너 경로이므로 재검증할 때 동일한 입력을 위 경로에 마운트한다. 다른 위치로 옮길 경우 기존 매니페스트를 편집하지 말고 새 출력 위치에 다시 freeze한다.

컨테이너 안의 재현 명령:

```bash
python /work/code/office_mount_inputs.py freeze \
  --root0 /rf0 --root45 /rf45 --original-lock /work/code/lock.json \
  --audit-checkout /work/audit_source_034e --out /work/NEW_INPUT_MANIFEST.json

# 위에서 생성한 해시를 별도로 고정한다. 기존 전달 매니페스트의 해시는 아래와 같다.
# 7721497182a1418a3509cdf8ebd575e5057f217a55ef7e9e20ae6dc0069ac554
python /work/code/office_mount_inputs.py prepare \
  --manifest /work/INPUT_MANIFEST.json \
  --manifest-sha256 7721497182a1418a3509cdf8ebd575e5057f217a55ef7e9e20ae6dc0069ac554 \
  --audit-checkout /work/audit_source_034e --out /work/NEW_PREPARED

python /work/code/office_mount_inputs.py validate \
  --manifest /work/INPUT_MANIFEST.json \
  --manifest-sha256 7721497182a1418a3509cdf8ebd575e5057f217a55ef7e9e20ae6dc0069ac554 \
  --out /work/PREPARED_FINAL
```

`NEW_INPUT_MANIFEST.json`을 사용하면 해당 경로와 새 SHA-256을 prepare/validate 양쪽에 전달한다.

실행 환경은 기존 Sionna 환경에 Git 검증용 도구를 추가한 전용 이미지다. 물리 계산 코드와 Python 패키지는 변경하지 않았다. 이미지 ID와 정확한 실행 인자는 전달 기록에 저장했다. 11개 회귀 검사는 Windows와 실제 데이터 처리에 사용한 Snowball 환경에서 모두 PASS했다. 장착각 전달, 구형 M45 형식, 시간·해시 변조, 차폐 라벨 제외, GT 혼입 방지, 시간순 출력 검사를 포함한다.
