# FP-SC-PRIOR-EVIDENCE-R2 — 실행 전 계약

2026-11-06. PROPOSER → IMPLEMENTER → 동일 작업자 자체검사. 기준 94b49a5abe8443b8eacf4a1e3600ad3d52b10e9f.
사용자의 '모두실행'을 따른다. 선행 관문 실패/판단 불가는 후속 P/M E1-02 실행 허가가 아니다. E2 금지.
Stage2 v1을 덮어쓰지 않는다. 최신 지시를 우선해 static48을 prior 개입 분모에서 제외한다. 별도 C-only 계약에서만 사용한다.

## 질문·근거
전체 dynamic6272에서 과거 innovation과 UWB-reset 없는 DR 비교가 제공하는 신호 및 식별 불가능 사례를 측정한다.
현재 prior는 과거 UWB posterior+DR, 별도 DR은 원본 x0+controls만 사용. 공통 초기화·센서 오차가 있으므로 독립 증거가 아니다.
과거 innovation은 j<k만, 채택/기각 모두 유지. 현재/미래 정보와 evaluator는 진단 함수에 전달하지 않는다.
작은 P/매끄러움/작은 innovation은 정확성 인증이 아니다. 독립 절대 위치/Heading 근거 없음. UNKNOWN 유지.

## 계산·개입 사전 지정
원본 운동함수 transition을 재사용해 DR mean만 적분한다. Q 보정/교차 공분산은 미확립이므로 DR 차이로 확률·VALID를 만들지 않는다.
거리 방향은 각 원본 prior에서 등록 anchor(10,0)로부터의 단위벡터, 접선은 그 90도 회전이다. GT 방향 사용 금지.
위치 수준 ±0.1/0.5/1m, yaw ±5/15/45deg. 일정 bias(처음부터), jump(N//2부터), drift(N//2부터10초 선형증가)를 적용한다.
위치만, yaw만, 위치+yaw(동일 수준 인덱스/부호)를 전수 실행. P만 배율0.1/0.01 및 위치·yaw 단독/결합과 각 배율의 결합.
공유 반례는 world x 일정bias±1m 및 yaw±45deg를 prior와DR 모두에 적용. 이는 저장 state-level 반례이지 새로운 물리 RF replay가 아니다.
위치/yaw 개입 후 과거 원본 innovation은 그대로인 반사실 진단임을 표시한다. 연동된 필터/RF 재생성을 주장하지 않는다.
별도 합성 대조: 잘못된 prior와 양립하는 zero innovation, gap/delay(1/2/5s), reinit 경계, 과거 raw FP ±2tap.
이력 개입은 입력 이벤트/검사 대상으로 저장한다. provider 미구현에서 M 강등·복구 성능이 입증됐다고 하지 않는다.
원본 trace mask와 main NIS는 다른 필터 출처이며 서로 gate 동치 검사를 하지 않는다.

## 분할·지표
R2 개발1958, R4/R5 고정평가4314. 모두 EXPOSED_DEV. case/route 단위로 묶으며 연속20초 블록을 기술 통계용 episode로 기록한다.
블록/개입복제/Full-LoS를 독립 환경으로 세지 않는다. static48 제외. 기존43904 stress의 narrow exclusion11095는 SHA와 재집계로 보존한다.
전체 원본 정상/오류 구간 포함. 이전11095만을 보정 데이터로 삼지 않는다.
행별: DR-position/yaw 차이, 과거 최대5초 main NIS 평균(현재 제외), 이력수·기각수, P trace, 평가용 실제 위치/yaw오차.
각 metric의 유한값수/결측수/중앙값/p95/max, 경로/개입별 공개. P coverage는 미보정 진단이지 안전성 PASS 아님.
provider 위험한VALID=용도오류위반VALID/VALID, 활성화=VALID/전체. VALID=0이면 위험은N/A, 활성화0이며 실용성PASS 금지.
용도오차한계/허용위험/최소활성화/독립에피소드 근거 미정이면 provider gate UNDETERMINED. mapping95%를 전용하지 않는다.

## 검사·보존
원본 운동함수의 직선·회전 특수사례, 기존posterior→prior 산술1e-10, 공유bias 차이 불변1e-10,
미래innovation 변조→현재과거통계 exact불변, 기각 기록포함, full6272 행수/키/hash 검사.
합성 이력 무효/초기화에 대해 existing protection의 UNKNOWN/INVALID 및 trusted reset 검사를 재사용한다.
한계/실패는 제거하지 않고 기록. 기존 failure/VAB/생산 provider 코드는 변경하지 않는다.
논리CPU≤3, BLAS1. 새 RT/SourceFFD/선택/EKF posterior 갱신 금지. DR mean 적분은 이번 허용 범위.
실행 전 이 계약과 별도 C-only 계약·runner SHA를 manifest로 저장한다. 결과 후 수정은 별도 실행으로 보존.
