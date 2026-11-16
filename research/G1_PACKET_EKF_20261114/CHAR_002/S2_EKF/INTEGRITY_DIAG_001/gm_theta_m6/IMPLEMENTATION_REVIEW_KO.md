# M6 구현과 본 재생 진입 검토

## 범위와 판정

질문 G1-INT-001/M6. 읽기 전용 독립 검토 에이전트 m6_implementation_review는 구현과 본 재생 진입 검증을 ACCEPT로 판정했다. 검토 대상 재생 계약의 SHA-256은 `7a996294f82f5a87de2013b3a49034edafccc02fae0153ba647e9753d779642a`다. 적용 역할은 RESEARCH-GOVERNANCE-v1 AUDITOR다.

검토 시점에 seed 10·11–14 후보 재생은 진행 중이었다. 이 문서의 수용 범위는 재생 구현과 진입 검사다. 전체 성능·공통 통과 대역·5-seed 채택은 최종 출력에서 판정한다.

## 확인한 내용

- 부호 있는 H_sψ 적재, 5상태 AR 전이·교차 공분산, 전체 Joseph 및 G2 Schmidt 갱신이 계획과 일치한다.
- G3·G5는 거리 조건부 편파 기저에서 지정한 gain 행을 조절하며 실제 gain으로 공분산을 갱신한다.
- seed별 G0 R_ref, seed 10 고정 mask, donor LORO 모수와 G1+KI의 인계가 구현에 반영됐다.
- 처음 실행은 trace의 t·pose_id 메타데이터 누락으로 중단됐다. 기존 실행과 수정 전 소스는 replay 및 replay_failed_sources에 보존됐고 attempt_02에서 재검증했다.
- attempt_02/implementation/CHECKS.json에서 기준선 15개가 M5 보관 trace와 정확히 일치했다. G1·G2·G3·G1+KI 비활성 parity, G4 보관 A2 스케줄 parity, G5 비활성 parity가 통과했다.
- 세 궤적의 두 간격 SourceFFD 수치 미분에서 동일 branch 실패는 0건이었다. 변경 branch는 별도 집계했다.
- 독립 선형 후방분포, Schmidt 교차항, signed 적재, AR 정상 분산과 고정 cell 정보 상한 검사가 통과했다.
- 기존 정보 차단 검사에 미래 운동 입력 교란·파일 읽기 차단 검사를 추가했다. online_barrier/CHECKS.json의 30개 설정이 모두 통과했다. 현재 관측 교란과 미래 z/ds/gy/dt/R/muMB 교란의 요구된 prefix 차이는 0이며 파일 접근 시도도 0이었다.
- 집계 코드가 추가 정보 차단 검사 통과를 요구한다. 소스·출력 해시가 기록과 일치한다.

현재 검토 범위의 필수 정정은 없다.
