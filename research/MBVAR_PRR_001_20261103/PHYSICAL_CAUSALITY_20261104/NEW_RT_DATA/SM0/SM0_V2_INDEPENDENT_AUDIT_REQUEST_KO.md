# SM0 V2 — INDEPENDENT AUDITOR 사전·결과 감사 요청서

**현 단계:** 독립 사전감사 요청 / 새로운 원시 RT canary 미실행 / 원본 V1 STOP 유지. 이 요청서 자체는 코드 승인 또는 GO token이 아니다.

## 감사 우선 자료

1. SM0_V2_PRECISION_AMENDMENT_KO.md 및 원본 audit/C0B_RESULT_AUDIT.md.
2. PHASE_DIAGNOSIS_002/NUMERICAL_DIAGNOSIS.json의 legacy32, F64, Sionna cfr 비교.
3. producer.py, precision_qa.py, native_math.py, test_native_math.py, test_precision_qa.py, run_canary_foreground.sh.
4. RUNTIME_LOCK.json, INPUT_LOCK_DRAFT_002.json, 원래 audit/GO_SM0_CANARY.json 및 CANARY_R4_194_001/MANIFEST.json.

## G0: 독립 수학·코드 감사

- 과거 원본은 raw a=complex64, tau=float32. 직접파 архив 일치 검사는 원본 정확 NumPy 표현 및 연산 순서로 수행. F64 ray sum은 경로그룹 재합/독립 합에만 사용. archived Full과의 비교는 F64로도 유지.
- 이 두 정밀도의 위상·진폭 차이를 삭제하거나 archive comparator와 F64 closure를 혼동하면 FAIL.
- 기존 상대 L2 상한 LoS 1e-5, Full 1e-3, F64 재합 1e-8은 유지.
- 음성 시험: archive LoS에 위상 교란, F64 반사군 에너지 교란, DIRECT index 누락·중복, raw a/tau dtype 변형, 원래 V1 GO 재사용, source/FFD/runtime hash 불일치, 기록된 STOP 원본 오염.
- 별도 runner, 독립 구현 및 계산 증거, 모든 코드/input/blob SHA, 환경·단위·범위, PASS/FAIL/HOLD를 기록.
- float64와 complex64 경로군으로 계산한 물리적 표면 제거 효과·편파비 차이의 민감도도 점검. 이 검사가 불충분하면 물리 인과 기여율 판정은 HOLD.

## G1: 원본 보관 RAW 재판독 (Native solver 없이)

- 오래된 CANARY_R4_194_001의 원래 MANIFEST status STOP_MISMATCH 및 RAW SHA를 먼저 검증.
- 보존된 원시 계수로 구버전 float64 LoS vs archive FAIL과 legacy expression LoS vs archive PASS를 모두 계산.
- 새 RECHECK_R4_194_V2_001/RECHECK_RESULT.json에서 amended 산술만 확인. 원본 STOP 판정을 PASS로 덮어쓰면 안 됨.

## G2: 새 R4-B pose194 Native canary

- G0 독립 코드 감사 PASS와 G1 완료 시에만 독립 감사자가 새로운 정확 코드 SHA와 input hashes에 묶인 SM0_GO_V2 token 발급.
- token: schema SM0_GO_V2, decision GO, authorized EXACT R4_aB_m0 pose194, lock code/source/bank/threshold/runtime/precision_contract/reference 필드 모두 일치.
- 원래 WSL2 런타임과 24개 원본 입력 해시, FFD 2개 bank, 257 bin, solver seed, 독립 ray chain grouping 확인.
- 새 CANARY_R4_194_V2_001의 raw·bins·manifest·해시 검산. archived Full/LoS, 독립 F64 closure와 실제 원본 first-path tap, 부호·포트 순서, 그룹 제거 후 신뢰도/정밀도 민감도 검산.
- 독립 DATA AUDITOR가 원본 simulator/producer 내부 QA와 분리된 checker로 PASS/FAIL/HOLD 기록. PathSolver 내부 산술 동등성은 독립 archive agreement만으로 완벽히 입증되지 않으므로 한계 보존.

## G3: 14개 확장 및 C1/C2

G2 단일 canary의 독립 DATA PASS와 새로운 승인 없이는 나머지 14 pose 실행 금지. 독립 데이터 승인이 있어도 C1 동일 prior EKF 분리, C2 재귀 전파, C3 Heading 개입은 각각 별도 계약과 독립 감사 후 실행.

필수 감사 산출물: AUDIT_V2_CODE.md/JSON, CANARY_V2_DATA_AUDIT.md/JSON, source and runtime SHA registry, 모든 실패 반례, 명시적 PASS/STOP/HOLD, 승인된 특정 pose 범위.

**금지:** 합성 CI PASS만으로 Native ray 재실행 성공/과학적 인과성 성공을 주장하는 것; 사전 기준 변경을 구버전 PASS로 라벨링하는 것; GO 없이 새 solver 실행하는 것.
