# E1-02 실행 전 준비 결과

**준비 코드·동적 입력·모델·환경 사전 검사 PASS. E1-02는 HOLD_NOT_READY, E2–E5는 SCIENCE_NOT_RUN.**
후보 개정·도달성은 사용자가 제시한 제한된 검토 범위에서 TECHNICAL_ACCEPT_WITH_SCOPE로 기록했다.
실제 RF 검출/선택, dynamic mapping, EKF replay는 이번에 실행하지 않았다.

## 확인 결과

| 항목 | 실제 결과 | 근거 |
|---|---|---|
| VAB 검출 전용 경로 | 공유 후보 집합 사용, selected_tap=raw_tap 유지, 일반 select/probe 호출 없음 | detection.py, 합성 검사 |
| 원본 FP 이력 | legacy_support 기반 raw-only bootstrap을 별도 recipe로 구현 | RAW_ONLY_LEGACY_SUPPORT_GATE_R1 |
| 실행 차단 | mapping boolean만으로 불가, VAB profile의 E2 진입 불가, execute_science=false 거부 | 13개 신규 합성 검사 |
| 전체 합성 검사 | 신규 13 + bridge 18 + reach 14 + legacy 24 = **69/69 PASS** | FINAL_CHECK_002/RESULT.json 및 로그 |
| 기존 결정 호환성 | **1,000/1,000 정확 일치** | 고정 486f0b6의 선택기와 비교 |
| 원본 입력 | **35/35 해시 일치** | INPUTS/OFFLINE_PREFLIGHT.json |
| canonical 동적 입력 | **6개 case, 6,272 packet** 변환·스키마·시간축·prior/Pprior exact 대조 PASS | INPUTS/*/EXPORT_RECEIPT.json |
| 최종 입력 잠금 | **73개 파일 SHA 검증** | FINAL_CHECK_002/MANIFEST_PREP_ONLY.json |
| 원본 FFD bank | 두 payload 각 약 248MB, 고정 SHA 일치 | PREPARATION_RECEIPT.json |
| 모델 연결 | SourceFFD 로딩 및 OriginalAdapter(VAB) 생성 PASS, native/evidence/replay 호출 0 | ADAPTER_LOAD.json |
| 목표 환경 | Snowball KMS, Python 3.12.14 / NumPy 2.3.5 | PREPARATION_RECEIPT.json |
| CPU 제한 | affinity **[0,1,2]**, Docker quota 3, BLAS/OMP/MKL/NUMEXPR 각 1 | 실행 명령·RESULT.json |

검사 코드 기준 커밋은 `69bda87b84c72df120ac3ecffe494d33348a7081`이다.
최종 코드 잠금 SHA는 `ee6209237ef25be4e22bd0551b15c981c0a082db6facee2311d53dd8e6c3ff25`.
같은 작업자의 자체검사이며 독립 감사가 아니다. 원시 50,560행을 다시 실행하거나
외부 독립 재계산했다고 주장하지 않는다. 기존 E1 실패·R1·bridge·reach 결과는 수정하지 않았다.

## 입력의 범위와 보존

동적 case는 R2/R4/R5 × B0 × Full/Native_LoS이며 기존 E0 A2 controls/replay를 재사용했다.
원본 `truth`는 N×3이다. gyro bias를 추정해 네 번째 열을 만들지 않고, 검출 전용 evaluator만
N×3을 받도록 분리했다. 일반 정정/trajectory evaluator의 N×4 계약은 유지한다.
변환된 prior/Pprior는 보관된 측정 전 배열과 정확히 같으며 replay를 새로 수행하지 않았다.

기존 static 48개 파형은 원본 입력 잠금에 포함되어 보존되지만, 현재 동적 stage case 6개에는
포함되지 않는다. 6,320개 전체를 E1-02에서 평가하려면 static C-only 입력 경로를 별도로 완성하고
case 목록을 갱신해야 한다. static 방향 조건을 시간열이나 가짜 prior로 변환하지 않았다.

실제 canonical online/evaluator payload와 bank는 다음 스노우볼 폴더에 유지했다.
`/home/KMS/codex_runs/FP_SC_E102_PREP_20261105/repo/`
canonical 입력은 그 아래 본 보고서 폴더의 `INPUTS/<case>/`에 있다.
GitHub에는 코드, export spec, SHA manifest, 검사 로그/영수증과 계획을 게시한다.
중복 canonical 대용량 NPZ와 bank payload 자체를 이번 결과 커밋에 다시 넣지는 않았다.
기존 원본으로 재생성하는 스크립트는 `scripts/prepare_fp_sc_e102.py`이며 기존 출력 덮어쓰기를 거부한다.

## 실행 전 남은 관문

1. `DYNAMIC_MAPPING_PLAN_KO.md`의 probe domain·coverage/폭 수용 기준을 결과 전에 동결한다.
   별도로 허가된 dynamic mapping 검사와 검토 receipt가 필요하다. 현재 NOT_RUN이다.
2. E1-02의 대상이 동적 6,272개인지 static 포함 6,320개인지 실행 계약에 확정한다.
   전체 대상이면 static C-only 경로의 준비·검사를 마친다.
3. 원본 FAIL/HOLD와 개정 기술 수용을 구분한 선행 결과 검토 및 진행 판단을 남긴다.
   추가 receipt는 기술적 수용만 기록하며 `scientific_gate=HOLD_RESULT_REVIEW`다.
4. 위 근거를 최종 manifest/code/input 해시에 결속하고 명시적 승인 후 **E1-02만** 실행한다.
   현재 `NO_EXECUTION_APPROVAL.json`은 execute_science=false, stages=[]다.

후속 순서는 `PROGRESSION_DECISION_KO.md`를 따른다. E2의 정상 FP 보호·오정정/보류율,
E3의 F01/F11 및 R_rs, E4의 자기강화/과신 prior, E5의 5Hz 운용 검증은 각각 별도 관문이다.
이번 준비 결과로 wrongness/confidence의 확률 보정, FP 정정 안전성, EKF 개선을 주장할 수 없다.

## 준비 중 실패와 수정

- 로컬 partial-clone/LFS 경로가 진행하지 않아 중단하고, 스노우볼에서 고정 커밋의 payload를
  직접 받아 SHA를 확인했다. 기존 원본 파일이나 실패 결과를 대체하지 않았다.
- 최초 export 보조 작업은 container 경로 설정 오류로 입력 변환 전에 중단됐다.
  경로를 수정한 다음 별도 작업에서 6개 입력 변환이 완료됐다.
- `FINAL_CHECK`의 신규 합성 검사 2개는 빈 잠금 fixture 때문에 목표 관문에 도달하기 전에 실패했다.
  유효한 synthetic 파일 잠금을 넣어 검사 의도를 바로잡았고, 원래 실패 로그를 보존했다.
  최종 결과는 `FINAL_CHECK_002`다. 실행기 차단 규칙을 완화해서 통과시키지 않았다.
- `INPUTS/MANIFEST_PREP_ONLY.json`은 초기 변환 당시 잠금이다. 현재 준비 기준은
  `FINAL_CHECK_002/MANIFEST_PREP_ONLY.json`이며 두 문서 모두 실행 승인이 아니다.
