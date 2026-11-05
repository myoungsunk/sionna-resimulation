# E1 후보 개정 재검증 R1 — 실행 계약

역할 IMPLEMENTER / 질문 FP-SC-001-E1-R1. 사용자 명시 요청으로 구현·Snowball 실행·검산·GitHub 게시를 수행한다. E1-02가 아니며 E2_GO=false. 동일 작업자의 별도 수식 검산은 SELF_REVIEW이고 독립 감사가 아니다.

기준 결과 commit 0679b3b615ce99639f5bba4e2515eff209375db7, 과학 코드 ce4ac73cae7debe3754c7b7b0b0008ca66fdbf5d. 구현 커밋은 실행 전 EXECUTION_LOCK에 고정한다. 기존 결과·후보 생성기·후속 adapter는 변경하지 않는다. 기존 governance는 MBVAR-INFO 전용 범위이므로 기존 FP-SC와 동일한 로컬 RESEARCH-GOVERNANCE-v1 및 IMPLEMENTER 역할을 적용하고 복사본/해시를 보존한다.

## 사전 고정 요인

V0=기존 에지±1 및 양측 prominence; VA=기존 후보 + 에지부터 peak까지, 기존 양측 prominence; VB=기존 에지±1, 기존 + 왼쪽 상승 지지; VAB=두 변경 결합. VAB가 주안이다. 실패 후 VA/VB 중 유리한 arm으로 바꿔 채택하지 않는다.

A는 채택된 봉우리의 기존 후보를 보존하고 e<=n<=p 중 a[n]>=max(noise_floor,numeric_floor,0.15*a[p])를 추가한다. B는 기존 BELOW_PROMINENCE인 비경계 봉우리에 한해 절대 지지, a[v]<0.30*a[p], a[p]-a[v]>=max(noise_floor,0.06*G)를 만족하면 추가 허용한다. B-only는 기존 e±1, VAB는 A도 적용한다. G는 두 RX 전체 최대 진폭이고 v는 왼쪽 단조 골짜기, p는 plateau 첫 peak다. 하강 구간을 추가하지 않는다. 6%/30%/15%, noise/numeric floor, cap64와 raw fallback, 두 모드는 그대로다. 참조·route·pose·GT·prior·history를 생성기에 전달하지 않는다.

35개 INPUT_LOCK 원본, 동일 6,320 파형, STRONGEST_ONLY/TWO_PORT_UNION, 4대조=50,560행. 각 arm 12,640행 및 receipt를 따로 기록한다. 새 RF/새 noise/selector/EKF 실행은 0이다. 참조는 생성 이후 평가기만 사용한다. 기존 METRIC_SPEC/SPLIT_MANIFEST의 정상/오류/episode/정적 좌표 분모를 유지한다.

## 판정과 중단

V0는 기존 12,640행의 모든 CSV 필드(후보 hash 포함), 분모·집계·판정을 재현해야 한다. 이 확인이 실패하면 나머지 대조를 실행하지 않고 진단한다. 후보 순서·ID·상태는 정확 일치, 별도 CIR 계산의 실수 비교는 기존 checker의 abs(a-b)<=1e-12*max(1,abs(reference))를 유지한다.

VAB의 dynamic Full TWO_PORT_UNION 큰 오류 supported AND usable exact-tap recall은 전체와 비어 있지 않은 route마다 >=95%여야 한다. 분모 0은 NOT_TESTED. 기존 usable-reference 성공의 신규 실패 0, 기존 후보 및 raw fallback 보존, 기존 usable 파형 신규 overflow 0, cap64 유지가 필요하다. 같은-lobe support와 group의 변경/병합을 기록하고 원래 그룹을 덮어쓰지 않는다.

모든 입력을 유지하고 후보 수 median/p95/max, group 수/병합, 정상/오류별 부담, episode 누락, 시간 및 프로세스 최대 RSS를 공개한다. RSS는 Linux 프로세스 전체(입력 및 로그 버퍼 포함)이며 생성기만의 메모리라고 주장하지 않는다. arm별 총 실행시간에는 출력 기록이 포함되므로 후보 생성 전용 시간도 별도 기록한다. 시간 비교는 실행 환경 영향이 있는 기술 측정이다.

후보·봉우리·지지 채널·group·분모·원본 성공 회귀·overflow를 별도 scalar 계산으로 검산하고 입력/출력 hash를 기록한다. production helper를 재호출해 정답으로 쓰지 않는다. 검사 불일치나 입력/키/개수 손상이 있으면 중단하고 실패 증거를 보존한다. 과학 gate 실패는 계산 오류가 아니며 네 대조를 모두 보존한 뒤 VAB_NOT_ACCEPTED로 판정한다.

## 허용 주장 및 별도 문제

수치 gate 및 검산이 통과해도 노출 개발 corpus의 제한된 후보 가용성 개선만 주장한다. FP 정정 성공, 선택 안전성, 편파/거리 개선, EKF 개선, 새로운 환경 일반화는 NOT_TESTED다. 기존 E1 실패를 소급 PASS로 바꾸지 않는다.

후속 selection.from_pool의 prominence/G * exp(-|tap-edge|) 및 min_support=0.15는 확장 후보를 다시 제외할 수 있다. 후보 버전·지원 의미·eligible·rf_score의 연결 문제는 OPEN_SEPARATE_ISSUE로 남긴다. 이 실행에서 선택기 임계값/점수/adapter를 수정하지 않으며 E2는 시작하지 않는다.
