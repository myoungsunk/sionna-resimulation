# R1–R5 보완본 사전 유효성 평가 및 남은 R4 결함

기준: 2026-11-02, 원격 `ca8cb43777100a0f5fae53978c0e4096d49701ff`.

**사전 판정: 수치 자료는 검사한 범위에서 ACCEPT_WITH_BOUNDARIES; R4 QA 완결성은 REVISION_REQUIRED; 별도 독립 감사자의 최종 서명은 PENDING.** 이번은 제안자 문맥에서 독립 감사 준비를 위한 검토이며, 새로운 독립 감사 객체의 최종 인증을 대신하지 않는다. 구현·원자료·기존 결과·threshold를 변경하지 않았다. 새로운 RT 또는 전체 필터 재실행은 없다.

## 1. 실제 완료한 확인

- GitHub HEAD 일치. 이전 감사 `daf9999057c0ac32ae0ca8be20021ae9f31d1d22`와 비교하여 신규 27파일, 기존 수정/삭제 0개.
- 보완 ZIP 350,036 bytes / SHA-256 `18a99461a245be53b46bcfa0c4ac1596383f74459b4f17dc981e5bb62e51d70d`. 내부 inventory의 42파일 SHA·크기 일치.
- 게시 영수증의 23개 blob SHA는 확보한 파일과 일치. 원격 code blob은 `5566bcb53b32075af0f72ad83e2565138d8bc6c3`. 27개 원격 파일 모두를 개별 재다운로드한 전수 byte 검증으로 표현하지 않는다.
- 정확한 의존 입력은 RERUN ZIP 219,512,794 bytes / SHA `d2c9ab428ae676579a79907451a7523615876d3075f24f6abe7ee279ba75f7b2`. 입력 lock 108개 SHA를 확인했다. ZIP에 빠진 ±45 FFD 은행은 이전 artifact에서 별도로 회수해 지정 해시로 보충했다.
- 제출 `repair_v2.py`를 변경 없이 실행하면 PASS / 24배치 / 25,088 비교 / 67 음성시험이 재현됐다. 이는 실행 일관성이며 검사 의미의 증명은 아니다.
- 제출 helper를 사용하지 않는 Cholesky 갱신으로 실제 mu_MB→mu_BB 치환 24배치·25,088 packet의 state/P/K/NIS를 archived BB shadow와 대조했다. 허용오차 이내이며 mean 오염은 갱신을 바꾸었다.
- 144개 score 행의 Heading RMSE·Heading 평균오차·XY RMSE·수용수·평가구간 수용수 5량을 직접 재계산했다. 최대차 <1e-10.
- R5 reference/target 스냅샷 144개에서 rho/sigma/control/prior/h/J/mu/R/nu/S/K/NIS/mask/posterior와 최초 state/gate 차이를 원 trace에서 재확인했다.
- 132 trace 및 전체 score CSV는 이전 감사 원자료와 byte-identical. 물리/shadow/FD 표의 해제된 내용도 동일하다. gzip 헤더에 따른 압축파일 바이트 차이는 데이터 변화가 아니다.

## 2. 보완 상태

|항목|사전평가|
|---|---|
|R1 원본/재구현/부분 게시 식별|범위를 명시한 상태로 보완 확인. 원본 15503350은 여전히 MISSING|
|R2 사후 보완 admission|추가 기록 확인. 과거 사전 독립승인을 소급하지 않음|
|R3 실제 평균 동일화|24배치/25,088 별도 산술 확인|
|R4 필수검사 완결성|현재 수치 5,288개는 허용 이내. 음성시험/시간/분모 guard는 아직 미완결|
|R5 첫 분기 실제 값|144 상세 스냅샷 재검산. 48 same-prior 원장은 다음 독립 감사 범위|
|R6 물리-갱신 구간|탐색적 사용 가능. 서로 다른 분모를 같은 효과로 읽지 않아야 함|

## 3. R4-OPEN-01: 이전 검사값 재사용으로 음성시험 PASS가 무력화될 수 있음

원격 소스 `code/repair_v2.py` 287–294행:

