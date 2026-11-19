# Corridor 원거리 Kriging 실행 기록 — 기준선 재현 실패로 중단

판정: **STOP_BASELINE_PARITY_FAIL / 유효한 EKF A/B 결과 없음**.

2026-11-19 15:14:00–15:14:40 KST에 Snowball의 KMS 계정으로 원본 커밋 `205dbd1c57e0e09fb605c40fe550c89ed08bd2b5`의 `smoke`를 실행했다. 종료 코드는 1이다. [사전 계약](../PLAN_KO.md)의 허용오차를 초과했으므로 `explore` 40개 조건 실행과 집계를 진행하지 않았다. 기준이나 동결 원본은 수정하지 않았다.

| 기준선 검사 | 동결 POINT_B | 이번 재생 | 절대 차이 | 허용치 |
|---|---:|---:|---:|---:|
| B0 / seed30 / R2 / F2SKRWV Heading RMSE (°) | 1.3665340961341461 | 1.3665452243647542 | 0.000011128230608115075 | 0.00000001 |

오차는 허용치의 약 1,113배다. 절대 수치가 작더라도 사전 게이트는 실패다. 해당 검사는 최초 실패에서 종료하므로 나머지 조건의 기준선 일치도 확인되지 않았다. smoke 내부에서는 후보 arm의 궤적도 계산되지만, 재현 게이트를 통과한 `RESULT.json`은 한 개도 저장되지 않았다. 후보 성능 비교나 개선·악화 결론을 게시하지 않는다.

## 복원과 검증

기존 안내의 호스트 경로 `/home/claude/{m8,m8cal,sionna-resimulation}`는 없었다. 별도 디렉터리 `/home/KMS/FAR_KRIGING_AB_20261119_01a1f269/attempt_02`를 컨테이너 안에서 `/home/claude`로 연결했다. 다른 작업의 파일이나 컨테이너를 변경하지 않았다.

- GitHub 보관본의 sweep CSV, Kriging 초모수, V 분산표, 센서·필터·평가 코드를 사용했다. `SWEEP_CAL_B.npz`는 17자리 CSV를 round-trip 방식으로 읽어 복원했으며, 이 NPZ를 포함한 교정 자산 4개 모두 기존 SHA-256과 정확히 일치했다. 재학습이나 분산 재보정은 하지 않았다. [RESTORE_CHECKS.json](RESTORE_CHECKS.json)
- 원본 reference online/evaluator NPZ는 LFS에서 확보하고 기존 계약 해시와 대조했다. FFD bank는 기존 Snowball 사본을 읽기 전용 연결했으며, 기존 모델 로더의 해시 검사를 통과했다. 원본 입력 파일을 덮어쓰지 않았다.
- 기존 `gen_inputs_ext.py generate 30 49`로 Phase B 입력 120개를 생성했다. **파일 SHA-256은 기존 INPUT_INDEX_EXT와 0/120 일치**했다. 원본 Phase B NPZ 자체를 확보한 것은 아니므로 동일 바이트 입력으로 재생했다고 주장하지 않는다. [INPUT_HASH_CHECKS.json](INPUT_HASH_CHECKS.json)
- 같은 생성기로 과거 seed10–29 입력 120개를 재생성해 보관 원본과 배열을 비교했다. `ds` 최대 차이는 `1.3877787807814457e-17`, 나머지 필드는 bit-exact였고 기존 `1e-10` 검사에 통과했다. 이는 **seed30–49의 원본 바이트 일치를 증명하지 않는다**. [INPUT_PARITY_10_29.json](INPUT_PARITY_10_29.json)
- 실행 환경은 기존 Snowball Docker 이미지 `sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`, Python 3.11.15, NumPy 2.4.6, pandas 3.0.6, SciPy 1.17.1이다. 기존 Phase B 입력 생성 기록은 NumPy 2.5.3이다. 환경과 파일 해시 차이는 확인했지만, 이번 RMSE 불일치의 원인으로 확정하지 않았다.

역할은 IMPLEMENTER의 자기 검사이며 독립 감사나 과학적 채택이 아니다. 적용 지침은 저장소에 동결된 `gm_theta_m6/inputs/{COMMON_CONTRACT,ROLE_IMPLEMENTER}.md`이며 해시는 [EXECUTION_RECEIPT.json](EXECUTION_RECEIPT.json)에 기록했다. 새 센서 seed50–69, 추가 RF, 다른 환경의 실험, G-T2/G-V 확인 자산 평가를 수행하지 않았다.

## 실패 기록과 보존 상태

초기 복원 스크립트는 체크섬 JSON 키에 확장자를 잘못 포함해 `KeyError`로 종료했다. 수정 후 별도 `attempt_02`에서 복원을 통과했다. 최초 실패 디렉터리와 로그를 보존했다. Phase B 파일 해시 검사 실패도 별도 기록했으며 성공으로 바꾸지 않았다.

새로 만든 7개 컨테이너는 모두 종료 상태이며 실행 중인 작업은 없다. 실패/복원 자료와 생성 입력은 위 Snowball 작업 공간에 보존했다. 이 폴더에는 로그, 실행 인자·종료 상태, 입력/소스 해시 목록과 복원 스크립트를 업로드한다. `BUNDLE_MANIFEST.json`은 정확한 커밋에서 읽은 입력/코드 목록이며, 보관된 NPZ나 bank 자체의 중복 업로드는 하지 않는다.

이번 실행에서 XY·Heading RMSE, Pose95·Heading95, NEES 및 거울해에 대한 유효한 A/B 비교는 얻지 못했다. 재개에는 원본 Phase B 입력과 실행 환경 확보 또는 원인 규명 후 기존 게이트 재통과가 필요하다. **원거리 Kriging 개선이나 CONDITION_PASS를 주장할 수 없다.**

## 실행 순서

1. `prepare_far_bundle.py`: 고정 커밋에서 탐색 실행용 자산과 소스를 추출한다. 저장소 루트에서 실행한다.
2. `restore_far_workspace.py`: 비어 있는 별도 작업 공간을 `/home/claude`로 연결한 컨테이너에서 수행한다. bank 디렉터리는 `/banks`에 읽기 전용 연결한다.
3. `python /home/claude/m8/gen_inputs_ext.py generate 30 49`
4. `check_far_inputs.py`: Phase B 원본 파일 해시 대조. 이번에는 실패했다.
5. `python /home/claude/m8/gen_inputs_ext.py parity`: 과거 grid의 배열 재현 검사. 이번에는 통과했다.
6. `python .../far_kriging_ab_20261119/run_far_kriging_ab.py smoke`: 이번에는 기준선 게이트 실패로 중단했다. smoke와 입력 검사는 일부 시간 중첩됐으며, 모든 결과를 확인한 뒤 본 실행을 진행하지 않았다.

전체 Docker 명령, 시간, image ID 및 종료 코드는 실행 receipt를 참조한다. 이 기록은 실패한 실행의 증거이며, 입력 해시 실패를 우회해 본 실행할 권한이나 절차가 아니다.
