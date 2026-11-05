# FP-SC-001 제안자 패키지

**목적:** 정상 FP를 보존하며 오선택만 선별 교정하고, 그 효과가 편파비·ranging·최종 EKF 성능까지 이어지는지 단계별로 검증한다.

**상태:** v0.1 PROPOSER DRAFT. 구현·실행·독립감사·승인 토큰 없음. 기존 PR #37의 탐색 코드를 실행 승인한 문서가 아니다.

## 읽는 순서

| 파일 | 용도 |
|---|---|
| [01_EXECUTION_PLAN_KO.md](01_EXECUTION_PLAN_KO.md) | H0–H7 가설, E0–E5 실험, 가정·정의·계약·성과·중단 기준 |
| [02_EXPERIMENT_MATRIX.csv](02_EXPERIMENT_MATRIX.csv) | 21개 실험 항목과 가설/대조/가정/지표/산출물 추적표 |
| [03_AUDIT_AND_CLAIM_REVIEW_KO.md](03_AUDIT_AND_CLAIM_REVIEW_KO.md) | 구현 전·코드·결과·주장 독립 감사 요청과 22개 최소 기술 검사항목 |
| [04_RUN_CONTRACT_DRAFT.json](04_RUN_CONTRACT_DRAFT.json) | 기계 판독 계약 초안. 모든 GO=false, 필수 미확정 필드가 있으면 실행 차단 |
| [05_SOURCE_REGISTRY.json](05_SOURCE_REGISTRY.json) | 실제 열람한 GitHub 문서·코드의 정확 commit, 링크, blob 및 읽은 범위 |
| [06_AUDIT_RESULT_TEMPLATE.json](06_AUDIT_RESULT_TEMPLATE.json) | 향후 감사자가 채울 결과서. 현재 감사 결과가 아님 |
| [07_PROPOSER_SELF_CHECK.json](07_PROPOSER_SELF_CHECK.json) | 문서 연결·ID·계약·계수의 작성자 자체검사. 독립 과학감사 아님 |
| [08_IMPLEMENTER_HANDOFF_KO.md](08_IMPLEMENTER_HANDOFF_KO.md) | 처음 구현자에게 전달할 범위 및 E0 착수 조건 |
| [MANIFEST_SHA256.json](MANIFEST_SHA256.json) | 이 패키지 파일의 무결성 목록(목록 파일 자신은 제외) |

## 중요한 설계 결정

**오선택 탐지와 대체 후보 선택은 서로 다른 가설이다.** 4cm는 nominal tick의 기하 이동 한계이며 detector offset·quantization·prior 오류를 포함한 경계가 아니다. 후보간 거리/편파 차이는 confidence의 입력일 뿐 개선의 정답이 아니다.

**ranging 보호를 직접 시험한다.** F00/F10/F01/F11로 거리만·편파만·둘 다 변경하는 효과를 구분한다. 관측 추출기 변경 후 μ/R·Rrs 정합과 단일 정보계상을 확인한 뒤 전체 폐루프로 간다.

**경로 일반화와 같은 RF의 새 seed를 구분한다.** 주 계획은 기존 세 경로에서 공통 selector의 조건부 성능 검증이다. 전체 pipeline route-heldout 또는 새 물리환경은 별도 계약이다.

**기술 PASS와 과학적 주장 지지는 다르다.** 정상 보호, 교정 coverage, 편파/ranging, Heading/XY, 공분산 및 5Hz 지연을 독립 판정한다. 한 지표만 좋아지면 전체 채택을 승인하지 않는다.

GitHub 문서 초안으로 옮길 때 권장 위치: `research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/PROPOSER_20261105/`.
기존 코드와 기존 실험 결과를 덮어쓰지 않는다. 이 패키지 작성 과정에서는 원격 저장소를 변경하지 않았다.
