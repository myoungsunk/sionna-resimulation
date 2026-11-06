# prior 근거 개입 및 별도 C-only 실행 결과

2026-11-06 KST. 기준 commit 94b49a5abe8443b8eacf4a1e3600ad3d52b10e9f + 영수증의 신규 script SHA.
PROPOSER → IMPLEMENTER → 동일 작업자 자체검산. 외부 독립 감사 아님.

**동적 근거 개입과 별도 C-only 실행 완료. provider 수용은 판단 불가, P/M E1-02 및 E2는 미실행.**
현재 점수·정책을 유지한 C-only는 오류를 한 건도 탐지하지 못했다. 이를 오탐 없는 안전한 정책으로 채택하지 않는다.

## 1. 단계별 실제 상태

| 단계 | 실제 수행 | 판정 |
|---|---|---|
| 정보 출처·독립성 | 이전 Stage1 및 실제 원본/입력 해시 연결 확인 | 완료; 독립 절대 근거 없음 |
| 동적 오류 개입 | 6,272 원본 × 277 시나리오 = 1,737,344행 저장·재집계 | 배열/진단 실행 완료; provider 성능 아님 |
| 이력 개입 | 6,272 × 11 유형 = 68,992회 기존 보호 함수 검사 | UNKNOWN의 M 사용/오염된 trusted 이력 차단 확인 |
| VALID 계약 | P/M별 범위·출처·시각·만료·prior ID·보정·복구 정의 | 구조 명세 작성; 수치 수용 기준 미정 |
| provider 수용 | 허용 용도오차/위험/최소활성화 및 독립 표본 근거 없음 | UNDETERMINED, VALID 생성 구현 안 함 |
| P/M E1-02 | 선행 provider 관문 미통과 | NOT_RUN |
| 별도 C-only | dynamic6,272 + static48 | 실행·검산 완료, 고정정책 탐지 실패 |
| E2 | 정정 실험 | NOT_RUN |

Stage2 v1은 보존했다. 최신 지시대로 static48은 prior 개입에서 제외하고 C-only에만 포함했다.
R2 개발1,958 / R4·R5 고정평가4,314를 유지하며 모두 노출 개발 데이터다. 이번 실행에서 provider 임계값을 튜닝하지 않았다.

## 2. 정보 출처·시간축과 식별 한계

| 근거 | 실제 출처와 허용 시점 | 찾을 수 있는 단서 | 구분 못 하거나 추가 근거가 필요한 것 |
|---|---|---|---|
| DR-prior 차이 | DR은 원본 x0+ds/gy/dt만 적분. prior는 이전 UWB posterior에서 예측. 현재 RF 이전 | 둘 사이의 위치/Heading 불일치와 변화 | 공통 초기 bias, 공유 센서오류, 어느 쪽이 틀렸는지의 확정 |
| 과거 innovation | main trace j<k, 최근5초; 기각 포함 | 과거 관측과 예측 불일치 | 잘못된 상태·관측이 서로 지지하는 오류; 현재 판정의 자기인증 |
| P·시간·연속성 | 저장 Pprior와 과거 시각, 누락/도착 지연 개입 | 과신 입력·오래됨·급변·구조 이상 | 작은 P/매끄러움만으로 실제 정확성 보장 |
| 별도 절대 근거 | 현재 자료에는 운용 중 독립 센서/초기화 인증 없음 | 해당 없음 | GT+잡음 초기화를 독립 센서 증거로 사용 불가 |

DR 공분산 보정 및 prior-DR 교차 공분산은 확립하지 않았다. 차이를 정규화된 신뢰확률로 만들지 않았다.
main NIS와 별도 shadow filter의 mask를 구분했다. 저장 shadow NIS가 없으므로 main NIS로 대체하지 않았다.
원본 기각53건도 과거이력 자료에 보존했다. 미래 NIS 변경 시 현재 이력 통계 불변 및 공유 bias 차이 불변 검사를 통과했다.

