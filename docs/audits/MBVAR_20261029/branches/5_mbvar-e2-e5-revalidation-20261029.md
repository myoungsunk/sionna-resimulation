# mbvar-e2-e5-revalidation-20261029

범위: E2/E5 재검증 및 초기상태 교차

브랜치: research/mbvar-e2-e5-revalidation-20261029

고정 감사 HEAD: `af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3`. 게시 직전 원격 ref와 일치. 실행 SHA와 HEAD는 구분한다.

이 문서는 이번 대화에서 확보한 감사 결과의 브랜치별 통합 기록이다. 과거 개별 감사 전문은 전부 확보하지 못했으며 이를 복원하거나 독립 감사로 표현하지 않는다. 공통 정책·범위는 [기준 보고서](../STAGE1_PROVENANCE_KO.md)를 따른다.

## 코드와 실행

[HEAD 코드](https://github.com/myoungsunk/sionna-resimulation/blob/af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_e2_e5_revalidation_20261029/revalidate.py#L20-L45)

계산 40830330560 @ aa1027b7ab44078a797bf26556879a99cb8de3d8; 복구 집계 40831583667 @ 419c18303aa29bacdeef724e1c67f07e7e5322a3; 초기상태 교차 40830802359 @ fe5d3edf4969c53862308ab8dace4d58601d111d.

실행 SHA 및 고정 코드 링크는 [1단계 기준표](../STAGE1_PROVENANCE_KO.md)를 참조한다. HEAD 코드가 모두 과거 계산에서 실행됐다고 보지 않는다.

## 확인과 판정

저장 code snapshot의 확인 파일 동일성을 재사용하되 계산과 복구 집계를 분리한다. 현재 S_all 유한 시간축은 선택 ACF 압축 문제로 자동 무효화하지 않는다. FULL_JAC/FROZEN 보완 경로와 후속 corrective 증거를 기존 E2 문제의 수정/재검증 기록과 구분한다.

판정: 현재 입력·시간 경로 제한적 ACCEPT / READY_WITH_GAPS. 전체 필터/Jacobian 수학 PASS는 판정하지 않음.

남은 제한: 과거 입력 artifact 12877504527 실제 bytes 미재해시. 전체 wrapper·수학 정확성은 이번 2단계 범위 밖.

[1단계 공백](../STAGE1_GAP_CLOSURE_KO.md) · [2단계 입력·시간 감사](../STAGE2_INPUT_TIME_KO.md) · [증거 JSON](../evidence/provenance.json)

코드 수정·필터 재실행·RF 생성은 수행하지 않았다. 결과의 인과효과·성능 채택 PASS는 승인하지 않았다.
