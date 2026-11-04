# MBVAR-PRR-001 — S2/S3 종결 이후 제안자 수정 판정 및 검증 계획

2026-11-04. 근거 commit cc21c58bcbc0dd11320ee1b11b600bbd1e3da49e.
상태: PROPOSER DRAFT / 미동결 / 미구현 / 미실행. S1–S3의 감사·코드·결과는 **수정하지 않는다**.
기존 결론: 기술감사 ACCEPT / C4·C5 PARTIAL / C6 NOT_SUPPORTED / C7 NOT_TESTED / 전체 채택 NO-GO / 실시간 HOLD.

## 1. 판정 근거

| Full primary (t>=30s), 잠금 seed10–29 | S1 예방 B/A Heading ratio | S2 P 복구 D_P/A | S3 CP 복구 C_CP/A | S3 결합 D_CP/A |
|---|---:|---:|---:|---:|
| R4-B B0 | 0.921514 | 0.913822 | 0.910990 | **0.821953** |
| R4-B L2 | 0.905549 | 0.895775 | 0.894417 | **0.782719** |
| R5-B B0 | **1.062248** | 1.083735 | 1.008012 | **1.073474** |
| R5-B L2 | **1.050435** | 1.084502 | 1.012198 | **1.071620** |

R4 S3 D_CP 온라인 emitted Heading 개선은 확인됐으나 Heading95 coverage B0 0.592905, L2 0.575169로 명목 95%에 여전히 미달. R5 Full은 예방-only B 자체가 1.05 보호한도 위반이다. **복구 발동만 막으면 R5 보호가 자동 해결된다는 주장은 거짓.**

R5 S2 Full P-injection 164건 중 132건(80.5%)은 적용 *직전* 이미 정확했다. S3 EVAL 259 event 중 137건은 이미 정확, 이 중 R5 Full은 132/162건. 이미 정확 정의: Heading 1° 이하 *동시* XY 0.10m 이하, offline GT로만 판정. 이벤트는 같은 RF·경로·seed에서 반복되므로 독립 환경 표본이 아님.

S2 C4 국소복구 성공은 두 R4 Full 그룹에 한정. R5의 전체 악화가 132개 필요 없는 이벤트 때문이라고 인과 확정하지 않는다.

**S3 계산 지연**: 5Hz Full C_CP/D_CP 실측 p99 389–1265ms, 예산 200ms FAIL. S3 seed10 R4-B B0 Full의 의심 첫 시작 0.8s, 복구 60.0s, 재처리 297 packets; R5 B0 Full은 88.8→133.8s (226 packets), 195.6→231.6s (181 packets). Seed0 DEV에서 10초/30초 이력은 R4 Full에서 identity(no retrospective policy)와 동일하였고, 60초 대비 D_CP의 primary Heading RMSE가 B0 0.16115° / L2 0.17283° 커짐. 따라서 **history를 임의 10/30초로 축소하지 않는다.**

## 2. 수정 우선순위

**N0 — 기존 이력의 독립 분석:** 복구 필요성과 실제 복구 이득을 발동 이전 정보로 구분 가능한지 확인.
**N1 — 온라인 선택 규칙:** 편파 관측 할인 여부와 checkpoint 복구 실행 여부를 각각 구분하는 동일 공통 정책 평가.
**N2 — 계산 등가성/실시간성:** 과거 60초의 정보를 삭제하지 않고 replay burst를 incremental shadow EKF로 분산할 수 있는지 검증.

신규 경로 학습/신규 RF/새 앵커/마운트 교체/FGO 전환은 범위 밖. 구현 전 독립 사전감사 필요.

## 3. N0: 읽기 전용 사건 분석 — 구현보다 먼저 수행

### 구분해야 할 사후 라벨

- L_accuracy: 해당 event의 *처치 이전 prior*가 Heading<=1°, XY<=0.1m를 동시에 만족하는가. 정답 GT는 offline evaluator만 사용.
- L_benefit: **동일한 손상 시작 상태와 이후 동일 데이터**에서 개입 ON과 OFF를 비교한 10초·20초 Heading/XY 오류 적분, 회복시간 및 tail 개선 여부. L_accuracy와 다름.
- 자연 재귀 A/B/C/D 결과를 같은 event의 반사실적 개입효과로 즉시 치환할 수 없음. 선행 개입·다른 prior가 혼합되므로 L_benefit은 matched snapshot replay가 검증된 경우에만 계산하고 아니면 NA.

