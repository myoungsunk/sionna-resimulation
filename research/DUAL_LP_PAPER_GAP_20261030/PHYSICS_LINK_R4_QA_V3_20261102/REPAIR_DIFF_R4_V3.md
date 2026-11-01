# R4 QA V2 → V3 수정 내역

제안자 사전 감사: [`25e16bfb…/01_PREAUDIT_VALIDITY_AND_OPEN_R4_KO.md`](https://github.com/myoungsunk/sionna-resimulation/blob/25e16bfb71786835dbd7260467e243016c0bca6b/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_REAUDIT_READINESS_20261102/01_PREAUDIT_VALIDITY_AND_OPEN_R4_KO.md).

## R4-OPEN-01. 검사 재사용 버그

**기존 코드:** `try:trace_metrics(...)`로 반환을 버린 뒤 앞선 `dt` 오염 시험의 `got`을 재사용하여 `pose_id`와 `t` 오염이 탐지된 것처럼 기록.

**보완 코드:** `r4_mutation_probe(...)`가 오염마다 독립 `current_metrics=trace_metrics(...)`를 호출한 뒤 `required_violations(current_metrics,norm)`를 계산. 미선언/누락 metric은 즉시 FAIL. 이전 검사 결과 참조 없음. 예외는 감지된 오류로 구분 기록한다.

**반례:** 해당 검출기가 모든 metric에 0을 반환하도록 monkeypatch 또는 테스트 override했을 때 각각 4개 오염 시험의 `detected=False`가 확인됐고, **음성 시험 자체의 상태는 `FAIL`**. 메타시험은 이러한 실패가 올바르게 전파됐는지 평가한다. 정상 입력은 `detected=False`, 순서 반전과 단독 실행 결과는 동일했다.

## R4-OPEN-02. 타임라인·채점분모

- `time_order`: `max(0,-min(diff(t)))`를 `count(diff(t) <= 0 or nonfinite)`로 변경. 중복 timestamp가 0으로 은폐되는 문제 해소.
- `timeline_reference`: 검사 대상의 `t_s`와 **독립된 원 CONTROL의 `t_s`** 비교. 원 CONTROL은 input lock 해시 검증 대상.
- `timeline_dt`: 시각 차분과 독립 sensor `dt` 비교.
- `score_count`: `count(t_actual >= 30) - count(t_reference >= 30)`의 절대값. 비교 기준은 원 CONTROL 시간축이므로 자기 비교 아님.
- `score_mask`: 두 채점 mask의 개별 packet XOR 개수. 경계 이동으로 동일 분모라도 다른 표본이 채점되는 것을 검출.

기준 window `t>=30-1e-9`와 기존 score 계산 함수는 **변경하지 않음**. 실제 반례에서 829→834가 검출됐다.

## 최종 fail-closed 계약

- V2의 5,288 필수 검사와 선택 2개를 그대로 보존.
- 신규 432개 trace 수치 검사(3×144), 신규 9개 오염/메타 검사 → 신규 441개.
- 필수 ID **5,729개** 중 누락/중복/불일치가 하나라도 있으면 `BLOCKED/FAIL`.
- R3·R5와 기존 144조건 성능은 재사용·재검증하며 모델·RF 입력·trace 원본 수정 없음.

## 한계

`SELF_REVIEW_ONLY`: 독립 제3자 최종 감사 아님. 원본 `15503350…` 미복구. V4 미실행, V5 fresh inference 불가, 과학적 결과 `MIXED` 유지. 이 변경으로 시간·공간 인과 설명이 추가로 증명된 것은 아님.
