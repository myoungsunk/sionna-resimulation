# DLP-PHYS-LINK-001 — 독립 재감사 (2026-11-02)

**판정: `REVISION_REQUIRED`.** 감사 소스는 전체 SHA `ca8cb43777100a0f5fae53978c0e4096d49701ff`로 고정. 본 브랜치는 사전감사 인계 커밋 `25e16bfb71786835dbd7260467e243016c0bca6b`에서 분기했으며 기존 구현·trace·threshold·score를 수정하지 않음.

## 실제 별도 계산 결과

| 검증 | 독립 감사 결과 |
|---|---|
| 수치 비교 | 직접 재계산 **2,091 checks, FAIL 0** |
| R1 계보 | 보완 inventory 42개, RERUN input lock 108개 전수 SHA 일치. 외부 FFD ±45° 두 은행 별도 확인 |
| 원본 보존 | 이전 ZIP과 RERUN ZIP의 **132 trace, 12 shadow, score CSV byte-identical**. gzip 5개는 압축 바이트만 다르고 내용 동일 |
| R3 평균 null | implementer shadow helper 없이 Cholesky / `P - KSKᵀ`로 **24 batch / 25,088 packet** 직접 계산. 최대 state 4.44e-16, NIS 5.68e-14 |
| R4 수치 점수 | 144 논리행 × 8점수 직접 재계산. 최대 heading RMSE 차이 5.33e-15° |
| R5 첫 분기 | 144 raw trace snapshot·state/gate index·first differing field 일치; same-prior 48원장 및 이전 posterior lookup 대응 일치 |
| 물리/갱신 대수 | 3,136 packet의 Full/LoS/SourceFFD port-power→signed s; 50,176 shadow 후보의 innovation 및 signed K분해. FD 9,356 stable / 52 transition 기록 확인 |
| 과학 결과 | Heading 12/12, XY 8/12 개선 회고 결과 유지. R4 XY 악화 및 지정 상수 우세 남음 |

**주의:** 144 논리 비교는 132 물리 trace에 BB_ORIG fixed/self 12 alias를 포함한다. 이 연구는 1개 RF 장면에서 3경로×4 gyro 조건을 재사용한다. 12개 독립 RF 장면으로 주장하지 않는다.

## R4 검증기 결함 — 실제 반례 실행

1. **stale `got`**: [repair_v2.py](../PHYSICS_LINK_REPAIR_V2_20261102/code/repair_v2.py) 287–294행은 pose/time 오염에 대한 현재 `trace_metrics` 반환값을 폐기하고 직전 `dt` 변이의 `got`을 사용한다. pose/time 검출기 반환을 모두 0으로 대체해도 두 시험은 `status=PASS`. 반대로 직전 `dt` 검출을 0으로 대체하면 실제 pose/time 검출이 동작해도 둘 다 FAIL이 된다.
2. **strict timestamp 누락**: `time_order=max(0,-min(diff(t)))`는 `t[1]=t[0]`에 대해 0. 실제 duplicate timestamp가 계약 위반인데 검출 실패.
3. **분모 항등식**: `score_count=count_nonzero(t>=30)-len(t[t>=30])`는 언제나 0. R2 time+1s mutation에서 scoring population이 **829→834**로 변해도 이 검사는 계속 0.

기존 보고서 `5290/5290 PASS` 및 `67/67 negative PASS`는 **검증기 자체의 올바른 작동을 인증하지 못한다**. R4 현재 저장 수치가 오염됐다는 직접 증거는 없음.

## 다음 필수 수정 (별도 구현 커밋)

- pose/time 검사는 **현재** 반환되는 오류 메트릭을 변수에 저장해 판정; NaN/Inf fail-closed. 오염 검출기를 0으로 무력화한 anti-test가 실제 **FAIL** 해야 함.
- `t` strictly increasing 및 원 timestamp–dt 연결 검사. duplicate/역순/간격 변조 시험.
- 독립적 원본 timeline/score mask/선언 분모를 기준으로 `n_score` 검증. 분모 변이 829→834 검출해야 함.
- 정상, 오류, 검출기 무력화, 단독·순서교환, `python -O`을 각각 실행하고 새 ID 매트릭스/receipts를 기록. 본 감사 객체는 소스 수정을 하지 않고 그 후 별도 재감사.

## 수용 범위와 독립성

감사자 역할은 **ChatGPT AI 별도 scratch Python runner**이며 구현자의 점수·shadow 업데이트 helper를 정답 함수로 재사용하지 않았다. R4 반례만 검사대상 함수 자체를 black-box로 호출했다. 별도 *사람*의 서명 또는 원본 15503350의 복원을 가장하지 않는다.

**미검증**: 원본 missing commit의 과거 실행, fresh ML inference, 새 RT 장면, 전체 SourceFFD complex-to-CIR의 새 모델 전수 재실행, 시간 공분산의 물리적 교정, 실제 하드웨어 유효성, holdout 일반화, 전체 누적 인과 분해.

이 감사의 상세 CSV 2,091개, 원본 보존 132행, 입력 SHA, R4 monkeypatch 로그, 재계산 Python 코드는 동일 사용자 대화에 `DLP_Independent_Reaudit_20261102.zip`으로 제공함. 원료 ZIP/FFD 원본은 용량상 포함하지 않음.

**최종 범위 판정: `DATA_ACCEPT_WITH_BOUNDARIES / R4_QA_REVISION_REQUIRED`. 논문용 회고적 수치 결과는 유지하되 `R1–R5 INDEPENDENT_QA_PASS` 선언 보류.**
