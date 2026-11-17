# M7 검증 증거 게시

본 게시물은 mount 0 · 앵커 B · R2/R4/R5 · seed 10–29의 완료된 M7 실행 증거다. 주 판정은 B0 및 주입 ARW에 Q를 맞춘 L2이며, Q 불일치 stress는 보고 전용이다. 동결 수치 판정은 모든 arm에서 `M7_PASS=false`다. 실행 완료와 모형 채택은 별도이며, 판정 기준을 변경하지 않았다.

## 읽는 순서

- [요약 및 궤적별 표](attempt_02/brief/REPORT_KO.md), [궤적 요약 CSV](attempt_02/brief/TRAJECTORY_SUMMARY.csv)
- [seed별 판정](attempt_02/assessment/REPORT_KO.md), [궤적·seed별 CSV](attempt_02/assessment/BY_TRAJECTORY_SEED.csv), [판정 JSON](attempt_02/assessment/DECISION.json)
- [동결 계약 6개 및 실행 receipt 색인](attempt_02/completion/RUN_CONTRACT_INDEX.json), [완료 기록](attempt_02/completion/COMPLETION.json)
- [짝 비교](attempt_02/paired_assessment/), [R5 통과별 정보 회계](attempt_02/passages_assessment/), [replay trace](attempt_02/replay/cells/)
- 실행·검증 Python은 이 디렉터리의 `m7_*.py`, `test_m7_*.py`, `check_m7_replay.py`, `verify_m7_implementation.py`에 있다.

`attempt_02`가 최종 실행이다. `attempt_01` 및 초기 구현 검사는 이력 보존용이다. 기존 `COMPLETION.json`의 Git 게시 상태 문구는 완료 당시 기록이므로 그대로 보존했다. 이번 게시 목록은 `PUBLICATION_MANIFEST.json`으로 구분한다.

## 데이터와 경로

NPZ와 JSONL은 저장소 기존 규칙에 따라 Git LFS에 저장한다. `git lfs pull` 후 실제 데이터가 내려받아진다. 이 디렉터리의 `.gitattributes`는 CRLF 자동 변환을 막아 동결 파일 바이트를 보존한다.

`PUBLICATION_DEPENDENCIES.json`은 동결 계약이 직접 hash-pin한 외부 입력 70개의 원래 절대 경로를 저장소 경로와 연결한다. 기존 HEAD에서 같은 SHA256이 확인된 67개를 재사용하고, 저장소에 없던 원본 evaluator NPZ 3개만 `publication_dependencies/`에 복사했다. 원래 계약과 입력은 수정하지 않았다. 과거 부모 계약의 재귀 의존성 전체를 조사했다는 주장은 하지 않는다.

모든 seed는 동일한 RF 실현을 공유한다. seed 반복을 독립 환경 검증으로 해석할 수 없다. 감사 범위는 원 감사 기록을 따르며, 게시 해시 검사는 별도의 과학적 독립 감사를 뜻하지 않는다.
