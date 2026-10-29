# mbvar-causal-isolation-20261029

범위: 시간상관 기전 분리용 surrogate/decimation

브랜치: research/mbvar-causal-isolation-20261029

고정 감사 HEAD: `3af005b8491b5668c0989b82bc3cbc990cfcf8b7`. 게시 직전 원격 ref와 일치. 실행 SHA와 HEAD는 구분한다.

이 문서는 이번 대화에서 확보한 감사 결과의 브랜치별 통합 기록이다. 과거 개별 감사 전문은 전부 확보하지 못했으며 이를 복원하거나 독립 감사로 표현하지 않는다. 공통 정책·범위는 [기준 보고서](../STAGE1_PROVENANCE_KO.md)를 따른다.

## 코드와 실행

[HEAD 코드](https://github.com/myoungsunk/sionna-resimulation/blob/3af005b8491b5668c0989b82bc3cbc990cfcf8b7/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_causal_isolation_20261029/causal_isolation.py#L30-L92)

40825807998 @ 4e14448a8af81c3e99cd257f23cb07615ebd8a15; artifact 12876686764.

실행 SHA 및 고정 코드 링크는 [1단계 기준표](../STAGE1_PROVENANCE_KO.md)를 참조한다. HEAD 코드가 모두 과거 계산에서 실행됐다고 보지 않는다.

## 확인과 판정

작은 ZIP bytes·6개 내부 파일·4개 CSV·entrypoint 해시와 manifest 연결을 확인(G6 CLOSED). accepted lag와 geometry 정렬 교란 한계는 기존 보고서에 명시되어 있으며 인과효과 확정으로 확대하지 않음.

판정: 출력 provenance READY; 현재 입력/시간 구조 제한적 ACCEPT; 전체 READY_WITH_GAPS.

남은 제한: 입력 lock이 해당 결과 manifest에 없음. 과거 소비 입력 bytes(G3), 전체 runtime module snapshot(G4)은 미완.

[1단계 공백](../STAGE1_GAP_CLOSURE_KO.md) · [2단계 입력·시간 감사](../STAGE2_INPUT_TIME_KO.md) · [증거 JSON](../evidence/provenance.json)

코드 수정·필터 재실행·RF 생성은 수행하지 않았다. 결과의 인과효과·성능 채택 PASS는 승인하지 않았다.
