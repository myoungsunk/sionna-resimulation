# DLP-R1B-CH4-001 — R1·Anchor B HOLD 전달 패키지

**최종 판정: `HOLD_RF_PARITY`. 전체 917개 RF 및 실제 4상태 EKF 재귀는 실행하지 않았다.**

실제 실행은 8개 고정 canary pose의 Native LoS/Full 쌍이다. 독립 재계산한 복소 상대오차 RMS `1.0051515145524099e-4`가 동결 기준 `1e-4`를 초과했다. 현재 데이터는 실패 원인 검토와 재현을 위한 근거이며 제IV장의 성능 검증 완료 자료가 아니다.

## 먼저 읽을 파일

1. [최종 결과 및 논문 사용 범위](10_FINAL_RESULT_AND_MANUSCRIPT_USE_KO.md)
2. [최종 기계 판정](08_QA_PARITY_AND_LIMITATIONS.json)
3. [원본 V2 실행 계약](00_REQUEST_CONTRACT_FROZEN_V2.json)
4. [독립 원시 감사](audits/P0_CANARY_RAW_AUDIT_FINAL.json) 및 [지연 차이 진단](audits/P0_DELAY_DIAGNOSTIC_INDEPENDENT.json)
5. [독립 감사 요청과 완료 상태](09_INDEPENDENT_AUDIT_REQUEST_KO.md)

## 구성

| 경로 | 내용 |
|---|---|
| `REQUEST_RECEIVED_KO.md` | 원래 요청서 내용 |
| `00_…V2.json`, `02_…V2.json` | 동결 조건·입력 및 코드 해시 |
| `01_…FINAL_KO.md` | P0 최종 계보·환경·타당성 |
| `04_…`–`07_…` | P1–P4 실제 수행 상태와 남은 조건 |
| `data/pose_timeline.csv` | 원본 917개 궤적의 동일 bytes |
| `runs/P0_CANARY_V2/` | 8개 원시 NPZ/JSON, 실제 환경, mesh, 원래 QA, 실행 로그 |
| `audits/` | 실행 전·후 별도 계산 감사와 소스 코드, 보존한 정정 이력 |
| `figures/` | 원본 궤적 기하 그림 PNG/PDF와 생성 근거 |
| `runtime/` | 실제 canary 수집기, 미실행 4상태 replay 및 생산 수집기 |
| `P0_COST_MEASUREMENT.json` | 실측 비용·의미 정정·단순 외삽 |
| `SHA256SUMS.txt` | 이 폴더의 모든 전달 파일 SHA-256; 자기 자신과 cache 제외 |

원래 `01_P0_PROVENANCE_AND_FEASIBILITY_KO.md`와 `P0_POSE_GEOMETRY.json`은 실행 전 상태를 기록한다. Native QA의 `independent_audit=PENDING`도 발행 당시 값이다. 이 파일을 사후 수정하지 않았으므로 최종 상태는 `08_QA_PARITY_AND_LIMITATIONS.json`과 후속 감사에서 확인한다. V1 계약·감사 영수증은 이력을 위해 남겨 둔 것이며 실제 Native RF는 V2 계약으로만 실행했다.

## Git 계보

| 용도 | SHA |
|---|---|
| 기반 소스 | `e365b2f79eb86a3fd53d0d350f8e2d9364f285fe` |
| 사용자 참조 과거 기록 | `9e9133ecb46f96d88ee14652d42f43525fdd1b29` |
| 초기 V1 보존 | `15f593e319b1bf4a2cc9838d6ec9c8431e98a6c4` |
| **실제 Native 실행** | **`24d657af7773d1c0347e843ece6b49e9c2d55ac2`** |

외부 전달 ZIP의 `DELIVERY_RECEIPT.json`은 실행 후 보고서 보존 commit과 bundle 해시를 기록한다. ZIP의 Git bundle은 위 기반 commit을 prerequisite로 하는 추가 local commit 묶음이다. 원격 GitHub branch/PR는 게시하지 않았다.

## 원래 입력 확보

