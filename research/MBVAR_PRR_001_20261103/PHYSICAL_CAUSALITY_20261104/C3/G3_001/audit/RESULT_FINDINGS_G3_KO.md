# C3 G3 저장 원시 데이터 독립감사 결과

VERDICT: ACCEPT — 사후 행정 복구를 거친 저장 원시 데이터에 한정

질문 ID: C3-SM2-YAW-001  
실행 코드: ce1f30da7637cef22bc952d029989b5edf939094  
대상: G3 잔여 5좌표 × 4yaw = 20조건, BATCH_001  
독립 검산: INDEPENDENT_G3_RETAINED_VERIFIER_001.py  
검산 소스 SHA256: 05fa625338c4c7c5f3e4183f5f791593bbc9f3942d154dbbf548bbe1ca70bdb6

## 판정 구분

- 저장 원시 데이터의 수치·무결성: ACCEPT.
- 원래 G3 실행의 정상 종료: 수용하지 않음. FORCED_AFTER20, exit_code=3221225786을 보존한다.
- 행정 메타데이터 복구: RECORD_RECOVERY_ONLY. 원본 BATCH_001을 변경하지 않은 별도 인덱스다.
- G4 물리 분해·source-model 평가: 미실행이며 이 감사는 진입 GO가 아니다.
- 전체 알고리즘 채택 NO-GO·실시간 HOLD: 유지.

원래 producer는 전체 MANIFEST를 저장한 뒤 전체 파일 인덱스를 계산하고 최종 stdout을 출력한다. 따라서 MANIFEST의 pending-audit PASS 상태만으로 정상 종료를 입증할 수 없다. 마지막 조건 종료는 2026-11-05T01:13:42.070553+00:00, 전체 MANIFEST의 종료 표시는 01:13:46.590383+00:00이며, 실제 관리 실행은 01:14:19.758159+00:00에 강제 종료됐다. 정확한 중단 명령 위치는 입증하지 않는다.

BATCH_001/ARTIFACT_HASHES.json, 최종 C3_RESULT stdout, 호스트 완료 JSON은 여전히 없다. 이를 사후 생성하지 않았다. G3_EXECUTION_INCIDENT_001_KO.md가 원래 G3_EXECUTION_SUMMARY.json·G3_EXECUTION_REPORT_KO.md의 실행 PASS 표현을 정정한다. 원래 실행은 정상 종료 PASS로 소급 변경되지 않는다.

## 독립 검산 범위와 증거

생산 producer·qa·native_math 함수를 호출하지 않는 별도 검산기를 동결 WSL 환경에서 한 번 실행한 기록을 확인했다. 검산기는 NumPy 1.26.4를 포함한 실행 환경 전체를 원래 runtime lock과 대조한다. 해당 검산 실행은 exit0·natural 종료됐고 ref_count=0, process·supervisor·job 부재가 확인됐다. 이 정상 종료는 검산기에만 해당하며 원래 G3 강제 종료와 구분한다.

검산 관리 resource: 6568503e-adee-4c2b-9d57-5de2ecc0ff5d  
검산 관리 run: 730f961e-f32d-425b-afed-e7b2bff54eab  
검산 시각: 2026-11-05T01:19:47.598181+00:00–01:31:54.111347+00:00

검산 소스와 결과·stdout의 전체 일치, 20개 조건별 결과와 최종 결과의 일치, 빈 stderr, 동결 command 및 현재 11개 코드 바인딩을 확인했다. G2는 기존 독립 DATA 수신증을 재사용하고 수치 검산을 반복하지 않았다. 이전 CANARY_001 STOP의 9개 인덱스 항목도 보존 확인했다.

확인한 데이터는 20조건, 본 bin 5,140개, 반복 bin 60개, 저장 ray 321,600개다. 각 조건은 257 bins·16,080 rays·63 semantic groups이며 bin당 62–63 rays다. 반복 QA와 ray 수는 독립 환경 표본 수가 아니다.

