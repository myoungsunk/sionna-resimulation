# 1단계 보완 감사

질문 ID: MBVAR-AUDIT-S1-GAP-CLOSURE-20261029

기록일: 2026-10-29. 역할: AUDITOR. 이 문서는 같은 대화에서 수행한 검사를 정리한 것이며 독립 감사라고 주장하지 않는다.

적용 지침: 저장소 AGENTS.md와 [COMMON_CONTRACT](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/COMMON_CONTRACT.md), [ROLE_AUDITOR](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/ROLE_AUDITOR.md). 정책 기준 커밋은 `73d589ebd0b9da37fc60d2e34c87de5ffb95c107`이다. 로컬 지침은 보조로 읽었으며 동결 정책을 덮어쓰지 않았다.

자료 범위: 접근 가능한 GitHub 코드·workflow·실행 로그·manifest·선택한 artifact, 동결 저장소 bytes, 기존 대화의 직접 검사 기록. 기존 노트는 탐색·과거 결과 설명에만 사용했다. 원래 상위 대화의 개별 감사 전문을 모두 확보한 것은 아니다. 아래 브랜치별 문서는 이번에 확보한 근거를 통합한 기록이며 미확보 전문을 복원한 문서가 아니다.

## 공백 해소표

| ID | 기존 공백 | 확보한 근거 | 근거 유형 | 판정 | 남은 한계 |
|---|---|---|---|---|---|
| G1 | forensics 신규 스크립트 실행 | 4ad의 run_four_priorities.py 존재를 확인. 조사한 tree·workflow·실행 기록에서는 연결된 receipt/D3·D4/output manifest를 확보하지 못함. | 직접 확인 | UNRESOLVED | 미발견은 미실행 또는 부존재 판정이 아님. PB는 상위 실행으로만 유지. |
| G2 | premodel scratch와 저장 코드 동일성 | MANIFEST와 저장소 diag 두 파일 해시 일치. Cloud 시간·기반 SHA와 import 두 줄 차이라는 설명 확인. 제한된 R5-A B0 점수 일치 기록. | 직접 확인 + manifest/이전 제한 검사 재사용 | PARTIAL | scratch 원본·실행본 해시·실행 로그·runtime import 해석은 미확보. 제한된 수치 일치를 전체 동일성으로 확대하지 않음. |
| G3 | 실제 사용 입력 무결성 | lock 문자열 비교(C), 동결 저장소 trace 재해시(B) 14/14. 대형 input artifact 목록·크기·보존 상태 조사. | 직접 확인; 14/14는 2단계 갱신 | PARTIAL | 과거 실행 input artifact bytes(A) 0개. FFD bank 실제 재해시(B) 0/2. 전체 RF 미검사. |
| G4 | 실행 당시 import 해석 | workflow checkout·REFLECT_ROOT·frozen fetch·준비 로그·sys.path·일부 코드 snapshot 동일성 확인. | 직접 확인 | PARTIAL | 실행 당시 module 경로·전 의존성 해시 snapshot이 없음. workflow 구조의 뒷받침과 직접 module 증명을 구분. |
| G5 | noise premise 생성 출처 | control HEAD에서 JSON·계획 추가 확인. 생성기·명령·실행 receipt·입출력 해시 연결 미확보. | 직접 확인 | UNRESOLVED | 미검증 premise로 분리. 6개 결과 자동 무효화 또는 pose 인과 해석 승인에 사용하지 않음. |
| G6 | 작은 결과 artifact 파일 연결 | causal/time-GM API digest·로그·ZIP bytes 재해시·내부 manifest·CSV 해시·entrypoint source 해시 대조. | 직접 확인 | CLOSED | 결과 artifact 범위만 닫힘. causal 입력 lock 없음; time-GM lock은 해시 문자열이고 원문은 ZIP에 없음. |

G3의 B14/14 표시는 이후 2단계 읽기 전용 검사로 갱신한 값이다. 최초 보완 감사 시점의 B1/14를 과거부터 전수 확인한 것처럼 소급하지 않는다.

## 코드·기록 위치

