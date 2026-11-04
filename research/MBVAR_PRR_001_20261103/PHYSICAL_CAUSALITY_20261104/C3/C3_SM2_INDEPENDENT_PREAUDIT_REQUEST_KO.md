# C3-SM2-YAW-001 — 독립 설계 사전감사 요청서

상태: PROPOSER DRAFT / NOT FROZEN / NOT RUN. 이 문서는 C3 실행 GO가 아니다.

## 선행 독립감사 근거

- C2/C2_001/audit/C2_RESULT_AUDIT_RESULT.json — 2,640 재귀 궤적의 독립 기술감사 ACCEPT
- NEW_RT_DATA/SM0/C0B_ANALYSIS_001/audit/RESULT_AUDIT.md — 15 pose 선택된 RF에 대한 분석 ACCEPT
- NEW_RT_DATA/SM0/PRECISION_AMENDMENT_001/AMENDMENT_KO.md — 분석 채널은 원래 복소64 위상과 복소128 그룹 합, 별도 F64 독립 검증
- SIMULATION_DATA_REQUEST_KO.md §4, CAUSAL_VERIFICATION_PLAN_KO.md §6 — SM2/C3의 원래 승인 전 제안
- C3/C3_SM2_PROPOSER_CONTRACT_DRAFT_KO.md — 이번 정확 XY·yaw 목록과 중단 조건

## G0 — 독립 사전설계 감사

1. 정확 6개 XY와 공통 yaw 네 값은 원래 실험 정의 및 SM0 실제 pose와 맞는가? x/y/z 및 angle deg/rad, anchor, mount, body→antenna transform, port order·FFD orientation drift가 없는가?
2. 직접파는 yaw에 따라 antenna projection이 바뀐다. Full s만으로 multipath effect를 주장하지 않고, 같은 yaw의 LoS s와 eMP=Full−LoS를 별도로 계산하는가?
3. yaw-only 변경에서 장면 물성·solver seed/정밀도/샘플 수/주파수·TX/RX 위치·FFD bank·receiver 높이·원본 source byte가 모두 불변인가?
4. 새로운 yaw에는 archive composite H가 없으므로 원래 다른 yaw의 archived H를 참조값으로 위장하지 않는가? 신규 포즈의 독립 path sum/직접파 및 detector QA, deterministic repeat check를 정의했는가?
5. R4/R5 원래 실시간 센서 자료를 새 synthetic SM2 yaw data와 혼합해 GT/replay trace로 쓰지 않는가? 과거 C2 같은-RF 공개 seed 결과를 새 독립 environment라고 주장하지 않는가?
6. C3 결과는 동일 XY에서 heading의 simulated RF effect이며, 기존 R4/R5 복구 성공/실패의 전부를 heading만으로 설명하는 결과가 아닌가?

## G1 — 독립 코드감사

SM0 amended producer 기반 신규 yaw-only wrapper의 code SHA/inputs/variants를 검토하고, 구현자와 분리된 checker로 다음 failure injection을 실시:
- RX 좌표 변화·source bank drift·TX port swap·RX port swap·주파수 그리드 변화·solver seed 변화;
- degree/radian 혼동·body yaw에 mount 45deg 이중 적용·안테나 회전 없음;
- 원본 complex64 결과를 F64 결과로 바꾸어 attribution 하는 우회;
- semantic group mismatch/NaN/missing direct path/zero denominator;
- old GO token 재사용·canary 4조건 외 실행·output overwrite·GT leakage;
- malformed archive comparison for previously unobserved new yaw.

코드 감사 PASS는 신규 Native 데이터 수용 또는 과학적 인과 주장의 PASS가 아니다.

## G2 — 한 좌표 4-yaw canary 독립 DATA 감사

- R4_168 x=5.251464, y=0.325895, z=0.45m, yaw {0,180,+35.7,-35.7} 단 4조건.
- 각 조건의 257-bin per-ray raw, two RX Full/LoS, legacy grouped fields, independent F64 closure, per-port FP/ratio/tap, direct delay, output SHA, scene+bank+runtime SHA를 별도 검증.
- 위 모든 검사 후 별도 DATA_AUDIT PASS가 있어야 잔여20조건 실행 GO를 받을 수 있다.

## G3 — 잔여20조건 및 결과감사

24조건 무누락, 각 좌표 내 four-yaw exact equality of positions, same-tap vs detector shift, per-ray path-sum, Full/LoS direct subtraction, Hpsi units, signed polarization denominator floor. 24개 RF를 독립 자연주행 표본이나 시드 반복으로 분석하지 않는다. 결과감사는 물리 현상과 기존 C2 결과의 연결에 주장 경계를 표시한다.

## 필수 산출물

별도 SPEC_AUDIT_C3.json/md, CODE_AUDIT_C3.json/md, 4-yaw GO_CANARY, 4-yaw DATA_AUDIT_C3, 별도 GO_EXPAND20, final RESULT_AUDIT_C3 및 GitHub source-lock/manifest. 각 결과에는 auditor, runner, 정확 SHA, PASS/FAIL/HOLD와 실행 범위를 명시.

승인 없이는 새로운 PathSolver 호출, 20조건 확장 및 C3 Heading 과신/온라인 정책 채택 주장 금지. 원래 S1–S3 NO-GO/HOLD 판정 보존.
