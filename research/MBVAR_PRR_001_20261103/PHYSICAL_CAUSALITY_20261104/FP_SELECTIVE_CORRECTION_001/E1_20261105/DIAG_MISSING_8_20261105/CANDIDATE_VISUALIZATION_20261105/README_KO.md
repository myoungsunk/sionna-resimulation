# 기존·제안 후보 및 채널별 지지 비교

2026-11-05. 이미 확인한 누락 8건에 한정한 진단 시각화. 운영 후보 생성 코드 변경, 전체 corpus 재검증, 선택기 실행 및 E2 실행은 없다. 기존 E1 실패 판정은 유지한다. 기반 commit: 7707db1d69bc60b2c7cba591bac2508b611c64c9.

## 실제 CIR 위 기존·제안 후보 비교

- [4건 비교 1](proposed_overlay/CIR_candidate_comparison_1.png), [4건 비교 2](proposed_overlay/CIR_candidate_comparison_2.png), [전체 PDF](proposed_overlay/CIR_candidate_comparison_8.pdf)
- [후보 위치·수 및 A/B별 검산 기록](proposed_overlay/OVERLAY_CHECK.json)

검은 원은 기존 후보, 초록 삼각형은 제안 A+B에서 추가된 후보, 빨간 점선은 참조 tap이다. 이 첫 비교 그림은 TWO_PORT_UNION 후보 위치를 양쪽 파형에 동일하게 표시한다. 양쪽 RX가 각각 지지한다는 뜻이 아니다. 실제 지지 채널과 제외 이유는 다음 분리 그림이 기준이다.

## RX0·RX1 분리: 실제 채널별 지지와 제외 이유

- [전체 8건 PDF](channel_support/RX_separated_all_8.pdf)
- [R2·974](channel_support/R2_974_RX_separated.png)
- [R4·729](channel_support/R4_729_RX_separated.png)
- [R5·506](channel_support/R5_506_RX_separated.png)
- [R5·507](channel_support/R5_507_RX_separated.png)
- [R5·510](channel_support/R5_510_RX_separated.png)
- [R5·978](channel_support/R5_978_RX_separated.png)
- [R5·979](channel_support/R5_979_RX_separated.png)
- [R5·980](channel_support/R5_980_RX_separated.png)
- [채널별 후보·봉우리 및 검산 기록](channel_support/CHANNEL_SUPPORT_CHECK.json)

각 패널은 해당 채널이 실제로 지지하는 후보만 표시한다. raw fallback은 봉우리 지지와 구별하여 채널에 귀속시키지 않았다. 전체 후보는 검은 원과 초록 삼각형의 합이다. 참조 주변을 확대했으므로 좌우 그림 경계는 신호 종료가 아니다.

후보가 끊기는 원인: 기존은 에지±1 및 골짜기~봉우리 범위 제한; 제안은 봉우리까지 확장하되 이후 하강/평탄부 제외; 시작 전 tap은 에지-1보다 앞이거나 15% 진폭 조건 미달; 별도 봉우리는 돌출도/왼쪽 상승 지지 조건 또는 30% 선행 에지 분리 조건에서 탈락한다. 화살표는 보이는 주요 봉우리와 시작/종료 위치에 이유를 표시한다. 모든 봉우리 기록은 JSON에 보존했다.

## 확인 결과와 한계

A는 기존 후보를 유지하며 30% 에지부터 봉우리까지 조건을 만족하는 tap을 추가한다. B는 기존 조건에 탈락한 봉우리 중 왼쪽 상승 지지가 충분한 것을 추가 허용한다. 정확한 규칙은 [기존 제안서](../evidence/CANDIDATE_REVISION_PROPOSAL_KO.md)를 따른다.

|사례|참조 포함에 충분한 변경|기존 → A+B 전체 후보 수|
|---|---|---|
|R2·974|B|12 → 40|
|R4·729|A 또는 B|16 → 33|
|R5·506|A|14 → 32|
|R5·507|A|14 → 30|
|R5·510|B|8 → 18|
|R5·978|B|17 → 39|
|R5·979|A|16 → 31|
|R5·980|A|21 → 41|

8건 모두 A+B의 supported/usable 후보에 참조가 포함되고 64개 상한을 넘지 않았다. 원본 H 입력 해시를 기존 잠금과 대조했다. 직접 역 DFT로 CIR을 계산하고 기존 채널별 후보/에지를 기존 로그와 정확 대조했다. 채널별 지지를 합치고 raw fallback을 더한 집합이 기존 비교 그림의 전체 후보 집합과 일치함을 검산했다. SELF_REVIEW이며 독립 감사가 아니다.

이는 이미 관찰한 8건의 진단 계산이다. 전체 데이터 성능·미지 환경 일반화·선택 정확도·거리 오차 개선을 입증하지 않는다. E2_started=false.

## 재현 및 파일 무결성

plot_proposed_overlay.py와 plot_channel_support.py는 당시 로컬에서 실행한 원본 스크립트다. 원래 작업 루트 아래 diagnosis8/와 repo/가 나란히 존재하고, diagnosis8/ 아래 기존 DIAGNOSIS.json 및 SOURCE_LOBES.json이 있는 구조를 가정한다. GitHub 보존 위치에서 바로 실행하는 용도가 아니다. 재현은 별도 scratch 작업 루트에 그 구조와 잠금 입력을 준비해야 한다. 기존 증거 위에 덮어쓰지 않는다.

MANIFEST_SHA256.json은 이 신규 패키지 파일의 바이트 해시를 기록한다. 상위 기존 패키지와 manifest는 수정하지 않았다.
