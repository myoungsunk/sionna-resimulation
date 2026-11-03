# R1·Anchor B Snowball 독립 사전 감사

2026-11-03 KST. 독립 검토자 /root/preaudit가 LOCAL-P1-V1의 P0 계약·수집기·차단 경로를 ACCEPT로 판정했다. 서면 감사 원본은 INDEPENDENT_P0_AUDIT.json, 해시를 결합한 최종 분할 계획은 03_SHARD_PLAN_AND_PREAUDIT.json이다. 기준 커밋은 435e05b2a6c735e8a964f1e701cb94b93db64795이다.

기존 8개와 신규 4개는 수치 정밀도 검증용이다. 신규 4개의 생산 재사용 계보에 대한 과학적 승인이 보류되어, 의뢰서에서 허용한 917개 전량 신규 계산안을 동결했다. 16개 분할은 작업 단위이며 동시 작업자 수는 벤치마크 후 정한다. 원래 HOLD_RF_PARITY는 보존했다.

Snowball KMS 계정으로 Python 3.11.17과 지정한 다섯 패키지 버전, LLVM polarized variant, 단일 스레드, 원본 6개 mesh·재질 및 안테나 뱅크 두 개를 확인했다. 동일 서버의 보존 raw 12개 재검산에서 tap·strong port 불일치는 0건이었다. Linux 회귀검사 11개가 통과했다. 독립 검토자는 raw a·τ에서 주파수별 H 행렬 6,168개를 재구성했다. 최대 절대차는 3.576224061345498e-18이다.

최종 계약과 감사서를 연결한 후 Snowball의 실제 수집기 진입점에서 사용자 승인서 생략 시 종료 코드 2와 USER_PRODUCTION_APPROVAL_REQUIRED를 확인했다. 이번 작업의 신규 Native solver 호출은 0회다. 다음 단계는 1·2·4·8 worker의 실제 처리량·메모리 측정이며 917개 생산 계산, P2, P3은 미실행이다. 2시간 완료 여부는 미확정이다.

Snowball 검증 기록은 /home/KMS/SIONNA_R1B_CH4_LOCAL_20261103/P0_435e05b_v1/ 에 보존했다. 초기 이미지 버전 불일치, 격리 이미지 빌드 중 누락된 libatomic1, KMS의 쓰기 가능한 HOME을 지정하기 전의 캐시 초기화 실패, 후보 갱신 중 감지된 소스 해시 불일치도 해당 경로의 시도별 로그에 남겼다. 최종 Linux 검사와 환경 검사는 동일한 최종 코드와 계약으로 다시 수행했다.
