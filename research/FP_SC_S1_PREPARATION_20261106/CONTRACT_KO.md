# S1 가상 선택 실행 전 준비 계약

질문 ID FP-SC-S1-PREP-001. 역할 IMPLEMENTER 자기점검(독립 감사 아님).
대상 작업 브랜치 implement/fp-sc-vab-shadow-staged-20261106, 구현 기준 9cc34f0675a79ee94e2af39f93bf84bb3e45d587. 원래 source base e416cf62c0cde15151a1851168231da73a0cbfff는 실행기 계약대로 유지한다.

## 이번 허용 범위
기존 canonical 입력을 해시 검증하여 준비 작업 사본에 materialize, 입력 스키마·시간·pose 연결 확인, 코드·원본 모델 소스·FFD bank 잠금, S1 manifest 생성 및 실행기의 preflight만 허용한다. SourceFFD 추론, 후보 생성·선택, EKF 갱신, S1–S3 과학 실행, E1-02/E2 실행과 승인 파일 생성은 하지 않는다.

## 예정 S1 범위(아직 미승인)
기존 동적 6,272파형: R2/R4/R5 × Full/Native_LoS 6개 case. 각 case의 C/P/M/PM 4모드, 총 25,088행을 예상한다. VAB TWO_PORT_UNION, 기존 Policy 전 항목 고정. Native_LoS case는 음성대조이며 Full과 분리 보고한다. static 48개는 이 동적 S1의 대상이 아니며 기존 C-only 증거를 보존한다. 기존 50,560행 후보 비교나 11,095건 회귀집합을 대체하지 않는다.
각 case는 별도 manifest·승인·새 출력 디렉터리를 요구한다. 최초 실행 case와 순서는 승인 때 지정하며 자동으로 6개를 연속 실행하지 않는다. S2/S3는 S1 실행 승인으로 허용되지 않는다.

## 사전 수용 조건
모든 canonical payload가 기존 준비 manifest SHA와 일치하고 LFS pointer가 아닐 것. online 스키마·유한값·단조시간·pose·dt를 기존 loader로 검사하고 evaluator와 정확히 시간/pose 연결할 것. 참조는 준비 점검에만 사용하며 S1 선택 입력에 넘기지 않는다. FFD bank는 원래 BANKS SHA와 일치할 것. 코드·모델·baseline 파일은 SHADOW_COMMON_LOCK_V2에 연결한다. CLI preflight가 각 manifest에서 PASS해야 하며 이것은 과학 실행 승인이나 성능 PASS가 아니다.
실행 시 기존 정책을 바꾸거나 VALID를 만들지 않는다. P/M은 UNKNOWN 기반 반사실 진단, M은 직전 raw FP만 사용한다. 선택 결과를 재귀 이력·운영 FP·EKF로 반영하지 않는다.

## 후속 결과 검토 계획
추후 별도 승인된 S1은 raw/제안 tap, HOLD 사유, 점수·margin·후보집합 hash를 보존한다. S1만으로 참조 대비 성공을 판정하지 않으며, 실행 완전성 검토 후 S2를 별도 승인하여 참조 대비 정상→오류·오류→정상·무변경을 평가한다. S3 이전에는 S2 결과 검토가 필요하다. 효과 크기에 대한 사후 임계값 변경은 금지한다. 결과 누락·중복·해시 불일치·비유한 값·경계 위반이면 중단하고 실패 기록을 보존한다.

## 해석
준비 PASS는 파일·계약·연결이 갖춰졌다는 의미만 가진다. 모델 정확도, P/M 신뢰성, FP 정정 안전성, EKF 개선 또는 실시간 성능은 미검증이다. 실행 환경이 달라지거나 공통 파일이 변경되면 preflight 및 승인 해시를 새로 검토한다.
