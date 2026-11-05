# FP-SC-001 E1-02~E5 — 코드 선구현 인계

**상태: CODE_IMPLEMENTED / SYNTHETIC_QA_PASS / SCIENCE_NOT_RUN.**

사용자 지시: GitHub 문서를 기준으로 E1-02부터 E5까지 코드를 개발하고 푸시하되 실제 실험은 실행하지 않는다. 기본 포맷·합성 테스트만 허용한다. 이 변경은 새 실행 승인이나 외부 독립감사가 아니다.

기준 커밋은 `2be558a6fa62bb5472e4e275e684df907ac16e84`이다. 원래 E0/E1-01, S1~S3, W0, SourceFFD, raw RF, 기존 결과·계약은 수정하지 않았다. 신규 RT, 실제 원시 RF 평가, 실제 720/1440 trajectory, 실제 하드웨어 벤치마크는 **0회**다.

## 구현 범위

| 단계 | 구현 |
|---|---|
| E1-02/03 | 동일 CIR 후보에서 C/P/M/PM 오선택 점수, 개발 PR/TP/FP 곡선, 정상·오류·미정의 분모, prior·이력·누락·null 입력 대조 |
| E2-01~04 | B0/B37/C/P/M/PM/PM-FORCE/NN-HARD 및 평가전용 oracle, self-history/teacher-forced, 후보별 점수·group margin·편파 모호성, CAL 최대 27정책 공통 선택, OFAT stress |
| E3-01~04 | F00/F10/F01/F11 추출, same-tap/선택오차 분해, route-heldout TRAIN 잔차 mean/full R, archived W0 동일-prior 단일 갱신과 정합모델/own-gate 대조 |
| E4-01/02 | A~F 각자 prior/P/history/BASE shadow를 갖는 t=0 재귀, A의 원 W0 no-op 검산, 720/1440 예산 격자 검사, seed paired 정확도·coverage·NEES·폭 |
| E4-03 | 선택기·관측모델 모두 heldout인 outer-fold 정책/모델의 명시적 등록·실행 경로. 별도 GO와 데이터 필요 |
| E5-01/02 | scheduled arrival부터 실제 sink flush까지 지연, queue/RSS/중복/지연/역순/누락/null/stale 이력, 이미 출력한 상태 불변 |
| E5-03 | 개발 환경과 분리된 외부 환경 계약·domain ID 검사 및 동일 6-arm 평가 경로. 새 환경 데이터 생성 자체는 하지 않음 |

## 중요한 구현 선택

`selection.py`의 native prior는 SourceFFD의 **native detector range**를 상태 공분산 방향의 7개 stencil에서 평가한 개발용 envelope다. 연속 `geometry+B_OLD`를 tap으로 반올림하지 않는다. 이 stencil은 불확실성 전체를 포괄하는 확률 구간이 아니다. mapping slack와 정책 수치는 제안값이며 실제 실행 전 검토·동결이 필요하다. E0의 정적 mapping 통과가 이 새 envelope의 안전성을 승인하지 않는다.

P와 M의 상관을 무시해 독립 확률을 곱하지 않고 최대 위반 penalty를 사용한다. 4cm를 sigma로 사용하지 않고 실제 elapsed time·속도 상한·history age·detector offset 변화·slack을 구분한다. CIR-only 후보는 기존 E1-01 코드 그대로 사용한다. GT/LoS/route/seed/current posterior를 선택기 API에 넣지 않는다.

E3 학습은 `z-h(xGT)-original_mu`의 **잔여 평균과 전체 2×2 공분산**이다. 보정 R은 기존 R과 거리별 sigma에 다시 더하지 않는다. 선택 문맥을 고정해 Jacobian을 계산하며, 선택 의존성이 사라진 Gaussian posterior라고 주장하지 않는다. 미관측/부족 stratum은 임의 대체하지 않고 중단한다. 이 정책으로 계산이 멈추면 새 보정 계약을 작성해야 한다.

A는 원 detector만 계산해 새 후보 생성비용을 기준선 지연에 섞지 않는다. 각 arm은 독립 재귀를 가진다. 별도 BASE shadow의 게이트와 MB_VAR posterior 갱신은 기존 W0 구조를 유지한다. shadow는 동일 상태에 관측정보를 두 번 더하는 것이 아니다.

## 확인한 것과 확인하지 않은 것

92개 테스트는 synthetic adapter와 작은 합성 배열만 사용했다. 10개 단계의 dispatcher/승인 hash/NPZ 입력/압축 결과/별도 검산 왕복도 합성 4-frame으로 검사했다. 120/240 scenario 검사는 metadata 격자 검사이지 실제 trajectory 계산이 아니다. 실제 SourceFFD·대용량 archive 통합 parity는 아직 실행하지 않았다.

`audit.py`는 production selector/update helper를 호출하지 않고 저장 파일 해시·분모·Joseph 식을 재계산한다. 그러나 같은 작성 세션의 self-check이며 raw RF 재산출, source FFD 독립 구현, 별도 기관의 독립감사 아니다. E3 fixed-prior helper의 검산은 구현 내부 수식 검사이며 E4 trace의 별도 저장 검산과 범위를 구분한다.

남은 실제 검증: native-support 범위, 정책·신뢰도 cutoff, 실제 RF 후보 오류·편파/거리 보호, noisy 조건의 variance, 전체 seed/route 노출, 보정 stratum support, 폐루프 영향, 실제 기기 5Hz, 센서 slip/급회전/노이즈-only 등 추가 장비별 fault fixtures. E5 코드 경로가 존재해도 이 현상들이 실제로 검증됐다는 뜻은 아니다.

## 실행 안전장치

기본 `plan` 명령은 데이터도 읽지 않는다. `run`은 별도 `execute_science=true` 승인, manifest/code/input/source SHA, 환경 일치, mapping 검토, 선행 단계 receipt를 요구한다. 이번 인계의 승인 template는 false다. E0/E1-01 GO를 새 범위의 GO로 재사용하지 않는다.

단계가 계산상 완료돼도 science gate는 `HOLD_RESULT_REVIEW`로 저장된다. 한 번에 여러 단계를 계산하려면 결과 검토 receipt를 주거나 승인에 **탐색적 계속 실행**을 단계별 명시해야 한다. 실패/반례를 PASS로 바꾸는 기능이 아니다. CAL에서 고른 정책은 같은 run의 뒤 단계에 자동 반영하지 않으며 새 SHA 계약으로 다시 동결한다.

설명: `RUNBOOK_KO.md`; 실행 계약 template: `MANIFEST_TEMPLATE.json`, `APPROVAL_TEMPLATE.json`; 가설별 추적표: `IMPLEMENTATION_COVERAGE.csv`; 실제 합성 QA: `TEST_RECEIPT.json`.
