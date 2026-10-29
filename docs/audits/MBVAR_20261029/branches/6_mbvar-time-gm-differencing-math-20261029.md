# mbvar-time-gm-differencing-math-20261029

범위: 시간 GM 및 differencing 수학 진단

브랜치: research/mbvar-time-gm-differencing-math-20261029

고정 감사 HEAD: `cf4b19ab02ea93c254b606a27128960f24880598`. 게시 직전 원격 ref와 일치. 실행 SHA와 HEAD는 구분한다.

이 문서는 이번 대화에서 확보한 감사 결과의 브랜치별 통합 기록이다. 과거 개별 감사 전문은 전부 확보하지 못했으며 이를 복원하거나 독립 감사로 표현하지 않는다. 공통 정책·범위는 [기준 보고서](../STAGE1_PROVENANCE_KO.md)를 따른다.

## 코드와 실행

[HEAD 코드](https://github.com/myoungsunk/sionna-resimulation/blob/cf4b19ab02ea93c254b606a27128960f24880598/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_time_gm_20261029/time_gm_study.py#L32-L85)

40828341230 @ 7fab61cb1b26240b8031b77e277bc6ab92651245; artifact 12877941768.

실행 SHA 및 고정 코드 링크는 [1단계 기준표](../STAGE1_PROVENANCE_KO.md)를 참조한다. HEAD 코드가 모두 과거 계산에서 실행됐다고 보지 않는다.

## 확인과 판정

원래 인덱스 및 실제 시간 차이 검사 경로를 확인. ZIP·9개 내부 파일·7개 CSV·entrypoint hash 연결 확인(G6 CLOSED). TRAIN/HELD 쌍 수와 원래 시간축 경로가 부합한다. differencing은 manifest상 analytic validation이며 measurement-differencing EKF 실행으로 표현하지 않음.

판정: 출력 provenance READY; 원래 시간 인덱스 경로 제한적 ACCEPT; 전체 READY_WITH_GAPS.

남은 제한: 과거 input bytes, Rbase/colored state 분리·AR1 근사·한 복도 및 route A/B 상관·최종 독립 test 부재 등의 기존 한계 유지. 성능 채택 승인 없음.

[1단계 공백](../STAGE1_GAP_CLOSURE_KO.md) · [2단계 입력·시간 감사](../STAGE2_INPUT_TIME_KO.md) · [증거 JSON](../evidence/provenance.json)

코드 수정·필터 재실행·RF 생성은 수행하지 않았다. 결과의 인과효과·성능 채택 PASS는 승인하지 않았다.