## 3. 동적 개입 결과와 한계

277 대조는 nominal1, 공분산축소만2, 위치/yaw/결합×부호×3수준×일정bias/jump/drift×P배율의270, 공유오류4로 구성된다.
위치 방향은 원본 prior와 등록 anchor를 이용한 radial/tangential이다. GT로 방향을 정하지 않았다.
raw prior/DR 경로와 개입별6개 진단·평가 지표를 각 case NPZ에 전 행 저장했다. evaluator 오차는 출력 평가 전용이다.

- prior와 DR에 같은 world-x ±1m 또는 yaw ±45deg를 적용하면 **DR-prior 차이는 1e-10 이내에서 그대로다.** 일치만으로 정확성 인증이 불가능한 반례다.
- 공분산만 0.1/0.01로 축소해도 중심 위치오차와 DR 차이는 변하지 않는다. 작은 P는 별도 보정 증거가 아니다.
- 무개입 Full에서 DR-prior 위치차이 중앙값은 R2 약0.403m, R4 약0.500m, R5 약0.413m이다. 같은 원본 prior의 평가용 위치오차 중앙값은 각각 약0.048m, 0.058m, 0.034m다. DR 불일치 자체를 prior 오차량으로 해석할 수 없다.
- 위치/yaw를 바꾼 뒤 원본 innovation을 그대로 둔 대조는 **저장 상태 인터페이스 개입**이다. 새 RF와 일관된 EKF replay가 아니다.
- 실제 gyro bias/센서 scale 오류를 주입한 공동 궤적·RF 재생성은 수행하지 않았다. 공유 상태 반례가 그 실험을 대체하지 않는다.

11개 이력 대조는 nominal, missing1/2/5초, delay1/2/5초, reinit, 과거rawFP±2tap, zero-innovation 합성 입력이다.
기존 UNKNOWN 보호의 이력 제거와 motion support 없음은68,992회 확인했다. 잘못된 rawFP도 실제 이전 raw tap에서 변형해 검사했다.
zero innovation은 합성 과거 입력이다. 실제 잘못된 RF가 그 상태를 지지하는 물리현상을 재현한 것은 아니다.
기존 코드는 항상 해당 지원을 보류하므로 **오류 탐지 지연·정상 복구 후 재활성화 지연·유용성은 검증되지 않았다.**

기존 stress43,904행의 narrow-reference exclusion **11,095건**은 원본 SHA 및 재집계 일치. 원래 실패를 수정/덮어쓰지 않았다.
20초 연속 블록은 기술 통계 단위일 뿐 독립 episode로 인증하지 않았다. 같은 경로/Full-LoS/개입복제는 독립 표본 수를 늘리지 않는다.

## 4. 별도 C-only 결과

VAB / TWO_PORT_UNION / 기존 policy SHA / wrong_cut=2.0 고정. 온라인 함수에는 spectrum과 noise variance만 전달했다.
전6,320 온라인 결정을 먼저 저장한 후 evaluator clean_H의 raw tap을 결합했다. 실제 select/native model/trusted history/EKF 호출은 금지했다.
실행 전 단일 동적 파형1건의 smoke 호출도 수행했다. 본 실행 분모6,320에 smoke를 중복 합산하지 않았다.

| 대상 | 전체 | 정상FP | 오류FP | 탐지TP | 오탐FP | 보류 |
|---|---:|---:|---:|---:|---:|---:|
| dynamic | 6,272 | 5,269 | 1,003 | 0 | 0 | 0 |
| static | 48 | 36 | 12 | 0 | 0 | 0 |
| 합계 | 6,320 | 5,305 | 1,015 | 0 | 0 | 0 |

