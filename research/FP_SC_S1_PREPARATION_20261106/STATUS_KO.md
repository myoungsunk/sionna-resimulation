# S1 준비 상태

판정: PASS_PREFLIGHT_NO_SCIENCE / AWAIT_EXPLICIT_CASE_APPROVAL.

최종 준비본은 FINAL_002의 6개 S1 manifest와 PREFLIGHT_RECEIPT.json이다. 루트의 첫 manifest/영수증은 파일 검사 범위가 더 좁았던 준비 기록이므로 실행에 사용하지 않는다. FINAL_002는 SourceFFD 하위 모듈을 추가 materialize하고 공통 코드 잠금에 포함했다. 기존 파일·알고리즘은 수정하지 않았다.

| 대상 | Full | Native_LoS | 합계 |
|---|---:|---:|---:|
| R2 | 979 | 979 | 1,958 |
| R4 | 742 | 742 | 1,484 |
| R5 | 1,415 | 1,415 | 2,830 |
| 전체 | 3,136 | 3,136 | 6,272 |

6개 case 모두 기존 payload SHA 일치, online 구조·유한값·시간·pose 검증 및 evaluator 정확 연결 통과. 6개 CLI preflight exit=0. 각 4모드 예상 총 행은 25,088이며 아직 생성하지 않았다. 두 FFD bank는 원래 BANKS SHA와 일치한다. SourceFFD 및 핵심 의존 모듈 import 성공; 모델 인스턴스 생성·native 계산·후보 생성·선택·EKF는 실행하지 않았다. bank 전체 수치 스키마 검사는 모델 로더 실행 단계에 남으며 이번에는 원래 파일의 byte identity를 검증했다.

새 승인 파일은 없다. S1 실행에는 사용할 case, 최종 manifest hash, 공통 code lock을 묶은 별도 승인이 필요하다. S2/S3는 아직 준비·승인된 실행이 아니다. S3 trace 존재 여부는 receipt에 기록했지만 그 수치적 정합을 이번에 검증하지 않았다. static 48개는 동적 S1에서 제외하고 기존 C-only 기록을 유지한다.

초기 missing source 중단은 PREPARATION_ATTEMPT_01.json에 보존했다. 원본 Git blob의 동결 해시를 확인하여 복원했다. 자기검사이며 외부 독립 감사가 아니다. 과학 성능·정책 안전성 PASS를 의미하지 않는다. 환경이나 파일이 바뀌면 해당 실행 환경에서 preflight를 다시 수행해야 한다.

기존 실패 기록·VAB 주안·모든 정책 임계값 유지. S1/S2/S3 과학 실험, E1-02, E2 실행 0회.
