# mbvar-control-correction-20261029

범위: 대조조건 정정 및 E1–E7 진단

브랜치: research/mbvar-control-correction-20261029

고정 감사 HEAD: `0a0e2237f085fa32683e4ae603cf5ca2372d2130`. 게시 직전 원격 ref와 일치. 실행 SHA와 HEAD는 구분한다.

이 문서는 이번 대화에서 확보한 감사 결과의 브랜치별 통합 기록이다. 과거 개별 감사 전문은 전부 확보하지 못했으며 이를 복원하거나 독립 감사로 표현하지 않는다. 공통 정책·범위는 [기준 보고서](../STAGE1_PROVENANCE_KO.md)를 따른다.

## 코드와 실행

[HEAD 코드](https://github.com/myoungsunk/sionna-resimulation/blob/0a0e2237f085fa32683e4ae603cf5ca2372d2130/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py#L213-L270)

계산 40820579727 @ 3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18. HEAD에는 결과·사후 정정·후속 계획이 추가됨.

실행 SHA 및 고정 코드 링크는 [1단계 기준표](../STAGE1_PROVENANCE_KO.md)를 참조한다. HEAD 코드가 모두 과거 계산에서 실행됐다고 보지 않는다.

## 확인과 판정

입력 행·관측 재구성은 제한적 확인. S_base/S_used 선택 ACF는 accepted-event lag이며 초 환산 해석에 S2-F1 REDIRECT. lag cross-correlation의 원래 이웃 검사는 별도. E4 블록은 프로토콜상 개수 기준이므로 실제 지속시간 보장 한계로 기록.

판정: 입력 감사 제한적 ACCEPT / READY_WITH_GAPS. 선택 ACF 물리 시간 해석 REDIRECT.

남은 제한: 과거 input artifact bytes와 noise premise 생성 출처 미확보(G3/G5). 기존 E2 groupby 집계 정정 및 revalidation의 Jacobian 보완을 이미 해결 안 된 동일 오류로 다시 등록하지 않음.

[1단계 공백](../STAGE1_GAP_CLOSURE_KO.md) · [2단계 입력·시간 감사](../STAGE2_INPUT_TIME_KO.md) · [증거 JSON](../evidence/provenance.json)

코드 수정·필터 재실행·RF 생성은 수행하지 않았다. 결과의 인과효과·성능 채택 PASS는 승인하지 않았다.
