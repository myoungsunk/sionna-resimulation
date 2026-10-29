# ds-state-info-var-forensics-20261028

범위: 신규 상태·정보·분산 진단

브랜치: research/ds-state-info-var-forensics-20261028

고정 감사 HEAD: `4ad94fe652d847592aa78ba017dd0a6a517652a1`. 게시 직전 원격 ref와 일치. 실행 SHA와 HEAD는 구분한다.

이 문서는 이번 대화에서 확보한 감사 결과의 브랜치별 통합 기록이다. 과거 개별 감사 전문은 전부 확보하지 못했으며 이를 복원하거나 독립 감사로 표현하지 않는다. 공통 정책·범위는 [기준 보고서](../STAGE1_PROVENANCE_KO.md)를 따른다.

## 코드와 실행

[HEAD 코드](https://github.com/myoungsunk/sionna-resimulation/blob/4ad94fe652d847592aa78ba017dd0a6a517652a1/research/DS_MASK_CAUSAL_X1_X2_20261026/ds_state_info_forensics/run_four_priorities.py)

신규 실행 SHA/receipt 미확인. PB 40652679303은 상위 실행만 입증한다.

실행 SHA 및 고정 코드 링크는 [1단계 기준표](../STAGE1_PROVENANCE_KO.md)를 참조한다. HEAD 코드가 모두 과거 계산에서 실행됐다고 보지 않는다.

## 확인과 판정

신규 스크립트가 존재하지만 호출 workflow/명령/receipt와 D3/D4 출력 연결을 확보하지 못했다(G1). 미발견을 미실행으로 단정하지 않는다.

판정: 실행 결과 감사 BLOCKED. 저장 코드 정적 감사 범위만 특정.

남은 제한: 원래 실행 명령·시각·인자·RUN_RECEIPT와 output manifest 필요.

[1단계 공백](../STAGE1_GAP_CLOSURE_KO.md) · [2단계 입력·시간 감사](../STAGE2_INPUT_TIME_KO.md) · [증거 JSON](../evidence/provenance.json)

코드 수정·필터 재실행·RF 생성은 수행하지 않았다. 결과의 인과효과·성능 채택 PASS는 승인하지 않았다.
