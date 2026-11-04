# SM0-FRESH-CANARY-001 — 신규 Native RT 관문

역할 IMPLEMENTER. 기준 PR #28, Git 17cbfb8bef78518729d5010dbf463df87e828c0c. 사용자 2026-11-04 「순서대로 실행해」와 PR28_AUDIT_COMMENT.json의 감사 의견에 따른다. PR #32는 closed/unmerged이며 가져오거나 병합하지 않는다.

## 이번 실행 범위

1. 독립감사에서 수용된 PRECISION_AMENDMENT_001/producer.py와 qa.py의 실제 SHA, 원본24개 입력/은행2개/환경을 다시 잠근다. scientific producer를 수정하지 않는다. 이 실행의 launcher/PLAN/계약/감사 의견 해시도 GO에 묶는다.
2. 독립감사자가 R4_aB_m0 pose194 한 개에만 신규 GO를 발급한다. 기존 GO를 재사용하지 않는다.
3. 원래 좌표·방향·source·solver·seed·257개 주파수·locked WSL 환경에서 신규 PathSolver를 실행한다. CAPTURE_001은 없던 디렉터리여야 한다. 최초 STOP과 이전 결과는 수정하지 않는다.
4. 별도 감사자는 원본 호환 per-ray/reduction 및 complex128 그룹, Full/LoS 전체 및 각 RX, 독립 F64 합산, semantic groups/counts/missing, valid/direct mask, per-bin 메타데이터/해시를 검증한다. legacy 및 archive Full/LoS의 Hann257/IFFT1028·strongestRX30% leading-edge tap을 독립 검산한다. 모두 통과해야 신규 DATA_AUDIT PASS다.

Full 상대L2 1e-3, LoS 1e-5를 전체와 RX별로 적용하고 F64 및 legacy 자체합산 상대L2/max-normalized는 1e-8을 유지한다. 실제 분석 채널은 complex64 원본 위상에서 complex128로 그룹 합산한다. F64-LoS의 과거 재현 진단 차이는 삭제하지 않는다. receiver tap 비교만 허용하고 chain/surface attribution은 이번 실행에서 하지 않는다.

## 중단과 후속 관문

입력/코드/환경/권한/pose 불일치 또는 수치·tap·메타데이터 실패가 있으면 STOP하고 원시·로그·검사 결과를 보존한다. 자동 재시도·기준 완화·pose 대체는 하지 않는다. 실행 성공과 독립감사 수용을 구별한다.

새 canary DATA_AUDIT PASS 뒤에도 나머지14개 확장은 별도 승인 전 실행하지 않는다. 이번 문서는 그 승인을 생성하지 않는다. 이전 BATCH_AMENDED_001 및 C0B_ANALYSIS_001은 기존 실행 이력으로 보존하고 이번 신규 관문의 대신으로 사용하지 않는다. 새로운 C0-B·C1·C2도 이번 단계에서 실행하지 않는다.

Windows managed-processes는 launcher를 소유한다. WSL 계산을 Windows Job 안의 Linux process로 주장하지 않는다. foreground WSL 명령의 실제 종료를 기다리고, 완료 후 manager finish 및 해당 WSL producer 종료를 확인한다. 실행 전 잠금/GO, 신규 원시 데이터, 독립 결과감사와 후속 관문 상태를 단계별로 GitHub에 게시한다.