기반 저장소는 [myoungsunk/sionna-resimulation](https://github.com/myoungsunk/sionna-resimulation)이다. 실제 source·model·filter core는 `02_INPUT_HASH_MANIFEST_V2.json`에 고정돼 있다. 전달 ZIP에 기존 저장소 전체나 Python 가상환경을 복제하지 않는다. Git bundle을 사용할 경우 기반 commit을 가진 checkout에서 bundle을 검증·가져와 정확한 local branch 계보를 복원할 수 있다.

두 원래 FFD bank는 약 495 MB이며 ZIP에 포함하지 않았다. [GitHub Actions 원래 run](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38875080492)의 artifact `12034154094`에서 복구한 입력이다. 입력 위치는 저장소 바로 옆 `ffd-banks/`이고, 각 파일의 크기·해시는 P0 최종 보고서와 V2 계약에 있다. 원래 archive와 bank 해시가 맞아야 감사 재현을 시작할 수 있다. 원래 artifact의 향후 보존·다운로드 가능성을 보증하지 않으므로 감사자는 확보한 원본을 같은 해시로 보존해야 한다.

## 원시 감사 재현 — 새 RF 없이 실행

실제 사용 버전은 `runs/P0_CANARY_V2/ENVIRONMENT.json`과 V2 계약에 있다. 본 감사는 numpy 1.26.4, scipy 1.14.1 및 기반 저장소의 SourceFFD 코드·원래 bank를 사용한다. 최초 실행의 Python은 3.12.14다. 수집기 코드를 import하거나 Native RT를 다시 호출하지 않는다.

저장소 루트에서, 원래 bank와 입력을 해시대로 준비한 후 **새 출력 경로**를 지정한다.

```bash
python research/DLP_R1B_CH4_20261103/audits/audit_native_raw.py \
  --run research/DLP_R1B_CH4_20261103/runs/P0_CANARY_V2 \
  --out /absolute/path/to/new-review/P0_CANARY_RAW_AUDIT_REPRODUCED.json
```

예상 과학 판정은 `HOLD_INDEPENDENT_RAW_AUDIT`이고 원시 accounting은 PASS다. 이 재현은 실패를 PASS로 바꾸기 위한 실행이 아니다. 원래 감사 영수증을 출력 경로로 지정하지 않는다. 출력의 `checks_performed`, `failed_checks`, 원시 해시와 metric을 함께 비교한다.

전달 폴더 자체의 무결성은 해당 폴더에서 확인한다.

```bash
sha256sum -c SHA256SUMS.txt
```

`audit_delay_diagnostic.py`는 원래 영수증 생성 경로가 코드에 고정돼 있으므로 그대로 실행하면 기록을 덮어쓸 수 있다. 전달본에서는 코드와 기존 JSON을 읽어 검토하고, 재실행이 필요하면 별도 작업 복사본과 새 출력 경로를 먼저 준비한다.

## 생산·필터 실행에 관한 상태

현재 HOLD 아래에서는 생산 RF·P2·P3·P4를 실행하지 않는다. `runtime/r1b_acquire.py`의 소스 검토는 실제 생산 검증이 아니며, anchor exact-equality 문제와 병렬 전역 중단 경계가 남아 있다. [추가 검토서](audits/P1_PRODUCTION_DRIVER_REVIEW_ADDENDUM_KO.md)를 함께 읽어야 한다. 이 코드를 수정하더라도 이번 canary의 복소 RMS HOLD가 자동 해소되지 않는다.

재개에는 지연 정밀도 경로 검토, 필요 시 별도의 명시적 구현·계약 개정, 새 해시와 사전 검토, 신규 canary의 모든 게이트, 비용·생산 계획 심사가 필요하다. 지연 정합 후 잔차를 원래 복소 채널 지표로 대체하거나 표본·가중치·허용오차를 결과에 맞춰 바꾸지 않는다.

GitHub 게시 승인과 과학적 실행 재개는 서로 다르다. 자동 승인 검토가 외부 게시 권한 미확인을 이유로 push를 차단해 원격 게시를 하지 않았으며, 다른 도구로 우회하지 않았다. 이 전달본은 차단된 외부 게시를 요구하지 않고도 검토할 수 있도록 구성했다.
