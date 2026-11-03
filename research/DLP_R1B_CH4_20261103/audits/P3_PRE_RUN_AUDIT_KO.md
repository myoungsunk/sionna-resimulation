# DLP-R1B-CH4-001 — P3 실행기 독립 소스 사전 검토

## 판정

**ACCEPT_PRE_RUN_SOURCE_WITH_BOUNDARIES**. 별도 계산 검토자가 신규 P2·P3 실행기 소스와 상속한 conventional 기준 계약을 검토했다. 실제 R1 RF 또는 R1 재귀 필터는 이 검토에서 실행하지 않았다. 이 판정은 P0/G1 통과 전 생산 실행을 허용하거나 과학적 결과를 승인하지 않는다.

- 검토자: `/root/ekf_contract_review`, 구현 에이전트와 구분된 계산 검토자.
- V2 계약: `00_REQUEST_CONTRACT_FROZEN_V2.json`, SHA256 `a31a537dd35823d10c1d74ee0cf488d439b7ba2c70114309e024b451a9468596`.
- 실행기: `runtime/r1b_replay.py`, SHA256 `e157573d863847a12da02a392edd6f0a9fdba0a5c4318b4e23b14503edfffd77`.
- V2 계약의 모든 `code_files` 바이트 해시를 실제 파일과 대조하여 불일치 0개를 확인했다.

## 기준선 계보와 필터 일치

사용자 요청서가 직접 지정한 `conventional_ekf_20261102/README_KO.md`, `CONTRACT.json`, `replay_conventional.py`, `INPUT_HASHES.json`을 SHA `9e9133ecb46f96d88ee14652d42f43525fdd1b29`에서 확인했다. conventional은 `diag_mbvar.run`과 `exp_pb.build_controls`를 통해 기존 4상태 core, SourceFFD, SensorV2를 사용한다. 코드 계보상 기존 P2 동결 설정과 R0·거리 오프셋·Q·초기화·seed·공동 NIS·Joseph 갱신이 일치한다. conventional 자체 문서는 독립 감사가 아닌 자기 검사임을 명시하므로 그 PASS를 R1 승인으로 이전하지 않았다.

신규 실행기는 상태 `[x,y,psi,b_g]`, seed0, `R0=diag(0.0068578637,0.0081)`, 거리 오프셋 `-0.5315983906250129 m`, 공동 gate `9.210340371976184`, 평균 보정 0 및 추가분산 0을 사용한다. 동일한 controls·초기 상태·P0가 LoS/Full에 재사용되며, 각 arm은 t0 갱신 이후 자기 posterior를 재귀 전파한다. 주 평가에는 원본 `t>=30`의 767개 시점과 거절된 갱신 시점이 포함된다.

R0의 R1 적용은 동일 관측 정의와 비교 기준의 상속이다. R1에서의 실제 분산 적합성을 입증한 것으로 해석하지 않는다. `h_r`가 연속 거리 bridge이므로 Native LoS 검출 거리와의 잔차가 0일 필요도 없다.

## 검토 중 발견하고 V2에서 해결한 사항

1. 초기 코드가 저장된 S와 K를 독립 재계산값과 직접 비교하지 않았다. V2는 rejected를 포함한 모든 유한 pre-gate 행에서 S·K를 검산한다.
2. 초기 RF manifest 확인은 세 가지 hash 연결에 그쳤다. V2는 생산 PASS, 실제 Native solver 표시, Full/LoS 채널, 917 paired/0 missing, 포트 축 정의, 실제 `(917,257,2,2)` 배열 및 실행기 자체 코드 hash를 요구한다.
3. 유한 공통 마스크가 줄어들어 부분 집계가 주 결과가 되는 것을 막기 위해, V2는 원시 관측·CIR·오차 및 완전성 기록을 보존한 뒤 917개 모두의 finite detection과 양의 FP 합전력을 요구한다. 실패 시 필터를 실행하지 않는다.
4. angle·`abs(H_spsi)` 구간 집계가 추가되었다. 직접파 visibility는 원본 flag가 있으면 보존하고 없으면 MISSING으로 표시한다. 민감도 크기 구간이 smooth-cell Jacobian 검증을 대체하지 않는다는 경계도 기록했다.

## 독립 산술 검사

프로젝트 참 궤적이나 실제 RF를 사용하지 않고 인위적 입력만 사용했다.

| 검사 | 결과 | 최대 오차 |
|---|---|---:|
| 4상태 운동 F의 중앙차분 | PASS | 1.17e-10 |
| 수용·거절 affine 갱신 상태 및 Joseph | PASS | Joseph 2.17e-19 |
| NIS와 gate | PASS | 2.28e-13 |
| TX1에 의도적으로 다른 신호를 둔 TX0/공통 tap 관측 검사 | PASS | range/s 8.88e-16, tap mismatch 0 |
| 정상 fabricated reject log | PASS | 정상 통과 |
| rejected 행의 저장 S만 변조 | PASS | parity HOLD 발생 |
| rejected 행의 저장 K만 변조 | PASS | parity HOLD 발생 |

초기 11개 순수 수치 검사는 최초 실행기 체크포인트 `ff605b...`에 묶여 있다. 검토한 V2 diff는 이 검사에 사용된 core 및 관측기 함수를 바꾸지 않았으며, V2의 새 rejected-log 보호 조건은 V2 hash에 묶인 별도 음성 검사 3개로 확인했다. 실제 R1 성능 검증을 수행했다고 표현하지 않는다.

## 남은 단계

Native RF 코드 사전 검토, 실제 8-pose G1 canary, 실제 비용 동결, 917쌍 RF 생산, P2 항등식, P3 재귀·Jacobians·scores, G4 독립 사후 검산은 각각 해당 단계에서 완료해야 한다. 특히 이 파일은 실제 P3 결과에 대한 승인서가 아니다.

검토자와 구현자는 별도의 에이전트이지만 같은 작업공간과 사용자 연결 시스템을 사용한다. 외부 사람의 서명이나 별도 물리 머신에서의 재현을 주장하지 않는다.