- G1: [신규 forensics 코드](https://github.com/myoungsunk/sionna-resimulation/blob/4ad94fe652d847592aa78ba017dd0a6a517652a1/research/DS_MASK_CAUSAL_X1_X2_20261026/ds_state_info_forensics/run_four_priorities.py). run 40670474984는 해당 스크립트 호출 근거로 사용할 수 없었다.
- G2: [premodel manifest](https://github.com/myoungsunk/sionna-resimulation/blob/06a8a0922e0f4b2fef79316bcfd77035475c2715/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/MANIFEST.json). 기반 소스 4ad94fe652d847592aa78ba017dd0a6a517652a1, Cloud 기록 02:42–03:01 UTC. commit 설명의 session_01X1n7vGdtzXNsGwYex2meNS는 실행 귀속 단서이며 실행 receipt가 아니다.
- G2 저장 코드 SHA256: diag_mbvar.py = 1fc906ae2c30ffface52fc97adfa93cd8702b8c33475529a17bb9b2753635af1; diag_overcount.py = 92aa185a364796986a34d81b69ab442babeedc9b731e500bc07ca62665b86e23.
- G4: [동결 추출 경로](https://github.com/myoungsunk/sionna-resimulation/blob/9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13/research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/fetch_inputs.sh#L6-L51). revalidation 저장 snapshot의 확인 파일은 ctl_core.py/run_stage.py/aggregate_ctl.py/revalidate.py이며 확인 범위 밖 전체 모듈 동일성으로 확대하지 않는다.
- G5: [noise premise](https://github.com/myoungsunk/sionna-resimulation/blob/0a0e2237f085fa32683e4ae603cf5ca2372d2130/research/MBVAR_CONTROLLED_SIM_PLAN_20261029/PREMISE_CHECK_NOISE.json). R4B 742개 비교 및 2.22e-16 차이는 JSON의 주장이다. 생성 출처가 연결되지 않아 독립 확인값으로 취급하지 않는다.

## 실행→출력 artifact 연결

| 실행 | artifact | ZIP bytes | SHA256 | 내부 확인 |
|---|---|---|---|---|
| [40825807998](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40825807998) @ 4e14448a8af81c3e99cd257f23cb07615ebd8a15 | [12876686764](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40825807998/artifacts/12876686764) | 8442 | 3d57c9f60c952142befcd739637d6fb55994ce32da201b0c904ce58aa26b14cd | 6개 내부 파일 재해시; CSV 4/4 manifest 일치; entrypoint 소스 해시 대조 |
| [40828341230](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40828341230) @ 7fab61cb1b26240b8031b77e277bc6ab92651245 | [12877941768](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40828341230/artifacts/12877941768) | 10534 | 304ac6178a681f16f9958ab43a3237e9b8837ac35670f29853567def8d5ac7db | 9개 내부 파일 재해시; CSV 7/7 manifest 일치; entrypoint 소스 해시 대조 |

API digest의 문자열 대조, 내려받은 ZIP bytes의 SHA256, 내부 파일의 SHA256은 각각 확인했다. 내부 파일과 manifest는 [증거 JSON](evidence/provenance.json)에 보존한다. ZIP에는 entrypoint 소스 전체가 포함되지 않았으며 manifest 소스 해시를 저장소 실행 SHA의 실제 소스와 비교했다.

## 입력 증거 A/B/C 구분

A = 과거 실행 artifact 실제 bytes, B = 현재 동결 저장소에서 취득한 bytes, C = 기록된 해시 문자열 비교.

A 입력 검증 수는 0이다. B는 CONTROL 14/14, FFD bank 0/2이다. C는 premodel lock과 revalidation R4B lock 및 14 CONTROL의 상위 OUTPUT_SHA256 기록을 비교했다. B/C만으로 과거 실행에서 동일 bytes가 소비되었다고 단정하지 않는다.

대형 input artifact는 control 12874606654와 revalidation 12877504527이고 각각 510272926 bytes, 조사 시 expired=false였다. API digest는 각각 2a95cf8d9a9b37794d01f81a383cbd8cb5247f7439085f5b8eb6b4b487e1a91b 및 4109a4d654f938259a1815945157c8cd3a34fa90f976d9d54dd638f517185b0f이다. ZIP digest가 다르므로 같은 크기만으로 동일 파일 묶음이라고 보지 않는다. 약 248MB짜리 bank 2개와 약 510MB input ZIP의 무차별 다운로드는 수행하지 않았다.

## 남은 공백의 영향 및 최소 자료

| 공백 | 영향·유지/보류 | 최소 자료 | 새 실행 필요 여부 |
|---|---|---|---|
| G1 | 신규 D3/D4 결과의 실행 귀속 보류; PB 상위 결과 유지 | 원래 호출 명령·로그·RUN_RECEIPT·출력 manifest | 과거 증명에는 역사적 자료 필요. 새 실행은 대체 증명 불가 |
| G2 | 저장 코드 정적 감사 가능; scratch 전체 동일성 보류 | 원래 scratch snapshot/hash/import 경로·실행 로그 | 과거 증명에 새 실행 불충분 |
| G3 | 현재 동결 입력 정렬 검사 유지; 과거 소비 bytes 단정 보류 | 보존된 input artifact 개별 파일 접근 또는 승인된 선택 취득 | 재필터 불필요; 원래 입력 bytes 접근 필요 |
| G4 | workflow로 뒷받침된 경로 유지; 완전 runtime 증명 보류 | 원래 module 경로/해시 또는 동등 snapshot | 새 실행은 과거 환경 확정 불가 |
| G5 | 후속 설계의 확정 premise 사용 보류; 기존 결과 자동 무효화 안 함 | 생성 코드·명령·SHA·입력 선택·해시 receipt | 자료 없으면 새 검증은 별도 승인 작업 |

갱신 준비 상태는 READY_WITH_GAPS이다. forensics 실행·premodel 역사 실행본·noise premise 범위는 BLOCKED/미확인으로 유지한다. 코드 수정·필터 재실행은 없었다. 이 보완 감사 자체에서는 2단계를 수행하지 않았고, 이후 사용자의 별도 지시로 수행한 2단계는 [별도 보고서](STAGE2_INPUT_TIME_KO.md)에 구분했다.
