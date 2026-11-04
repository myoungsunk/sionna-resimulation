# INDEPENDENT-AUDIT-REQUEST-001 — 물리 RF 인과실험 사전/코드/결과 감사 의뢰

**역할:** 기존 PROPOSER·IMPLEMENTER와 분리된 INDEPENDENT AUDITOR. 독립 세션·runner·수치 reference 구현 요구.
**실행 기준:** GitHub PR #24의 frozen source aac6fe8d4dba2bdaea3d531f3cf4fd196a773ce6, 본 branch의 CAUSAL_VERIFICATION_PLAN_KO.md와 SIMULATION_DATA_REQUEST_KO.md.
**현재 단계:** C0-A source self-QA 완료 / C0-B ray 데이터 미확보 / C1,C2,C3 본 과학 실행 미실시. 이 문서는 GO 토큰이 아니다.

## 1. 요청할 1차 감사: DATA_A0 / C0-A

1. Git에 저장된 원본 composite H_R2/R4/R5 Full·LoS 6개, Tnone 3개, SAMPLES 3개, frequences_hz 1개를 참조 SHA에서 읽고, A0_R1/VERIFIED_INPUT_SUBSET.json의 SHA256을 **실제 bytes로** 비교한다. Git LFS bank 2개는 SHA256과 실제 크기를 확인하되 C0-A 계산에서는 필요하지 않다.
2. 기존 [C0A_EXECUTION_RECEIPT.json](C0A_EXECUTION_RECEIPT.json)과 [Actions 41783949902](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41783949902) 출력 CSV 전체를 독립적으로 집계한다. 원시 trace 3136행, route별 979/742/1415, 30% FP shift와 abs(eMP)>0.3 검사, checksum 비교.
3. 원래 observation.py의 수치를 그대로 호출하는 검사는 재현이지만 독립 관측-chain 검증이 아니다. 별도 FFT(Hann→1028-tap IFFT)·30% detector·2포트 signed power ratio 계산 코드를 작성해 대표 positive/negative pose와 난수 subset을 독립 검산한다.
4. 이미 확인된 R4 pose168의 tap+2, R4 pose234 tap0, R5 pose982 tap+2, R2 pose525 tap0 등은 독립 재현해야 한다. 임계값을 결과를 보고 바꾸지 않는다.
5. SOURCE CHECK vs TECHNICAL PASS vs PHYSICAL CAUSAL CONCLUSION을 분리한다. noise-free archive를 실제 센서 잡음 포함 trace라고 주장 금지.

산출: DATA_A0_RESULT.json, C0A_REFERENCE_CHECKS.csv, independent source SHA, absolute/tolerance/roundoff, runner/session ID, 정확히 어떤 숫자를 재산출했는지, PASS/HOLD.

## 2. 요청할 2차 감사: 신규 SM0 ray 데이터와 C0-B

- BANK_MANIFEST와 binary FFD banks, PLY material SHA, Sionna/Mitsuba/DrJit 버전, solver seed/settings, frequency/port layout 검증. 원래 compute.py의 4개 pose baseline과 matched composite H 비교.
- 각 reported ray의 path ID/표면/반사차수/복소 257-bin 계수를 독립 파일에서 읽어 complex sum reconstruction 재검산. 동일 direct/Full 2port 비교, path grouping가 주파수 간 뒤바뀌지 않는지 검증.
- leave-one-path/surface 에서 **검출 tap을 고정한 영향**과 **검출기를 재실행한 영향** 분리. 개별 편파 ratio leave-one-out 값은 비선형이므로 덧셈 합 성립 주장 금지.
- R4 pose168/172/173, R5 pose982/465, R2 pose525, R4 pose234 negative-control을 모두 확인. 일부 원인 확인만으로 전체 경로 동일 메커니즘 단정 금지.
- native 생성 Full과 archived H mismatch/NA path 있으면 FAIL/HOLD, 사용자 또는 제안자의 새 tolerance 승인 없이는 재설정·선별 포즈 제외 금지.

