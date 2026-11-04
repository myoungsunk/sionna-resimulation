# SM0 V2 — 원본 채널 재현과 F64 광선합 정밀도 분리

**상태:** 제안 개정 / 미동결 / 신규 Native canary 미실행. 원본 R4-B pose194 V1의 STOP_MISMATCH와 모든 원시 결과·독립감사·허용오차 기록을 보존한다.

## 변경 이유와 검증된 산술

기존 원본 LoS와 독립 F64 직접파의 상대 L2 오차는 2.4708055e-5로 원래 1e-5 상한 초과. 동일 저장 raw a(complex64)/tau(float32)에 원래 NumPy 연산식을 사용하면 LoS 차이는 1.5256916e-7; F64 직접파의 진폭 차이만 보면 1.4428146e-7. 즉 위상연산 정밀도 차이가 원인인 것으로 강하게 지지된다.

기존 F64 그룹 재합산 차이는 3.3469e-16, F64 Full vs archive 4.2320e-5로 기존 상한 충족. 별도 Sionna Paths.cfr float32 API는 원래 NumPy의 archive 연산과 동일한 comparator가 아니다.

## 수정된 V2 계약 — 수치 상한 변경 없음

| 검사 | 분리된 comparator | 기존 동결 상한 | 필수 여부 |
|---|---|---:|---|
| archived LoS 일치 | 원래 복소64 NumPy 표현과 같은 연산 순서: a[:,0,:] * exp(-2j*pi*float64(f)*tau)[None,:] | 상대 L2 ≤ 1e-5 | 필수 |
| archived Full 일치 | 독립 F64 모든 경로 합 | 상대 L2 ≤ 1e-3 | 필수 |
| grouped path 합 | F64 ray 합 vs 비그룹 scalar cos/sin, math.fsum | 상대 L2 및 max normalized 각각 ≤ 1e-8 | 필수 |
| F64 직접파와 archived LoS | 원본 vs F64 계산 차이와 위상 | 수치 기록, 판정하지 않음 | 진단 |
| native Sionna CFR32 | 재현 가능성 진단 | 판정하지 않음 | 진단 |

**V2는 실패 후 새로 제안한 검증 계약이다.** 비교 대상이 바뀌므로 원래 V1 STOP을 사후 PASS 처리해서는 안 된다. 원래 허용오차 수치는 보존하지만 새로운 독립 사전감사, 새 code/input lock, 승인 토큰, 원본부터 다시 생성한 단일 canary가 필요하다.

## 데이터·소프트웨어 경계

- 원본 scene, geometry, FFD bank, 원시 Full/LoS 입력, 257개 bin, solver seed 20260924, runtime lock, original raw ray index/vertices, observation first-path detector, MB_VAR/EKF를 수정하지 않는다.
- precision_qa.py는 원본 expression의 complex64와 독립 F64를 분리해 각각 본래 목적에만 적용한다. raw coefficient dtype, tau dtype, DIRECT 개수, 배열 축도 fail-closed 검증.
- producer.py는 새 QA 결과와 두 precision의 archive 오차를 동시 기록하며 출력 RAW에 legacy DIRECT를 추가한다. 원본 데이터를 덮어쓰지 않는다.
- 기존 V1 GO는 V2 스키마 및 새 코드 해시에서 거절된다. 별도 독립 auditor가 발급하는 SM0_GO_V2만 허용하며 첫 pose194로 범위 제한.
- recheck_preserved_canary.py는 보존된 원본 STOP raw를 읽기 전용으로 산술 재판독한다. 이것의 PASS는 신규 native solve PASS가 아니다.

## 실제 재실행 단계 및 중단 기준

**G0: 수정 코드 자체 검사.** NumPy 1.26.4, Python3.11에서 native_math·precision_qa의 합성검증, 잘못된 archive·F64 closure·dtype·V1 token 거부 시험을 독립 runner로 진행. 이 단계에는 Sionna RT 시뮬레이션이 없다.

**G1: 과거 실패 raw 재판독.** 원래 CANARY_R4_194_001에서 raw/manifest SHA와 STOP status를 확인하고, 새 디렉터리 RECHECK_R4_194_V2_001에 amended 산술 결과만 저장. 기존 RAW, MANIFEST 수정 금지. 예상 legacy LoS 약 1.526e-7·F64 그룹 closure 약 3.347e-16이며 실제 숫자는 원본에서 재검산 후 기록.

**G2: 독립 사전·코드감사.** 구현자와 분리된 auditor/runner가 원래 NumPy promotion/order, 물리 path 합, negative controls, schema·GO binding, 런타임, 프리플라이트 및 데이터 출처를 검증. PASS 없이는 V2 GO 발급 금지.

**G3: 단일 신규 native pose194 재실행.** 승인된 정확 code SHA와 code/source/bank/threshold/runtime/precision contract를 포함한 GO_SM0_V2_CANARY.json 발급 후, 원래 WSL2 고정 런타임에서 run_canary_foreground.sh 한 건만. 신규 CANARY_R4_194_V2_001 폴더로 기록. 모든 257 bin의 legacy LoS/F64 Full/F64 closure 검사, first-path tap consistency, raw metadata 해시와 독립 교차검산. 실패 시 STOP; 구 canary 결과 덮어쓰기·나머지 14개 확대 금지.

**G4: 14개 확장**은 G3 독립 데이터감사 PASS 이후에만 별도 승인. 추후 C0-B 반사면 물리원인, C1/C2 인과 EKF, C3 동일 위치 Heading 대조도 별도 동결·승인 절차. V2 산술 PASS만으로 물리/Heading 원인 주장 불가.

## 주요 실행 명령 (고정 WSL 입력이 있을 때만)

G1 (no solver): python3 recheck_preserved_canary.py CANARY_R4_194_001 RECHECK_R4_194_V2_001

잠금 제안: python3 producer.py --source <locked_input_source> --bank <locked_bank_dir> --lock-only INPUT_LOCK_DRAFT_V2.json

G3 (독립 감사 토큰 발급 뒤에만): bash run_canary_foreground.sh

**G0 합성 CI 통과는 G2 독립 감사 및 G3 native canary 통과와 동등하지 않다.**

## 관련 원본

- SM0 원래 독립 STOP 감사: audit/C0B_RESULT_AUDIT.md
- 위상 오류 진단: PHASE_DIAGNOSIS_002/NUMERICAL_DIAGNOSIS.json
- 원래 canary: CANARY_R4_194_001/MANIFEST.json