### 온라인에서 이미 볼 수 있는 특징만

현재 시점 이전의 의심 episode 길이·위험 관측 횟수·부호, 이전 2~5초 d0 및 다중 offset Delta-s, 예측 h/H/편파 민감도, 사전 공분산 및 VAR 유효분산, 운동방향/속도/앵커 상대거리, 짧은 창의 모형 잔차·관측정보량·지향각 다양성·geometry guard. 별도 보조 특징으로 원본 MB_VAR(W0)와 예방 B의 추정 차이 검토 가능하나 두 필터가 같은 RF를 사용하므로 독립 상태 측정으로 취급하지 않는다.

**금지:** route ID, seed ID, GT 오차, Native-LoS oracle, 발동 후 미래 suffix, 이후 회복시간을 온라인 결정 특징으로 쓰는 것. 작은 d0/NIS도 잘못된 prior에서 나타날 수 있으므로 정확성 증명으로 사용 금지.

비교: 기존 latch rule / geometry-only / observation-consistency / 두 필터 간 disagreement / 조합. 처음부터 새 학습모델을 의무화하지 않는다. R4 필수 복구를 놓치는 경우와 R5 불필요 개입을 허용하는 경우를 모두 공개한다. 반대 사례를 분리할 신호가 없으면 **NO_IDENTIFIABLE_SAFE_TRIGGER** 판정 후 복잡한 guard 구현을 보류.

**필수 산출물**: 사건별 BEFORE_FEATURES, 사후 GT LABELS, 짝지은 ON/OFF 결과가 있을 때만 BENEFIT, route/bias/channel/seed별 분모 포함 CROSSTAB, 누출 감사, 경로 제외/seed 묶음 분석. S1–S3 잠금 seed10–29는 이미 공개된 자료이므로 신규 규칙을 여기서 고른다면 확인용 holdout으로 다시 사용할 수 없음.

## 4. N1: 관측 할인과 복구 발동을 각각 분리하는 새 계약

현재 S1 예방 B가 R5 보호 실패, S3 CP-only C_CP는 R5의 약한 악화, S3 D_CP는 둘이 결합되어 R5 악화. 따라서 두 다른 수정이 필요할 수 있다.

### 1차: 복구 발동 guard만 시험

| Arm | S1 prevention | S3 recovery trigger | historical recovery |
|---|---|---|---|
| A | 없음 | 없음 | 없음 |
| B | 기존 고정 할인 | 없음 | 없음 |
| C_CP | 없음 | 기존 조건 | 원래 S3 |
| D_CP | 기존 고정 할인 | 기존 조건 | 원래 S3 |
| C_CP_G | 없음 | **단일 공통 online guard 후보** | 원래 S3와 동일 |
| D_CP_G | 기존 고정 할인 | **같은 guard** | 원래 S3와 동일 |

R4 개선을 보존하면서 R5 False recovery·선택 손실이 줄어드는가? 실제 평균 상태오차·coverage/NEES/XY/Heading 및 missed useful repair를 모두 평가. **D_CP_G가 B로 되돌아가는 것만으로 R5 Full B0=1.062>1.05이므로 전체 통과로 인정 금지.**

### 2차: 예방 할인 선택을 별도 수정

N1 1차가 보존 한계를 해소하지 못할 경우에만 예방 필요성도 online guard로 구분하는 B_G, D_CP_GG 등을 새 승인 계약으로 평가. R5만 예외로 할인 OFF하는 route-specific 설정이나 posthoc 조건 튜닝 금지.

### 사전 판정 기준 (초안, 동결 전 감사 대상)