Full 동적 오류 분모: R2 286 / R4 284 / R5 433. 각 Native_LoS는 대응 evaluator와 동일한 원본 대조이므로 오류0이며 독립 검증이 아니다.
1tap 오류924건, 2tap 이상91건도 모두 탐지0. 모든 row의 raw/reference가 유효하고 score가 존재했다.
점수 계산 가능률100%, 탐지율0%, 오탐률0%, 보류율0%. 계산 가능률은 provider VALID 활성화율과 다른 지표다.
dynamic score 범위0.0173225694–1.3047751473, static0.4222838017–0.8399783421로 모두 임계값2.0 미만이다.
현재 C 점수는 raw 후보의 0.7×[-log(support)]이며 확률로 보정된 값이 아니다. threshold가 이번 점수 범위 밖인 사실을 확인했을 뿐 새로운 threshold를 채택하지 않았다.
selected_tap=raw_tap 전수 일치. 오탐률을 오정정률로 보고하지 않는다. 정정은 실행하지 않았다.

## 5. provider 관문과 남은 작업

VALID 의미는 '특정 P 또는 M 사용 범위의 근거 충족'이며 포괄적 위치정확도 보증이 아니다. 세 상태와 P/M별 allowed 필드를 구조 계약에 정의했다.
현 자료로 VALID를 만들지 않았다. 기존 guard의 활성화0%는 실용성 통과가 아니며 위험한VALID 비율은 분모0으로 N/A다.
보정된 provider 지원구간이 없으므로 해당 포함률/폭도 N/A다. 기존 P를 보정완료 구간으로 둔갑시키지 않았다.

미해결: 용도별 오차한계·허용위험·최소활성화, 독립 초기 근거 또는 제한된 scope, 교차 공분산/보정 근거,
기존 muMB/muBASE/R donor 노출 감사, 실제 도착시각 자료, 시간 이력으로부터의 검증된 신뢰/복구 규칙.
사용자에게 수치 요구사항을 요청했으며, 이번 실행에서 임의 숫자를 수용 기준으로 설정하지 않았다.
향후 숫자를 정해도 이미 공개된 개입 결과에 대해 '결과 전 동결'했다고 주장할 수 없다. 새 계약/검증 버전으로 진행해야 한다.
따라서 `HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING` 유지. P/M E1-02는 선행 관문 미충족으로 실행하지 않았다.
C-only의 이번 탐지 실패는 별도 개발 과제로 남기며, 결과에 맞춰 기존 정책을 즉시 변경하지 않았다.

## 6. 실행·검산·보존

- 로컬 Windows, CPU affinity3개/BLAS1, 본 실행 약158.8초, 관측 peak working set 약163.3MB.
- 기존 prior integrity 단위검사12개 통과; 직선/회전 운동 특수사례 및 원본posterior→prior 재현1e-10 통과.
- 별도 저장출력 checker가 NPZ1,737,344행의 집계·공유반례, C confusion6320행, history68992행, 원본/코드/계약SHA를 재검산했다. 동일 작업자 자체검사다.
- managed process exit0/natural 확인 후 finish, 소유권 해제 및 process/supervisor/job 종료 확인. 백그라운드 잔여 작업 없음.
- 기존 production 코드·입력·실패·VAB 주안·E1-02 승인파일 변경 없음. 새3개 script와 새 research package만 추가했다.
- Git commit/push는 이번 실행에서 하지 않았다. 로컬 산출물 상태다.

산출물: CONTRACT_KO.md, C_ONLY_CONTRACT_KO.md, PROVIDER_ACTIVATION_CONTRACT_KO.md,
RUN_001/RUN_RECEIPT.json, EVIDENCE_CHECK.json, EVIDENCE_SUMMARY.json, *_DIAGNOSTICS.npz,
C_ONLY_ONLINE.jsonl.gz, C_ONLY_LABELLED.jsonl.gz, C_ONLY_SUMMARY.json,
HISTORY_001/HISTORY_CHECKS.csv.gz, HISTORY_001/CHECK.json, CHECK_001.json.
