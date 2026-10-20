# POWER_JOINT 감사 후 재실행 — 진행 상태

이 파일은 실행 완료를 뜻하지 않는다. 현재까지 실제 확보한 결과와 남은 작업을 분리한다. base=5ac914fa0ad53de454278d878962c68c2aebaabb, 작업 브랜치 research/powerjoint-audit-rerun-20261020.

| 과제 | 가설 | TECHNICAL | 과학 판정 | 핵심 수치 | 커밋 / run / artifact |
| --- | --- | --- | --- | --- | --- |
| T0 | 입력 보존 | TECHNICAL_PASS | CONFIRMED_IN_REPLAY | 5개 원본 ZIP SHA 일치 및 release 보존 | run39357262848 / artifact12235433909 |
| T1 | 시간기억 | 기존 7×4×9 완료, 신규 진행 | FALSIFIED_FOR_TESTED | 악화>10% 14/28; coverage 개선24/28; R5 A B0 4.556146→8.764142도 | run39358085399 / artifact12236825429 |
| T2 | 신규 기준선 | 실행 중 | NOT_ESTABLISHED | fullmotion0.25s, 실제 RF시점 갱신, seed0–4 | run39359952488 |
| T3 | SourceFFD 통일 | B_OLD 표 TECHNICAL_PASS | CONFIRMED_IN_REPLAY | L2 J4 M0 .298943 / M45 .180166도 | run39358530627 / artifact12236606373 |
| T4 | F1 흡수 경로 | 기존3이벤트 완료, D4 일부 공분산 오류, 신규 대기 | NOT_ESTABLISHED | R5 V1 skip개선3.020653도; D4 오류는 보존 | run39359599833 / artifact12236901430 |
| T5 | 초기화 | lock/코드 커밋, 정본 대기 | NOT_ESTABLISHED | C03 A/B 및 O01 10설정×FULL/SKIP | bb9c64e |
| T6 | 검출 tap Range | 기존7조건 재귀 완료; 9519점 요청 미충족 | BLOCKED_INPUT | 확보7251점에서 잔차RMSE0, FD0; 2268점 부족 | run39359601219 / artifact12236414588 |
| T7A | 온라인 특징 | 기존 결과 회수 | SUPPORTED_BUT_LIMITED | 12이벤트 abs_s AUC .742857, 포화 .700000 | run39354151551 / artifact12233874874 |
| T7B | 효용 정책 | 준비 중, 실행 전 | NOT_ESTABLISHED | 10s utility target, strict nested route holdout | — |
| T8 | M45 시간 바인딩 | 입력 SHA 검증; clock 보완 후 재실행 중 | NOT_ESTABLISHED | 기존 pose JSON 시간 누락은 frozen Tnone trace로만 바인딩 | run39360284277 |
| T9 | q–거리 교란 | TECHNICAL_PASS, 결과 회수 중 | NOT_ESTABLISHED | 양의 POWER 이득 pooled 거리 회수1.24283; 조건별 기준 미충족 | run39359824661 / artifact12237051901 |

## 정본과 입력

기억 구현1 원본 3fc70f2280471954f1a0673009812ad75437d9ea를 unit/RF parity로 인증했다. SourceFFD source_model.py와 p0_initial.py는 지정4b82e 커밋과 현재 git blob 동일함을 확인했다(SOURCE_IDENTITY.json). 신규 sensor lock v3는 T2 PROTOCOL_LOCK.json이며 최종 hash는 실행 manifest에서 확정한다.

구현2 A–F 원본 ZIP, 구현3 crosscase 실행 코드, 기존 E1 hybrid 실행 ZIP은 현재 확보하지 못했다. T6 원 요청9519점 대비2268점이 부족하며 요청 수를 바꾸지 않았다.

## 바뀐 수치

T3 OLD_LUT_CHANGES.csv에 0.05도 또는10% 초과 변경을 기록했다. 예: L2 M0 J4 .24→.298943도; L2 M45 J4 .16→.180166도. T4 R5 A M0 V1 이전 crosscase skip개선7.751→정본3.020653도. 기존 구 LUT/비정본 센서 수치와 새 정본을 혼합하지 않는다.

## 주장하지 않는 것

조건 수를 독립 장면 수로 간주하지 않으며 p-value를 붙이지 않는다. 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. T10 실험은 실행하지 않았다.