- 본 평가 R4/R5×B0/L2×Full/Native-LoS를 원본과 동일하게. 주 점수는 30초 이후; initial, near, late 별도 공개.
- R4 Full: A 대비 Heading ratio <=0.90, XY·NEES·Heading95의 개선/악화와 원래 C_CP/D_CP 이득 소실 여부 보고.
- R5 Full: Heading/XY ratio <=1.05, p90<=1.20, 정상 주행 false intervention 및 tail.
- Native-LoS: primary뿐 아니라 R5 near/late p90 및 worst-seed NEES 보호 악화 공개.
- 상태 정확도 지표와 공분산 넓이/coverage 함께 요구. P만 키워 coverage를 높인 결과는 복구 성공이 아님.
- 개발 seed0–9 및 필요시 이미 존재하는 동일 RF의 새로운 센서 실현 활용. 추가 seed도 **새 RF 환경 일반화**는 아님. 기존 잠금 seed10–29는 이미 결과를 확인한 자료임을 명시.
- N1의 새 threshold·feature set은 독립 사전감사 및 SHA 동결 후에만 확증 실행; 채택 실패 결과도 보존.

## 5. N2: 60초 역사 정보를 유지하는 incremental-shadow 계산 구조

**목적:** 물리 관측모델이나 S3 historical weighting policy는 바꾸지 않고, 5Hz trigger 순간의 burst replay를 분산.

S3 원본은 원래 risk 첫 timestamp 바로 이전 checkpoint에서 현재까지 모든 패킷을 cold reprocess하며, historical 기간 동안 실제 편파 가중치를 기존 값과 0.25 중 작은 값으로 제한한다.

**대안 후보:** 첫 의심 latch가 발생한 순간 최근 5초 위험패킷과 이전 checkpoint를 이용해 대체 discounted EKF shadow를 생성한다. **latch의 첫 위험 패킷 이전부터** 정확히 재생해야 한다. 그 후 매 0.2초 메인 EKF와 함께 shadow를 1-step 증분 계산한다. 후일 recovery trigger가 나오면 후보는 이미 현재시점까지 계산돼 있어 기존 S3의 source identity / PSD / displacement guard를 통과하면 atomically swap한다.

단순히 latch 시점부터 shadow를 시작하면 원본 S3와 다른 개입이 되므로 동일 모델이라 주장할 수 없다. 우선 기존 S3 231 candidate / 52,951 packet cold reference와 경로별 x/P, H, K, weight, acceptance, pose ID, error handling, swap 시점을 동일 조건으로 검산한다. 일치 실패는 STOP. 성공해도 latency 증빙이 없으면 실시간 PASS가 아님.

필수 5Hz scheduled-clock 계측: queue wait, first-latch short backfill, ongoing shadow per-step cost, event/candidate validation, output delay, p50/p95/p99/MAX, peak RSS, dropped packet. 목표 p99<=200ms (기존 고정 예산); 학습/입력 스테이징/독립 verifier 비용은 운영 hot path와 별도 보고.

**특기:** 기존 10s/30s history 단축이 R4 필수 동작을 없애는 개발 반례가 있다. 역사 정보량 절삭보다 연산 스케줄 변경을 우선 시험.

## 6. 독립 감사 흐름과 승인

N0 READ-ONLY audit → N1 설계/계수/데이터 모집단 freeze → INDEPENDENT CODE AUDITOR (다른 checker/runner, GT leak, unit, parity, counterfactual consistency) → 등록 DEV → 독립 RESULT AUDITOR (복구 이득·손해와 R5 보호) → 별도 locked evaluation 승인. N2는 계산 등가성 독립 감사 후에만 5Hz 실측.

원본 S1–S3 코드·데이터·최종 감사 변경 금지. 모든 수정은 별도 브랜치와 새 SHA. 실패를 숨기거나 R4 결과로 전체 범위 채택을 주장하지 않는다. 본 문서는 승인 요청용으로, 사용자 또는 독립 감사자의 채택/실행 승인과 다르다.

## 7. GitHub 근거 파일

- [S2 독립 결과감사](../S2/audit/RESULT_FINDINGS_S2.md)
- [S3 독립 결과감사](../S3/audit/RESULT_FINDINGS_S3.md)
- [S2 개입 전후 이벤트](../S2/runs/EVAL_001/EVENT_ENDPOINTS.csv)
- [S3 개입 전후 이벤트](../S3/runs/EVAL_001/EVENT_ENDPOINTS.csv)
- [S3 잠금 평가 대조](../S3/runs/EVAL_001/PAIRED_SUMMARY.csv)
- [S3 10/30/60초 개발 대조](../S3/runs/DEV_001/AUXILIARY_PAIRED_CONTRASTS.csv)
- [S3 원래 checkpoint 구현](../S3/foreground.py)
- [S3 원래 동결 규칙](../S3/RULES.json)
