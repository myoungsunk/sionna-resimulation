# prior provider 2단계 — 개입·분할 설계 v1

질문 ID: FP-SC-PRIOR-PROVIDER-STAGE2. 역할: PROPOSER, 문서 자체검사(독립 감사 아님).
기준: 94b49a5abe8443b8eacf4a1e3600ad3d52b10e9f, detached HEAD, 2026-11-06 KST.
상태: DESIGN_RECORDED_NOT_EXECUTION_READY. 1단계 완료를 입력으로 설계만 작성했다.
지침: 로컬 RESEARCH-GOVERNANCE-v1 COMMON_CONTRACT / ROLE_PROPOSER; 파일 해시는 DESIGN_MANIFEST.json.
기존 PRIOR_INTEGRITY_R1 동결 계약을 변경하지 않는다. 신규 VALID 구현·provider 실행·DR 생성·EKF 재실행·C-only 탐지·E1-02·E2는 이번 범위 밖이다.

## 1. 질문과 경쟁 설명

질문: 수치적으로 정상인 잘못된 prior를 과거 정보만으로 경고할 수 있는 범위와, 추가 절대 근거가 없어 판단할 수 없는 범위를 구별할 수 있는가?

- H1: UWB reset 없는 DR 비교와 과거 innovation은 prior 단독 점프/드리프트 경고에 기여한다.
- H2: 공유 초기 편향·센서 오차 또는 잘못된 RF의 자기 지지에서는 두 비교가 모두 작은 채 prior가 틀릴 수 있다.
- H3: 항상 UNKNOWN으로 보류하면 오승인은 줄지만 실용적 P/M 가용성은 확보되지 않는다.

H1과 H2는 동시에 참일 수 있다. 불일치 탐지 성공을 절대 정확성 인증으로 확대하지 않는다.
주안은 VAB 그대로다. 비교 provider를 선택하는 시험이 아니며, 평가 후 잘 나온 조합으로 주안을 교체하지 않는다.

## 2. 표본·분할 — packet 무작위 분할 금지

기존 dynamic 6,272행 = R2 979×2 + R4 742×2 + R5 1,415×2.

| 용도 | 데이터 | 행수 | 규칙 |
|---|---|---:|---|
| 보정·개발 | R2 Full | 979 | 향후 임계값/이력창 선택은 여기서만 수행 |
| 대응 음성대조 | R2 Native_LoS | 979 | 동일 R2 개발 그룹. Full provider 입력으로 혼합 금지 |
| 고정 경로 평가 | R4 Full / Native_LoS | 1,484 | 보정 후 설정 잠금, 별도 결과 공개 |
| 고정 경로 평가 | R5 Full / Native_LoS | 2,830 | R4 결과를 본 재보정 없이 동일 설정 적용 |
| 정적 계약 대조 | 기존 static 48개 | 48 | 전부 포함, prior/시간/가짜 이력 생성 금지 |

세 경로는 이미 노출된 개발 데이터다. 위 분할은 이후 튜닝 누출을 억제하는 prospective lock이며, 미노출 시험·새 환경 일반화·외부 독립 검증을 뜻하지 않는다.
행 6,320개를 독립 표본 6,320개로 취급하지 않는다. 같은 route의 Full/LoS·후보 모드·arm·개입 복제는 같은 분할에 둔다.
RF/관측 보정 모델의 donor 또는 학습 데이터가 R4/R5를 포함했는지 미해결이다. 해결 전에는 route-heldout end-to-end 모델 성능이라는 표현도 금지한다.
static은 기존 ID/입력 해시를 전부 보존한다. 동적 DR/M 성능 분모에는 넣지 않는다.

향후 시간 이력은 case별 시작점에서 초기화하고 다른 경로·채널·개입에서 가져오지 않는다. 초기 준비 구간도 전체 분모에 포함해 UNKNOWN으로 보고한다.
평가 결과를 본 뒤 설계를 바꾸면 새 버전의 사후 개발로 기록한다. 같은 R4/R5를 다시 미노출 검증으로 표시하지 않는다.

## 3. 비교 증거와 인과 입력

DR 비교기: xDR[k]=f(xDR[k-1], ds[k], gy[k], dt[k]); gy 단위는 rad 증분이다. UWB posterior/선택 FP로 reset하지 않는다.
prior와 같은 x0/controls의 공통 오차를 기록한다. 차이 공분산은 Pprior+PDR-C-C^T이며 C를 0으로 가정하지 않는다.
C 추적 또는 유효한 보수적 경계가 없는 경우 거리 차이는 진단 특징으로만 사용한다. 독립 확률 곱셈/신뢰확률 해석 금지.

