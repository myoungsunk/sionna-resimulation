# prior 신뢰 분리·P/M/이력 보호 전체 구성요소 재검증

판정: **PASS_COMPONENT_GUARDS_ONLY**. **E1-02 HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING**, E2 미실행.
기준 b8cc7ee731d61ac747cc99d7203ddcce28de962c. 계약은 구현 전 597c74f에서 동결했다.
역할 PROPOSER → IMPLEMENTER → 자체검사이며 독립 감사가 아니다.

## 변경 및 주장 범위
- 수치 Support와 prior integrity를 분리했다. 구조 정상은 UNKNOWN, 구조 이상은 INVALID다.
- 검증된 신뢰 제공자가 없으므로 VALID 승격은 이 버전에서 금지한다. 작은 covariance/좁은 구간/불리언으로 우회할 수 없다.
- C의 원래 RF 점수를 유지한다. UNKNOWN/INVALID의 P/M/PM은 effective_mode=HOLD, active wrong_score=None이다.
- prior/motion의 원래 비용과 residual은 diagnostic_only로 분리해 저장하며 평가 출력에서도 유지한다.
- 기존 trusted state는 사용 전에 초기화하고, untrusted prior에서 bootstrap/refresh/offset 재사용을 차단한다.
- 기존 후보 규칙/bridge/선택기 eligibility/수치 mapping 및 VAB 주안은 그대로다. legacy 일반 선택기는 기존 동작을 보존한다.
- 코드상 오류선언 경로의 차단을 검증한 것이며 잘못된 prior를 식별하는 성능이나 FP 정정 안전성을 입증한 것이 아니다.

## 실행·검산 결과
| 검사 | 결과 |
|---|---:|
| 전체 파형 | dynamic 6,272 + static 48 = 6,320 |
| 4 arms ×2 candidate modes | 50,560행 후보 및 eligible 집합 exact 재현 |
| pool hash 원본 일치 | 0 / 50,560 |
| dynamic nominal+7stress | 50,176 packet-scenario |
| UNKNOWN/INVALID × C/P/M/PM | 401,408 구성요소 검사 |
| P/M/PM HOLD | 301,056 state-mode 검사 |
| untrusted active score·history 보호 위반 | 0 / 0 |
| 후보 집합 변경 | 0 |
| static | 48개 C-only, prior/history 생성 없음 |
| 최종 합성검사 | 90개 PASS |
| legacy Decision 재현 | 1,000개 exact |
| 기존 nominal mapping 재집계 | G0~G5 일치, 6,272/6,272 참조 포함 |
| 기존 좁은 구간 참조 배제 | 11,095 / 43,904, 기록 그대로 보존 |

401,408은 독립 RF 표본수가 아니다. 같은 원본과 저장 mapping 구간에 상태/모드를 바꿔 구성요소를 검사했다.
M에는 guard를 우회하려는 오염된 motion support도 주입했다. 실제 시간 이력 선택 성능 결과가 아니다.
전체 검사는 prepare_detection/prepare_candidate_set/history guard를 직접 호출했다.
실제 detect/select/detection_loop/E1-02/E2/EKF 호출은 sentinel로 금지했다. 합성시험의 호출과 구별한다.
SourceFFD 수치 mapping은 변경하지 않았으므로 해시 검증한 기존 구간을 재사용하고 CSV를 재검산했다. 새 mapping 모델 질의는 0회다.

## pool hash 차이 — 바이트 단위 재현 미확인
후보 tap/eligible 집합은 전수 일치하지만 pool hash는 0/50,560 일치다.
사후 단일 파형(dynamic:R2:0:Full, VAB/TWO_PORT_UNION)에서 비교한 127개 차이는 모두 숫자 하위자리 차이였고
최대 절대차는 약 5e-16이었다. 이 표본에서 key/길이/비수치 차이는 없었다.
Windows 재계산과 과거 Linux 실행 간 부동소수 차이와 일치하는 관측이지만, 전체 scalar 필드의 원인을 전수 규명한 것은 아니다.
전수 float 동일성은 NOT_TESTED, 바이트 단위 동일성은 성립하지 않는다. 동결 G1은 후보/eligible 위치의 exact 재현이며
이를 해시 일치나 전수 수치 동일성으로 확대하지 않는다. FLOAT_HASH_DIAGNOSTIC.json 및 diagnose_float_hash.py에 표본 근거를 남겼다.

## 중요한 제한
**P/M/PM usable coverage는 0%다.** 현재 실제 입력에서 VALID를 뒷받침하는 검증된 제공자가 없기 때문이다.
이 상태를 모든 오검출을 해결한 PASS나 사용 가능한 P/M 정책이라고 부르지 않는다.
11,095개 reference 배제 구간은 그대로이며, 그 불확실한 증거가 오류선언·trusted history로 전파되는 경로만 차단했다.
동적 E1-02 진입 전에는 신뢰 근거/provider 및 그 평가 기준을 별도로 마련하거나 C-only/diagnostic-only의 범위를 별도 정해야 한다.
현재 manifest와 approval은 실행을 허용하지 않으며 E2 이후 권한도 부여하지 않는다.

## 재현·출처
- 전체 파형 구성요소 실행 commit: 82301adbb5cecde16f9157ab1aa48a45de708317.
- 최종 평가 출력 전달·합성검사 commit: 71abc6abfb3a19f2e1b5d7a57d91d95fbf709416. 보호 핵심 함수는 전체 실행과 동일 SHA이며 평가 출력 전달/부정 승인 검사를 추가했다.
- 로컬 실행: Windows, CPU affinity [0, 1, 2], 계산 라이브러리 thread 1.
- 전체 실행 소요: 1260.8초. 표본 시점 최대 RSS: 197.6MiB (OS 절대 peak 아님).
- RUN_001/RUN_RECEIPT.json 및 ARTIFACT_HASHES.json: 명령·환경·입출력 해시·시각·실행 SHA.
- RUN_001/CANDIDATE_RECHECK.csv.gz: 50,560행 후보 전수 비교.
- RUN_001/PROTECTION_RECHECK.csv.gz: 401,408행 상태/모드/점수/HOLD/이력 보호 검사.
- CHECK_001/GATE.json: 별도 CSV-only checker, 동일 작업자 자체검사.
- FINAL_TESTS_001: 90개 합성검사 및 legacy1,000 재현 영수증.
- PREPARATION_001: 총6,320 입력·최종 코드 lock, integrity receipt, 부정 실행 승인과 차단 확인.
- ../PRIOR_FAILURE_ANALYSIS_20261105: 기존 11,095건 원인 분석 및 전체43,904행 진단 자료.

기존 E1 실패·VAB 주안·R1 mapping 실패/제한 기록은 변경하지 않았다. 원본 파일 이동·삭제 없음.
다음 권고 작업은 VALID 신뢰 근거/provider 계약 검토이며 E1-02/E2 실행이 아니다.