모든 조건의 RAW와 개별 bin을 dtype·shape·값까지 결합하고, complex64 원래 phase/reduction과 complex128 F64 phase를 분리 재현했다. 원시 objects/interactions/valid/source index에서 semantic chain·그룹 membership·count·missing을 재계산했다. joint 및 각 RX의 scalar compensated 합 대비 closure, 모든 bin의 직접경로 계수·기하 지연, 60개 반복의 원시 exact equality를 검증했다. TX/RX 좌표·회전·두 포트 순서·scene/solver·source/bank/runtime/GO/SPEC·게시 코드 바이트도 연결했다.

| 항목 | 독립 확인 결과 | 동결 기준 |
|---|---:|---:|
| F64 재구성 joint relative L2 최대 | 4.1691440616863605e-16 | ≤1e-8 |
| 모든 closure의 joint·각 RX relative L2 최대 | 4.2045323951290937e-16 | ≤1e-8 |
| 모든 closure의 joint·각 RX max-normalized 최대 | 1.2584145566658613e-15 | ≤1e-8 |
| legacy closure 오차 | 0 | ≤1e-8 및 원시 replay exact |
| 직접경로 per-bin relative L2 최대 | 7.665214545538784e-7 | ≤1e-4 |
| 직접경로 지연 절대오차 최대 | 7.564921992414142e-16 s | ≤1e-12 s |
| 결정론 반복 | 60/60 raw exact | exact·채널 ≤1e-8 |

## 별도 행정 복구 검증

조건별 원래 인덱스 20개가 묶는 5,380개 파일과 root의 MANIFEST.json·INDEX.csv·빈 FAILURES.jsonl, 총 5,383개 비인덱스 파일을 별도 복구 인덱스와 대조했다. 모든 파일 집합과 해시가 일치했다. 각 조건의 원래 ARTIFACT_HASHES.json 20개도 별도 SHA로 묶었다. 원래 누락된 root 인덱스를 채우지 않았다.

복구 기록·복구 인덱스·강제 종료 receipt·원래 MANIFEST/INDEX·독립 REDIRECT 처분·정정문·21개 provenance 바인딩을 검증했다. 행정 복구 helper의 종료와 원래 과학 실행의 종료를 구분했다. 동결 허용오차를 낮추거나 새로운 RT·FFT·모델 초기화를 실행하지 않았다. 기존 정상 종료 전용 검산기는 바이트 그대로 보존했다.

## 보고서와 주장 감사

G3_EXECUTION_SUMMARY.json의 20개 조건 ID·순서·yaw·bin/ray/group 수·raw SHA·F64/legacy closure·반복·지연 수치를 독립 결과 및 원래 조건 MANIFEST와 대조했다. 원래 보고서 표의 20행은 표시 정밀도에서 모두 일치한다. 직접경로 독립 계산과 자체 집계의 차이 최대는 2.182710202054542e-16이며 동일한 .3e 표시에 영향을 주지 않는다.

이는 선택된 5좌표·4yaw의 저장 원시 데이터가 동결 수치 QA를 통과했다는 결론이다. G2의 4조건과 합쳐 24조건 원시 자료를 확보했다고 표시할 수 있으나, 24개 독립 환경·물리 인과효과·Heading 개선·G4 완료·전체 C3 과학 완료·알고리즘 채택으로 확장할 수 없다. G4는 실행하지 않았다.

독립 retained DATA 결과 SHA256: 969927084b590cfea7f456a5d67b231969c5afc96ddabe62b17ec373bd68926d  
복구 인덱스 SHA256: f286d30658e7c7f1013befe938715d1beb361612760bee205b2744718cbcdbc3  
강제 종료 관리 receipt SHA256: b9abe69a8bb8162c8ce08e7e54ca1a1f4ded14ad9f5ebebd9173ad7431399dd5

이 판정은 로컬 저장 데이터·실행 증거·정정된 보고서의 감사다. GitHub 최종 게시 바이트/LFS 연결은 이 판정에 포함하지 않으며 별도 게시 확인 전이다.

MISSING_EVIDENCE: 원래 정상 종료 증거는 누락 상태로 보존한다. 이 누락 때문에 원래 실행 성공을 주장할 수 없지만, 별도 저장 데이터 수용 범위의 필수 수치 근거는 확보됐다.

REQUIRED_CORRECTION: 없음. 강제 종료 및 정정·사후 복구 표시를 유지해야 한다.
