# MB_VAR 6개 브랜치 및 1·2단계 감사

기록일: 2026-10-29. 역할: AUDITOR. 이 문서는 같은 대화에서 수행한 검사를 정리한 것이며 독립 감사라고 주장하지 않는다.

적용 지침: 저장소 AGENTS.md와 [COMMON_CONTRACT](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/COMMON_CONTRACT.md), [ROLE_AUDITOR](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/ROLE_AUDITOR.md). 정책 기준 커밋은 `73d589ebd0b9da37fc60d2e34c87de5ffb95c107`이다. 로컬 지침은 보조로 읽었으며 동결 정책을 덮어쓰지 않았다.

자료 범위: 접근 가능한 GitHub 코드·workflow·실행 로그·manifest·선택한 artifact, 동결 저장소 bytes, 기존 대화의 직접 검사 기록. 기존 노트는 탐색·과거 결과 설명에만 사용했다. 원래 상위 대화의 개별 감사 전문을 모두 확보한 것은 아니다. 아래 브랜치별 문서는 이번에 확보한 근거를 통합한 기록이며 미확보 전문을 복원한 문서가 아니다.

## 문서

- [6개 브랜치 기준 및 실행 연결](STAGE1_PROVENANCE_KO.md)
- [1단계 보완 감사 G1–G6](STAGE1_GAP_CLOSURE_KO.md)
- [2단계 입력·시간 정렬 감사](STAGE2_INPUT_TIME_KO.md)
- [ds-state-info-var-forensics-20261028](branches/1_ds-state-info-var-forensics-20261028.md)
- [mbvar-premodel-diag-20261029](branches/2_mbvar-premodel-diag-20261029.md)
- [mbvar-control-correction-20261029](branches/3_mbvar-control-correction-20261029.md)
- [mbvar-causal-isolation-20261029](branches/4_mbvar-causal-isolation-20261029.md)
- [mbvar-e2-e5-revalidation-20261029](branches/5_mbvar-e2-e5-revalidation-20261029.md)
- [mbvar-time-gm-differencing-math-20261029](branches/6_mbvar-time-gm-differencing-math-20261029.md)
- [기준·실행·artifact 증거](evidence/provenance.json)
- [동결 입력 14개 및 SAMPLES 검사값](evidence/stage2_input_checks.json)
- [수행한 읽기 전용 검사 스크립트](evidence/stage2_input_checks.py)

## 현재 판단

전체 준비 상태는 READY_WITH_GAPS이다. 14/14 CONTROL trace의 현재 동결 저장소 bytes 해시와 행·시간 필드를 확인했다. 과거 실행 artifact의 입력 bytes를 직접 재해시한 것은 아니다. forensics 신규 실행 및 premodel scratch 실행본 연결은 여전히 제한된다.

2단계의 주요 조치 필요 사항은 control의 선택 표본 ACF를 물리 시간으로 환산하는 해석이다. accepted-event lag와 실제 0.2초 lag를 구분해야 한다. 전체 필터 정확성, 시간상관 인과효과, 성능 채택 PASS는 판정하지 않았다.

감사 중 코드 수정·필터 재실행·RF 생성은 없었다. 이번 게시 작업은 감사 문서와 검사 증거만 추가한다. 원래 6개 연구 브랜치는 변경하지 않는다. 3단계로 자동 진행하지 않는다.
