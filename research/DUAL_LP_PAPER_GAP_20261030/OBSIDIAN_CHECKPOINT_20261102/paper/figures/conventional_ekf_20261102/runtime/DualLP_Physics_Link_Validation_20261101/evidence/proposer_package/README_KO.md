# Dual-LP 물리 관측–상태 갱신–결과 연결: 제안자 문서 패키지

2026-11-01 | **PROPOSER_ONLY / DRAFT-v1 / NOT_FROZEN / IMPLEMENTATION_NOT_RUN**

## 목적과 고정 범위
원고 v4의 **R2-B·R4-B·R5-B × B0/L0/L1/L2 12조건**, Mount 0°, anchor B, 4-State, `MB_VAR/self` 대 `BB_ORIG/self`를 유지한다. 물리 FFD 관측구조와 성능 사이의 설명을 보강할 최소 검증을 설계한다. R4-A/5-State/SUB3/sub-tap 논문으로 바꾸거나 모든 환경·모든 XY 개선을 요구하지 않는다.

이번 제출은 기존 검토 문서·표의 보존과 **검증 명세·구현자 인계·결과 활용·원고 수정 계획**이다. 실험 코드·CI workflow를 추가하거나 시뮬레이션·학습·재귀 필터를 실행하지 않았다. 원고 v4 파일도 수정하지 않았다.

## 읽는 순서
| 문서 | 용도 |
|---|---|
| [01_PROPOSER_CONTRACT_KO.md](01_PROPOSER_CONTRACT_KO.md) | 질문·권한·데이터·중단 규칙·동결 조건 |
| [02_VERIFICATION_SPEC_KO.md](02_VERIFICATION_SPEC_KO.md) | 물리 민감도, 동일-prior 2×2, 상수분산 대조의 구체적 설계 |
| [03_IMPLEMENTER_HANDOFF_KO.md](03_IMPLEMENTER_HANDOFF_KO.md) | 다른 구현자에게 전달할 작업 순서·출력·QA·프롬프트 |
| [04_RESULTS_TO_CLAIMS_KO.md](04_RESULTS_TO_CLAIMS_KO.md) | 지지/혼합/비지지/미확정 결과별 주장·표·그림 사용 규칙 |
| [05_MANUSCRIPT_REVISION_PLAN_KO.md](05_MANUSCRIPT_REVISION_PLAN_KO.md) | 현 원고 §1–4를 유지한 수정 위치·문장·추가 그림 계획 |
| [06_GOVERNANCE_AND_FREEZE_KO.md](06_GOVERNANCE_AND_FREEZE_KO.md) | 기존 역할 규정의 적용 범위와 독립 감사·승인 공백 |
| [config/PROPOSED_NUMERIC_CONFIG.json](config/PROPOSED_NUMERIC_CONFIG.json) | 결과를 보지 않고 고정할 범위·수치·분모·실행 상한 |
| [config/SOURCE_REGISTER.json](config/SOURCE_REGISTER.json) | 고정된 커밋·blob·증거·입력 해시 미확정 목록 |
| [reference_review/MANUSCRIPT_V4_PHYSICS_CLAIM_REVIEW_KO.md](reference_review/MANUSCRIPT_V4_PHYSICS_CLAIM_REVIEW_KO.md) | 이전 평가서 원문 |
| [reference_review/tables/SELECTED_12_CONDITIONS_RECHECK.csv](reference_review/tables/SELECTED_12_CONDITIONS_RECHECK.csv) | 기존 12조건 재집계 원표 |

## GitHub 배포와 전체 원본 ZIP의 구분
이 폴더에는 새 제안자 문서와 기존 평가서·핵심 표·과거 QA를 읽을 수 있는 형태로 올렸다. **이전 ZIP 이진파일 자체와 그 안의 전체 RA4 CSV·재계산 스크립트는 이 폴더에 모두 복제된 상태가 아니다.** 원본 ZIP 및 모든 구성원은 대화의 전체 다운로드 패키지에 변경 없이 보존했다. 원본 RA4 입력은 [기존 GitHub artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594/artifacts/12890904334)와 SOURCE_REGISTER의 해시로 연결한다. artifact는 만료될 수 있으므로 구현자는 대화에서 제공된 전체 ZIP도 함께 보존해야 한다.

원본 ZIP 이름: `DualLP_Manuscript_v4_Physics_Review_20261101.zip`; 47,466 bytes; SHA256 `0d261f54a586cb0c11f24f32586ae693b83092bb24168dce0d2209b924156980`. 원본 구성원 해시는 `ORIGINAL_ARCHIVE_INVENTORY.json`에 기록한다. GitHub 직접 배포 파일의 목록과 blob은 `PACKAGE_MANIFEST.json`에 기록한다.

`reference_review/RECHECK_QA.json`의 `repo_writes=0` 등은 **당시 검토 작업의 역사적 상태**이며 이번 업로드 상태가 아니다. 원문을 수정하여 과거 상태를 바꾸지 않는다. 숫자 전사 부분집합을 원 CSV 전체나 독립 검증 결과로 부르지 않는다.

## 가장 중요한 세 검증
**V1 물리 민감도–signed 잔차**, **V2 같은 prior/lookup 상태의 평균×분산 개입**, **V3 상수 추가분산 대 기존 거리 lookup**을 우선 제안한다. V0는 출처·기계적 parity의 선행 관문이다. V4의 투영 상관·누적항은 시공간 설명을 강화할 때 선택하고, V5는 기존 학습–예측–재생 연결을 확인한다.

**현재 과학 실행 상태는 모두 NOT_RUN이다.** 사용자 요청은 문서 작성·업로드 승인이지 과학 계약 동결·구현·실행 승인이나 독립 감사 서명이 아니다. 별도 구현자는 V0 입력·수치 preflight 후보를 제출하고, 제안자와 독립 감사자가 검토한 뒤 허용된 단계만 동결하여 진행한다.

## 전체 다운로드 패키지 안내
이 로컬 ZIP에는 GitHub에 올린 제안서 01–06과 모든 기존 검토 자료 9개, 원본 ZIP을 함께 포함한다. `GITHUB_PACKAGE_MANIFEST.json`은 원격 배포 파일의 blob 목록이고, `PACKAGE_MANIFEST.json`은 이 다운로드의 전체 파일 SHA256 목록이다. 두 JSON config는 의미가 같고 표시 형식이 다를 수 있다. 실행을 위한 실제 H/CONTROL/학습모형 입력 lock은 향후 V0에서 별도로 확정한다.
