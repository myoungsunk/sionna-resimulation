# mbvar-premodel-diag-20261029

범위: 사전 모델 진단·과계수 분석

브랜치: research/mbvar-premodel-diag-20261029

고정 감사 HEAD: `06a8a0922e0f4b2fef79316bcfd77035475c2715`. 게시 직전 원격 ref와 일치. 실행 SHA와 HEAD는 구분한다.

이 문서는 이번 대화에서 확보한 감사 결과의 브랜치별 통합 기록이다. 과거 개별 감사 전문은 전부 확보하지 못했으며 이를 복원하거나 독립 감사로 표현하지 않는다. 공통 정책·범위는 [기준 보고서](../STAGE1_PROVENANCE_KO.md)를 따른다.

## 코드와 실행

[HEAD 코드](https://github.com/myoungsunk/sionna-resimulation/blob/06a8a0922e0f4b2fef79316bcfd77035475c2715/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code/diag_mbvar.py#L19-L88)

Cloud 2026-10-29 02:42–03:01 UTC. 기반 4ad94fe652d847592aa78ba017dd0a6a517652a1. manifest와 commit 설명의 session 귀속만 확보.

실행 SHA 및 고정 코드 링크는 [1단계 기준표](../STAGE1_PROVENANCE_KO.md)를 참조한다. HEAD 코드가 모두 과거 계산에서 실행됐다고 보지 않는다.

## 확인과 판정

저장 코드 두 파일의 해시는 manifest와 일치한다. scratch와 import 두 줄만 다르다는 설명 및 제한된 점수 일치는 전체 실행 동일성 증명이 아니다(G2). 현재 동결 입력에서 D3 유한값 시간축은 연속임을 확인.

판정: 저장 코드·현재 입력 READY_WITH_GAPS; 과거 scratch 전체 실행 연결 BLOCKED.

남은 제한: 원래 scratch snapshot·실행본 해시·로그·실제 import 경로 필요. 과거 실행본을 새로 만들어 대체하지 않음.

[1단계 공백](../STAGE1_GAP_CLOSURE_KO.md) · [2단계 입력·시간 감사](../STAGE2_INPUT_TIME_KO.md) · [증거 JSON](../evidence/provenance.json)

코드 수정·필터 재실행·RF 생성은 수행하지 않았다. 결과의 인과효과·성능 채택 PASS는 승인하지 않았다.
