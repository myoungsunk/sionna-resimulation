# E1 후보 개정 재검증 R1 결과

판정: **SUPPORTED_EXPOSED_CANDIDATE_AVAILABILITY_ONLY**. 사전 주안 VAB 유지. E1-02 또는 E2 실행 결과가 아니다.

동일 6,320파형 × 두 모드 × V0/VA/VB/VAB = 50,560행을 Snowball KMS에서 실행하고 별도 scalar 계산으로 검산했다. 새 RF·선택기·EKF 실행은 0이다. 기존 E1 실패는 보존한다.

|대조|전체 큰 오류 참조 포함|R2|R4|R5|신규 성공 회귀|신규 overflow|개정 gate|
|---|---|---|---|---|---:|---:|---|
|V0|79/87 (90.80%)|18/19 (94.74%)|13/14 (92.86%)|48/54 (88.89%)|0|0|NOT_MET|
|VA|84/87 (96.55%)|18/19 (94.74%)|14/14 (100.00%)|52/54 (96.30%)|0|0|NOT_MET|
|VB|83/87 (95.40%)|19/19 (100.00%)|14/14 (100.00%)|50/54 (92.59%)|0|0|NOT_MET|
|VAB|87/87 (100.00%)|19/19 (100.00%)|14/14 (100.00%)|54/54 (100.00%)|0|0|MET|

대상은 dynamic Full TWO_PORT_UNION의 |원본 tap−참조 tap|>=2이다. exact tap, supported AND usable 기준이다. 전 모집단의 회귀와 예산 검사는 두 모드 및 정적/LoS를 포함한다. 빈 분모는 NOT_TESTED다.

## 계산·검산 근거

- 구현 commit: `d7e391ba125739ae8e3cabca497208caad4c25bc`. 입력·원래 과학 코드·환경·개정 코드·사양의 잠금은 [EXECUTION_LOCK](RUN_001/EXECUTION_LOCK.json).
- V0 12,640행의 모든 기존 CSV 필드(후보 hash 포함)와 원래 SUMMARY를 재현했다.
- Snowball Linux Python3.12.14 / NumPy2.3.5 / SciPy1.17.0 / BLAS1에서 70개 합성·기존 검사 통과. [시험 로그](RUN_001/TESTS.log). 로컬 Windows의 기존 FFT 극소수 오차 실패는 [별도 기록](LOCAL_TEST_NOTE.json)에 남겼고 기준을 완화하지 않았다.
- 검산은 생산 생성기를 재호출하지 않는 별도 scalar 기하·후보·group 계산과 기존 독립 CIR 재구성을 사용한다. 동일 작업자의 SELF_REVIEW이며 외부 독립 감사나 독립 채택이 아니다.

|대조|검산 비교 수|불일치|생성기 시간(s)|전체 arm 시간(s)|프로세스 최대 RSS(MiB)|그룹 병합 행|
|---|---:|---:|---:|---:|---:|---:|
|V0|15,120,164|0|121.49|160.45|135.81|0|
|VA|16,230,212|0|187.24|232.37|138.11|0|
|VB|15,313,420|0|195.12|240.03|138.43|23|
|VAB|16,247,802|0|194.64|240.67|136.43|23|

최대 RSS는 입력/결과 버퍼를 포함한 프로세스 전체이며 생성기 단독 메모리가 아니다. 전체 arm 시간은 출력 기록을 포함한다. 그룹 병합은 모드별 행 수이며 독립 RF 사건 수가 아니다.

## 후보 부담: dynamic Full TWO_PORT_UNION

|대조|정상 median / p95 / max|오류 median / p95 / max|
|---|---|---|
|V0|9 / 17 / 23|11 / 19 / 27|
|VA|19 / 35 / 47|24 / 39 / 49|
|VB|9 / 17 / 23|12 / 19 / 27|
|VAB|19 / 35.4 / 47|24 / 39 / 50|

전체/정상/오류별 두 모드·파형·corpus 분포와 그룹 수는 [FINAL_VERDICT](RUN_001/FINAL_VERDICT.json)에 모두 보존했다. 각 arm의 EPISODES.csv와 STATIC_COORDINATE_SUMMARY.json에 episode/좌표 결과를 기록했다.

## 후속 연결 및 주장 경계

후속 선택기의 기존 prominence/G × exp(-|tap-edge|) 점수와 min_support=0.15 연결 문제는 **OPEN_SEPARATE_ISSUE**다. 후속 adapter·점수·임계값·모델은 변경하지 않았다. candidate_revision 및 지원 의미를 선택기에 결속하는 작업은 별도다.

수치 gate가 통과한 경우에도 주장 범위는 노출 개발 corpus의 제한된 후보 가용성 개선까지다. FP 정정 성공·선택 안전성·거리/편파 개선·EKF 개선·미지 환경 일반화는 NOT_TESTED다. VAB 실패 시 다른 arm으로 자동 교체 채택하지 않는다. E2_GO=false / E2_started=false.

## 증거 파일 및 복원

- [실행 계약](CONTRACT_KO.md), [사용자 결정 반영](E1_CANDIDATE_REVALIDATION_DECISIONS_KO.md), [수집·원격 종료 상태](COLLECTION_RECEIPT.json).
- 각 arm의 PACKET_CANDIDATE_COVERAGE.csv, SUMMARY.json, BURDEN_ROWS.json, EPISODES.csv, STATIC_COORDINATE_SUMMARY.json 및 *_CHECK/CHECK.json을 함께 제공한다.
- 큰 POOLS.ndjson.gz 원본은 GitHub 파일 크기 제한에 맞춰 40MiB 바이트 조각으로 게시했다. [TRACE_PARTS.json](TRACE_PARTS.json)의 순서와 해시로 복원한다. `python restore_trace_parts.py`는 조각/전체 해시를 확인하며 실험을 실행하지 않는다.
- arm별 원본 ARTIFACT_HASHES는 그대로 유지했다. 최상위 RUN_001/ARTIFACT_HASHES는 모든 로그/receipt가 닫힌 뒤 최종화했다. 그 이전 스냅샷은 PRE_CLOSE_ARTIFACT_HASHES.json으로 보존했다. [포장 기록](PACKAGING_RECEIPT.json).
- production 코드 변경은 새 개정 전용 파일로 격리했다. 원래 candidates.py와 기존 E1 결과는 수정하지 않았다.
