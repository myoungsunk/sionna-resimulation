# 재구현 설정 메타데이터 해석 기록

수치 설정은 실행 전에 저장한 CONFIG_LOCK.json을 변경하지 않는다. 그 파일은 제안 JSON에서 상속한 allowed_now(문서 작업), statuses=NOT_RUN, input_lock_sha256=null 필드를 포함한다. 이는 과거 제안 상태와 실행 시작 시점의 snapshot이며, 최종 실행 상태나 독립 동결 서명이 아니다.

실제 실행 권한은 사용자의 “다시 구현해서 만들어라 이전 결과랑 비교해” 요청에 따른 회고적 재구현이다. 실제 입력 hash는 INPUT_LOCK.json과 RECONSTRUCTION_START_RECEIPT.json, 최종 상태는 루트 QA.json에 기록했다. base_git_sha는 제안 원고 기준이고 실제 사용한 소스 commit은 RECOVERY_MANIFEST.json의 source_old/source_evidence다. governance_reference_sha 역시 제안의 역사적 참조이며 이번에 취득한 문서 commit은 recovery manifest에 별도 표시된다.

이 기록은 수치 규칙 변경이 아니다. 과거 결과를 이미 본 상태이고 독립 pre-run auditor가 없으므로 FROZEN 사전등록 실험 또는 독립 scientific release라고 표시하지 않는다. 어떤 불리한 결과도 삭제하거나 튜닝하지 않았다.