산출: C0B_CODE_AUDIT.md, C0B_PER_RAY_CHECKS.csv, C0B_RESULT_CLAIMS.csv, missing/ambiguous path reason, SHA·runner proof.

## 3. 요청할 3차 감사: C1/C2 EKF 코드와 과학 결과

- **무개입 parity:** 원래 MB_VAR W0 원본 mask/H/K/P/μ/R/Q, source code/seed/pose_id에 대한 F64 독립 검산.
- **C1 고정 K:** 동일 prior와 Full 평균/분산을 유지한 상태에서 F/F vs L/F, F/L, L/L의 상태 갱신 delta=K delta_z 및 wrap check; 동일 gain이면 P가 달라지지 않는다는 진단 대조 포함.
- **C1 게이트 변경:** F mask vs O self gate 분리. 이진 accepted/denied와 z_r/z_s 별 영향, range-only survivor, covariance cross channel 중복 및 Joseph 수식 검증.
- **C2 재귀:** 앞선 hotspot을 기준으로 선택했다는 점, GT oracle Full/LoS switch가 online input으로 들어가지 않았는지, 각 arm t=0 동일 x0/P0/Q/μ/R/rf/controls로 시작했는지 독립 검사. Time-scale 0–2/2–5/5–10/10–20 및 t>=30, negative controls.
- 물리 eMP, 잔여 epsilon, 상태 δh, innovation ν가 같은 mean/channel convention에서 일치하는지 검산. H_psi(s/rad)와 g_GT(s/deg), Jacobian·K를 혼용하지 않음.
- 실제 heading/XY state error와 P/NEES/95% coverage를 구분. 단일 패킷 상관으로 전체 재귀 인과율을 주장 금지.
- 공개 seed들의 같은 RF 유래 종속성, 개발/holdout 오염, 경로별 learned mean 계보 유지.
- C2가 성공해도 새 복구 알고리즘 S1–S3 전체 채택이나 실시간 200ms PASS로 자동 확대 금지.

산출: C1_CODE_AUDIT_RESULT.json, C2_RESULT_AUDIT.md, CONTROL_MATCH.csv, CLAIM_EVIDENCE_MATRIX.csv, code/data/contract SHA, reviewer runner logs.

## 4. STOP/권한

**즉시 STOP:** source SHA 불일치, bank mismatches, native-ray reconstruct FAIL, path labels 미정, sensor port swap, unit error, pose misjoin, 새 oracle GT feature의 online 누출, 무개입 F64 parity FAIL, 한 관측의 중복 사용, 원본 모델/결과 덮어쓰기, 사후 target/window/threshold 변경, 개발 실패 은폐, 독립 audit 미확보.

단계별 토큰:
- SPEC_C0B_APPROVED: data schema/solver/허용오차/pose list 승인
- GO_SM0_CANARY: 구현 SHA·고정 bank/scene/solver 후 최소 ray run 승인
- C0B_DATA_ACCEPTED: 독립 complex-path 재합 PASS
- GO_C1_DEV: C1 구현 감사 PASS
- GO_C2_DEV: C1 결과/주장 감사 PASS
- GO_C3_SM2: 동일 위치 yaw counterfactual의 독립 사전 승인

현재 위 토큰은 모두 **NOT_GRANTED**. 단계별 요약 보고를 그대로 믿어 승인 발급하지 않는다. GT·oracle 데이터 사용은 offline 기전 분석에만 허용.

## 5. 요구 결론 형식

모든 단계에 대해 (1) INPUT/PROVENANCE (2) CODE/MATH (3) SCIENCE/CAUSALITY (4) GENERALIZATION (5) REALTIME 별로 ACCEPT/PARTIAL/NO_GO/NOT_TESTED 분리. 복소경로 기전이 식별돼도 R4/R5 전체 재귀 인과 효과가 입증됐다고 곧장 승인할 수 없다.
