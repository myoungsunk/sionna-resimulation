# STEP1: 입력 게이트와 실행 기록

기준 revision은 `991da089e0723644b244fb663b37c519b6e941e2`이며 별도 `codex/drive-validation-20261008` checkout에서만 수정했다. RF 계산, Snowball 실행, commit/push를 수행하지 않았다. 실행 전 범위와 비교 조건은 `STEP1_PLAN.json`에 기록했다.

## 기존 방식 → 문제 → 수정 이유

기존 G2/G2′는 저장 reference 위치의 missing/unusable 목록을 검사했다. 이 보완을 유지했다. 그러나 CLI에 게이트가 하나도 선택되지 않으면 `all([])`가 참이 되었고, CLI는 FAIL에서도 0으로 종료했다. G4는 발견한 디렉터리와 receipt만 평가해 기대 pose/yaw가 누락되어도 나머지 수치가 좋으면 PASS할 수 있었다. 빈 G4, 중복 receipt/yaw, 비정상 H/frequency 입력은 명시적 평가 실패 보고 대신 예외·NaN이 될 수 있었다.

평가 집합의 완전성과 수치 품질이 모두 확보될 때만 PASS하도록 수정했다. 이 수정은 RF 관측 자체의 일치를 입증하려는 것이 아니라 평가 누락에 의한 거짓 PASS를 막기 위한 것이다.

## 수정 내용

- `scripts/drive_sim/parity_gate.py`: 선택 게이트가 없거나 빈 reference/evaluation 집합이면 FAIL. 선택된 모든 게이트가 실제 보고서에 있고 성공한 경우에만 전체 PASS. FAIL은 CLI exit 1이다.
- G4에는 `--g4-manifest`가 필수다. 사전 task list의 x/y/antenna_yaw_deg를 기대 집합으로 정의하고, 실제 receipt pose/yaw의 누락·예상 밖 항목·중복을 검사한다. task tag/ID 중복, 빈 yaw 목록, malformed files/receipts, H shape·finite 값, frequency 순서, reference bin의 영전력을 거절한다. 예외 유형과 이유를 `input_errors`에 저장한다.
- manifest 경로와 SHA256, 기대 pose/yaw 개수, 적용 threshold 출처와 trace mode를 G4 보고서에 기록한다. receipt와 H는 각 pose 디렉터리에 정확히 하나씩 있어야 한다.
- 사전등록 G4의 `criteria="same as G2"`에 따라 node trace G4에도 G2 기준을 사용한다. 기존 node G4가 G2′의 느슨한 기준을 적용했던 차이를 숨기지 않았다. G2/G2′의 원래 수치 기준과 계산은 변경하지 않았다. anchor-B task manifest가 5개 위치인 사실은 별도 manifest 계약이며, 원래 G4의 prereg_positions=3도 보고서에 남는다.
- `scripts/drive_sim/run_rf_snowball.sh`: 기존 G4 두 report 호출에 각각 사전 생성 task manifest 인자를 추가했다. 스크립트 실행은 하지 않았다.

## 실제 검증 결과

`py -3.10 -m pytest tests/test_parity_gate_coverage.py tests/test_parity_gate_inputs.py -q`: **10 passed**, exit 0. 빈 선택, 빈 reference/manifest, missing/extra/duplicate pose/yaw, malformed G4 files, H shape·nonfinite·zero reference·frequency 역순 실패와 정상 보고서 반환을 검증했다. G4 CLI의 numerical fixtures는 bank/RF를 mock한 offline 검사임을 구분한다.

기준 revision의 원래 `summarize` 함수와 수정 함수에 G2/G2′ 각각 error=0, 1e-7, 0.003의 동일 행을 제공했다. **6개 요약 객체 전체가 정확히 동일**했다. 근거는 `STEP1_REGRESSION.json`이다. node G4에는 error=2e-4에서 엄격한 G2 기준으로 FAIL, error=0에서는 PASS하도록 검사했다. 초기 fixture가 실제 G2 median threshold=1e-4보다 작은 1e-5를 FAIL로 기대해 한 차례 실패했으나, threshold를 바꾸지 않고 fixture를 2e-4로 바로잡았다.

실제 subprocess `py -3.10 scripts/drive_sim/parity_gate.py --out .../STEP1_NO_GATE_REPORT.json`은 **exit 1**, `NO_GATES_SELECTED`, `all_passed=false`를 기록했다. 로그는 `STEP1_NO_GATE_CLI.log`, pytest 로그는 `STEP1_PYTEST.log`에 보존했다. 관련 `git diff --check`는 exit 0이었다.

사전등록·amendments·기존 AUDIT_RESPONSE는 기준 revision과 CRLF/LF 정규화 후 일치한다. 실제 checkout raw SHA256과 Git blob SHA256을 모두 보존했다. Windows CRLF로 인한 raw hash 차이를 수정으로 해석하지 않았다. 기존 결과를 덮어쓰지 않았다.

## 기대효과 달성 여부와 남은 한계

구현 완료와 offline 회귀검증 완료다. 테스트된 누락·빈 입력·중복·비정상 입력은 거짓 PASS를 만들지 못했다. G4 node threshold 적용 변경은 원래 사전등록 계약을 복원한 것이므로 기존 node G4 PASS를 그대로 승계할 수 없다. 원본 trace/H/FFD와 manifest를 사용한 실제 G4 재평가는 수행하지 않았다. L1/L2, full RF 잔차, F01/F02 해결이나 anchor-B geometry 정확성을 이 검사로 주장할 수 없다. G4 geometry와 RF physics는 별도 관측층 검증 범위다.