```python
for name in ['pose_id','t']:
    ...
    try: trace_metrics(B,case,bias,arm,gate,copied,T)
    except (ValueError,AssertionError): detected=True
    else: detected=any(got[c]>TOLS[norm[c]] for c in got)
```

현재 호출의 반환값은 버려지고, `got`은 직전 dt 오염 시험의 반환값이다.

**실제 반례:** pose/time 검사 두 개의 현재 반환값을 의도적으로 모두 0으로 바꾸었는데도, 두 음성시험은 `observed=FAIL, status=PASS`로 남았다. 그러므로 67/67 중 이 두 항목은 해당 검출기의 작동을 입증하지 못한다. 현재 원래 검출기는 중복 pose에서 key_count=1, 역순 시간에서 time_order=1을 계산한다. 정상 데이터가 오염됐다는 발견은 아니다.

### 구현자 최소 수정

```python
try:
    current_metrics = trace_metrics(B,case,bias,arm,gate,copied,T)
except (ValueError, AssertionError):
    detected = True
else:
    detected = any(
        not np.isfinite(value) or value > TOLS[norm[name]]
        for name, value in current_metrics.items()
    )
```

각 시험에서 이전 변수값을 참조하지 않도록 독립된 스코프로 구성한다. 실제 오염→검출, 무오염→오경보 없음, 검출기를 무력화→음성시험 실패, 순서변경·단독 실행에서도 동일 결과를 확인한다. 이 코드는 제안이며 기존 구현을 수정하지 않았다.

## 4. R4-OPEN-02: 시간과 채점분모 검사 정의

- `time_order=max(0,-min(diff(t)))`는 동일 timestamp를 통과시킨다. 계약의 시간은 strict increasing이다. `t[1]=t[0]` 반례에서 현재 trace_metrics의 모든 오차값이 0이었다. `diff(t)<=0` 검사와 원 timestamp/dt 연결을 검증한다.
- `score_count=count(t>=30)-len(t[t>=30])`는 항등적으로 0이다. 전체 t에 +1초를 넣으면 평가 분모가 829→834로 바뀌어도 이 항목은 0이다. 별도 score 검사가 일부 변화를 탐지할 수 있더라도 해당 check 자체의 보장은 없다. 독립적인 원본 timeline/score mask/선언된 분모와 비교한다.

이들은 제한된 QA 보완 범위다. 현재 저장 데이터에 실제 중복시간이나 잘못된 채점분모가 있다는 증거는 발견하지 않았다. 기존 모델·성능을 바꾸거나 132개 필터를 다시 실행할 필요는 원칙적으로 없다.

## 5. R6 분모 주의와 데이터의 사용 범위

제출 896구간 중 544구간은 signed 항의 `n_used`와 loss의 `n_score` 개수부터 다르다. 전자는 전체시간 fixed-accepted, 후자는 t>=30의 모든 후보다. 서로 다른 분모의 두 평균을 그대로 인과적으로 대응시키지 않는다.

별도 제공한 `PHYSICS_TO_UPDATE_COMMON_POPULATION.csv`는 `t>=30 & fixed accepted & true-pose all-axis FD stable`의 같은 표본에서 signed K항과 local loss를 재집계한 384개 거리×tap×case×bias×arm 구간이다. 원집계는 보존했다. FD 안정성은 true pose 기준이며 current prior의 미분 안정성과 같지 않다.

## 6. 현재 유효한 결론

- 기존 Heading 12/12, XY 8/12, R4의 XY 악화는 보존·재계산됐다.
- 선택한 상수 대조에 대한 R2/R5 lookup 우세 8조건, R4 constant 우세 4조건도 보존됐다.
- 동일 BB prior의 즉시 Heading MSE와 최종 재귀 RMSE의 우열이 다를 수 있다는 결과를 사용할 수 있다.
- 원본 15503350 복구, V5 fresh inference, 새로운 환경 일반화는 기존 한계를 유지한다. V4는 선택 항목으로서 현재 회고적 수치 결과 수용의 선행조건으로 강제하지 않는다.
- 별도 감사자는 R4 제한 수정 후 실행 계보와 정합성을 재검증한다. MIXED 과학 결과는 감사 실패 사유가 아니다.