시점 k 허용 입력: 현재 관측 전 prior/Pprior, k까지 도착한 DR, j<k의 main nu/S/nis 및 별도 shadow mask, 초기 근거/보정 버전.
금지 입력: 현재·미래 관측/갱신 결과, GT, reference tap, 다른 채널 arm의 값. 평가용 정답은 출력 저장 후 결합한다.
도착 시각이 없는 기존 기록은 '지연 없는 offline 가정'으로 표시한다. 실제 온라인 지연 대응을 입증했다고 하지 않는다.
main NIS로 shadow mask를 재구성하지 않는다. shadow innovation 결측은 결측 그대로 둔다.

향후 진단 비교는 동일 입력에서 DR-only, past-innovation-only, 둘의 결합, 항상 UNKNOWN을 모두 공개한다.
이는 근거의 기여도 분석이며 기존 C/P/M/PM 정책을 변경하거나 승자를 채택하는 절차가 아니다.

## 4. 개입 사전 명세

아래 숫자는 물리적 고장률이나 안전 임계값이 아니라 설계한 stress 수준이다. 결과를 보며 유리한 수준만 선택하지 않는다.
각 단일 개입은 동일 case의 무개입 대조와 짝지으며 기본적으로 다른 필드를 고정한다. 결합 개입은 명시된 두 종류만 둔다.

| ID | 개입·수준 | 기대 확인 / 주장 경계 |
|---|---|---|
| I0 | 원본 무개입 | 출처·산술·분모 재현. 원본 전체를 '정확한 prior' 정답으로 간주하지 않음 |
| I1 | prior 위치에 ±0.1, ±0.5, ±1.0m; world x/y 한 축씩 | DR와 차이 증가에 대한 경고 민감도 |
| I2 | prior yaw에 ±5, ±15, ±45도; wrap 적용 | 위치와 별도로 Heading 민감도 |
| I3 | prior와 DR 위치에 같은 I1 상수 편향 | 차이 불변이어도 절대 정확성 인증 금지 |
| I4 | prior와 DR yaw에 같은 I2 편향 | 공통 Heading 오류 식별 한계 |
| I5 | 전체 Pprior에 1, 0.1, 0.01 배율 | PSD 보존 과신. 단독 및 I1/I2와 조합; 작은 P만으로 신뢰 승격 금지 |
| I6 | prior 단독 위치/yaw 오프셋을 10초 동안 0→I1/I2 수준으로 선형 증가 후 유지 | 급변뿐 아니라 점진적 오염에 대한 지연 측정 |
| I7 | 잘못된 상태와 양립하는 과거 innovation=0, S는 유한 PSD인 합성 fixture | 작은 innovation을 정확성 증거로 오인하는지. 물리적 RF 생성/현상 재현 주장은 금지 |
| I8 | 마지막 이력 나이 0, 1, 2, 2.2, 5초 및 시간 역전/중복, 결측 | 기존 2초 정책 경계의 계약 검사. 신규 provider 만료기간으로 자동 채택하지 않음 |
| I9 | 현재·미래 RF/GT/reference 값만 변조 | k의 prior 신뢰 출력 완전 불변 |
| I10 | NaN, Inf, 음의 고유값 공분산, 잘못된 shape/좌표 식별자 | 구조 이상 거부/INVALID. 조용한 행 삭제 금지 |

I1/I2/I6의 개입 시작은 floor((N-1)×q), q={0.25,0.50,0.75}. 방향·수준·시작점 복제는 독립 RF 표본이 아니다.
I3/I4는 처음부터 적용하는 공유 상태 오프셋 fixture다. 원본 controls에서 새 궤적을 재귀 생성한 실험과 구별한다.
현재 설계의 저장 배열 개입은 interface-level counterfactual이다. prior를 바꾼 뒤 원본 H/nu/S/mask를 유지한 데이터를 물리적으로 일관된 새 필터 실행이라고 부르지 않는다.
실제 gyro bias·wheel scale 오류를 controls에 주입해 두 궤적을 재생성하는 검사는 별도 replay 계약이 필요한 후속 항목이다. 이번 I4가 그 검사를 대신하지 않는다.
I7은 원본 RF를 변경한 시험이 아니라 합성 provider 입력이다. 다른 합성/원본 기반 결과와 분모를 합치지 않는다.
stale 복구 시 유한 값 복귀만으로 VALID/history refresh를 허용하지 않는 구조를 검사한다.

