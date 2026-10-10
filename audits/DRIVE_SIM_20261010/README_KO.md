# DRIVE_SIM 통합 감사 기록

이 브랜치는 2026-10-10까지 수행한 감사의 코드·보고서·근거를 단계별로 모은 보존/검토 브랜치다. **L1 FAIL, F01/F02 OPEN, scientific_PASS=false를 유지한다.** 업로드는 모델 수정 또는 과학적 채택이 아니다.

기준 checkout은 `991da089e0723644b244fb663b37c519b6e941e2`다. 루트의 production source는 그 기준 그대로 두고, 서로 다른 시점의 실제 코드를 각 단계의 `source/`에 보존했다. 통합 과정에서 legacy EKF와 sensor-v2를 합병하지 않았다. 각 snapshot에는 실행에 필요한 `src/qclean_uwb`, `scripts/drive_sim`, tests와 해당 configs가 있다. 미커밋 변경도 원 파일 bytes와 SHA-256으로 기록했다. 과거 결과가 통합 브랜치의 최신 단일 runtime에서 생성됐다고 해석하면 안 된다.

| 단계 | 자료 | 실행 기준/판정 |
|---|---|---|
| 00 | [독립 감사](00_independent_audit/evidence/INDEPENDENT_SCIENTIFIC_AUDIT_KO.md) | 최초 감사와 provenance; 원자료는 외부 |
| 01 | [원래 1–7 실행 보고서](01_validation_repair/results/DRIVE_SIM_20261007/VALIDATION_REPAIR_20261008/FINAL_REPORT_KO.md) | 991da089 + dirty source; 입력 검사 수정, 조건부 R 채택 보류 |
| 01 | [metric 독립 검산](01_validation_repair/results/DRIVE_SIM_20261007/VALIDATION_REPAIR_20261008/METRICS_INDEPENDENT_CHECK_20261008/REPORT_KO.md) | NEES≈320.776, pose coverage=0은 산술 오류로 설명되지 않음 |
| 02 | [sensor-v2 2단계](02_sensor_v2_review/results/SENSOR_V2_STAGE2_20261008/FINAL_REPORT_KO.md) | 2337c33f + dirty source; 제한 2,048회, covariance guard 수정, 안정화는 미해결 |
| 02 | [원 sensor-v2 계약](02_sensor_v2_review/prior_sensor_work/results/SENSOR_V2_20261008/MODEL_CONTRACT.md) | 원 sensor 작업 및 보완 기록을 함께 보존 |
| 03 | [L1 재현](03_l1_reproduction/results/DRIVE_SIM_L1_STAGE3_20261008/FINAL_REPORT_KO.md) | 실제 FFD로 5/500 위반 재현; tap 보간·극점 yaw 결함 분리 |
| 04 | [실제 LUT 조회 분석](04_l1_exposure/results/DRIVE_SIM_L1_EXPOSURE_20261008/FINAL_REPORT_KO.md) | legacy 24 seed 정확 재생; 23,472조회 중 혼합429, 위반18/수용15, 극점0 |

03의 재현 harness는 02의 `source/scripts/drive_sim/*l1*stage3.py` 및 03 결과의 생성 당시 `source/` 파일을 참조한다. 04에는 정확 재생에 사용한 별도 legacy source 전체가 있다. 실행 당시 source hash는 원 PLAN/receipt, 게시된 파일 대응은 ARTIFACT_INDEX.json으로 추적한다.

## 현재 멈춘 지점

L1 원인 확인과 기존 필터의 실제 노출 분석을 마쳤고 모델 수정 전에 멈췄다. 현재 R2에서는 tap 보간 수정 검증이 우선이다. 극점은 near-vertical 적용 전에 별도 좌표 계약 수정이 필요하다. 평가 mask의 9,408조회에는 혼합/위반이 없지만 이전 갱신의 누적 영향과 F02 인과 기여율은 UNKNOWN이다. L2, 새 RF/Sionna, 후속 필터 비교, 로봇/하드웨어 실험은 이 게시 작업에서 실행하지 않았다.

## 게시 범위와 원자료 접근

- 보고서·명령·수치 요약·실제 query/innovation/gating JSON·source·기존 manifest를 게시했다.
- 큰 text/JSON은 byte 손실 없이 `.gz`로 압축 게시했다. ARTIFACT_INDEX.json의 `published_path`가 실제 Git 경로다. 원 보고서의 상대 링크가 압축 전 이름 또는 NPZ를 가리키는 경우 아래 복원 도구로 별도 폴더에 복원해서 읽는다. 원 보고서 본문과 manifest를 게시용 경로로 덮어 고치지 않았다.
- bank·H·LUT·NPZ 등의 binary 원자료는 **이번 Git 업로드에 포함하지 않았다**. 원본은 기존 로컬 artifact 경로에 그대로 있다. 모든 파일의 original_path/bytes/SHA-256 및 external_original 상태를 ARTIFACT_INDEX.json에 기록했다. `05_shared_inputs`에는 입력 inventory만 있고 raw payload는 없다.
- 원자료가 필요한 독자는 해당 보관본을 받아 같은 hash를 확인해야 한다. 이 브랜치만 clone하면 전체 RF/MC raw를 보유하거나 실행을 재현한 상태가 아니다. 원자료를 별도 원격 저장소나 Git LFS에 업로드한 것으로 주장하지 않는다.
- 역사적 harness의 절대 경로는 원문대로 보존했다. 다른 머신에서 실행하려면 동결된 입력과 해당 경로를 준비하거나 **별도 복사본**의 경로를 명시적으로 재설정해야 한다. 필수 자료가 없으면 실행 불가로 기록해야 한다.

## 무결성 확인과 별도 폴더 복원

repository root에서 다음 명령을 실행한다. 이 도구는 해시·복사만 수행하며 실험을 시작하지 않는다.

```text
py -3 -X utf8 audits/DRIVE_SIM_20261010/tools/verify_package.py
py -3 -X utf8 audits/DRIVE_SIM_20261010/tools/restore_stage.py 04_l1_exposure D:/audit_restore/l1_exposure
```

복원은 목적 폴더가 없을 때만 허용한다. `.gz`를 원 bytes로 복원하고 `source/` 안의 경로를 목적 폴더 루트에 배치한다. binary 원자료는 기본적으로 복사하지 않는다. 원 로컬 보관본이 있는 머신에서만 `--include-local-raw`를 붙여 hash 확인 후 복사할 수 있다. 원본 checkout에는 쓰지 않는다.

PACKAGE_PLAN.json은 게시 전 동결한 checkout HEAD/branch/dirty 상태·원격·선정 방법, ARTIFACT_INDEX.json은 게시/외부 파일 대응, PACKAGE_VERIFICATION.json은 최종 해시·보존 검사다. 최종 commit 목록과 원격 HEAD 확인 receipt는 통합 작업의 별도 로컬 디렉터리에 남긴다. 추가 실험을 수행하지 않고 단계별 커밋으로 업로드했다.
