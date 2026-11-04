VERDICT: ACCEPT

FINDINGS:

- `ALL_15_AMENDED_SM0_DATA`를 수용합니다. 보존된 R4-B pose 194와 신규 14개 pose 모두 개정 계약의 독립 수치검증을 통과했습니다.
- 첫 canary의 원래 `STOP_MISMATCH` 및 기존 NO_GO는 변경하지 않았습니다. 첫 canary는 사후 계약 재검증, 나머지 14개는 사전 고정된 개정 계약 실행으로 구분했습니다.
- QA/producer/native_math의 계산 함수를 호출하지 않고 독립 검산했습니다.
- 데이터 수용과 C0-B 실행 승인은 별개입니다. 이번 감사는 실제 RF FFT를 실행하지 않았습니다.

EVIDENCE:

- 15개 pose, 3,855개 frequency bin, 241,200개 raw path, 3,975개 artifact 해시 검증.
- 원본 24개 파일, 두 antenna bank, 실제 runtime, pose/timeline, solver, 재질·PLY, TX/RX 위치·포트, per-bin 배열, valid/direct mask, semantic chain/group/count/missing 및 원본 archive slice 검증.
- 원본 complex64 per-ray 계산과 reduction은 저장 값과 비트 일치. 실제 legacy 그룹도 독립 재합산 결과와 일치.
- 실제 분석 Full의 최대 전체 상대오차 `1.2103707894821433e-4`, 최대 RX별 상대오차 `1.2950749541768317e-4`, 모두 `1e-3` 이하.
- LoS 최대 RX별 상대오차 `6.91387858594439e-7`, 기준 `1e-5` 이하.
- 독립 F64 합산 최대 상대오차 `3.441366669238409e-16`, 기준 `1e-8` 이하.
- 14개 batch 종료코드 0 및 `AMENDED_NUMERICAL_PASS`, 전체 완료 상태 확인.
- 정확한 수용 JSON은 `SM0_DATA15_ACCEPTANCE_RESULT`, 개별 결과는 `SM0_DATA15_POSE_RESULT`.
- 재현 검산기 `D:/codex/MBVAR_PRR_001_20261103_inputs/SM0/INDEPENDENT_DATA15_VERIFIER.py`  
  SHA256 `b6ef938a20c855b089475b5c99ef1dab1e4642ba8792d89c78bcae555c730d15`.
- 검산기 초안의 anchor literal 정확 비교를 원본 산식 `2.7-.05`로 교정했습니다. RF 입력·계약·허용오차 변경은 없었습니다.
- 신규 RT 호출 0회, 실제 RF FFT 호출 0회.

MISSING_EVIDENCE:

- C0-B 분석 및 독립 결과감사.
- 과거 원본 ray 계수의 완전 동일성, 실제 환경 일반화 및 Heading/공분산 과신 인과성은 미입증입니다.

REQUIRED_CORRECTION:

- 데이터 수용 범위에서 없음. 승인된 분석 코드와 이 수용 문서의 실제 해시에 묶인 별도 C0-B 실행 GO가 필요합니다.