## 5. 출력과 분모

한 행의 키: case_id, original_packet_id, corpus, channel, split, intervention_id, magnitude, axis/sign, onset_index, evidence_variant.
출력: P/M 각각 state, reason, evidence_ids, scope, valid_until, provenance, input_cutoff, diagnostic residual; 실제 선택 결과는 생성하지 않는다.
원본행수 / 설계 개입수 / 생성 가능수 / 결측 / 오류 / UNKNOWN / INVALID / 기타 상태를 모두 기록한다. 최종 확장 행수는 구현 시 해당 명세의 열거기로 확인한 뒤 실행 전 잠근다.
실패/결측은 삭제하지 않고 분모와 이유를 공개한다. 없는 정답에 평가값을 만들어 넣지 않는다.

- bad-prior 오승인율: bad 정답이 정의된 대상 중 해당 scope의 VALID 비율.
- VALID 조건부 오류율: VALID인 대상 중 bad 비율. VALID=0이면 0%가 아니라 N/A.
- 가용성: 전체 및 정상 정답 대상의 P/M VALID 비율. 항상 UNKNOWN 대조와 함께 보고.
- 경고 지연: 개입 후 첫 SUSPECT/INVALID까지 초 단위. 끝까지 미경고는 우측 검열/미탐으로 별도 보고하며 평균에서 빼지 않음.
- covariance coverage: 선언된 신뢰 구간과 해당 정답의 포함률. nominal confidence와 실제 coverage를 구분.
- 정상 FP 보호: 이번 단계는 selector를 호출하지 않으므로 오정정률/FP 탐지 성능은 NOT_RUN.

원본 bad-prior 정의에 필요한 위치/Heading 허용오차와 mapping 사용 범위는 미확정이다. 비영점 stress를 모두 안전상 bad라고 자동 분류하지 않는다.
정의 전에는 변위별 경고 곡선·보류율만 진단할 수 있으며 FP 정정 안전성 판정은 불가하다.
통계는 경로·채널·개입별로 보고한다. 3개 노출 경로의 연속 행으로 모집단 희귀 실패율이나 독립 이항 신뢰구간을 주장하지 않는다.

## 6. 수용·기각·판단 불가

구조 요구(위반 0건): 미래/정답 누출, 금지 reset, 다른 arm 입력 혼합, 근거 없는 VALID, static의 prior/history 조작, 기존 후보/실패 기록 변경.
I9 출력은 exact equality, 부동소수점 원본 산술 재현은 1단계 1e-10 허용오차를 사용한다.
위반이면 해당 구현을 기각하며 성능 결과로 우회하지 않는다. 항상 UNKNOWN은 구조 통과 가능하지만 유용성 수용은 불가하다.

실행 전 미해결 항목:
1. P/M 별 요구 정확도 및 허용 오승인 위험·최소 가용성의 수치 예산.
2. 독립 절대 초기 근거 또는 제한된 VALID scope, expiry/복구 조건.
3. 공유 오차/교차 공분산 처리와 이력창·보정 방법의 구체식.
4. muMB/muBASE/R donor 노출 및 시점 감사, versioned history export/행별 join.
5. 개입 열거의 정확한 분모·원본 packet 키 잠금 및 provider 구현의 별도 검사.

이 항목이 미해결이면 SCIENCE_GATE=UNDETERMINED / E1_02_HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING.
현재 단계는 개입·분할 설계 완료이지 성능 기준 동결 완료나 실행 승인 완료가 아니다. 다음 구현·본 실행 전에 별도 계약에서 해결한다.

## 7. 보존·검사·다음 단계

기존 11,095건 배제 및 E1 실패, VAB 주안, canonical 자료와 현재 UNKNOWN/INVALID만 허용하는 코드를 그대로 둔다.
SUSPECT/STALE/P·M 분리 출력은 제안 인터페이스이며 현재 구현된 것으로 표시하지 않는다.
새 파일: DESIGN_KO.md, DESIGN_MANIFEST.json, DESIGN_CHECK.json. 입력/기준 문서 해시와 분할 산술을 자체 확인한다.
문서용 scripts/06_build_reports.py는 이 checkout에 없어 실행하지 못했다. 대신 이 설계의 파일 참조/manifest/분모를 직접 검사한다.
로컬 문서만 작성; Git commit/push 및 원격 실행 없음. 다음 작업은 위 미해결 provider 수학·위험 예산 계약을 구체화하는 단계다.
