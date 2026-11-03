# LOCAL-P1-V1-32 자원 확대와 실행 승인 계약

기준 커밋은 `c2d881e947aaf6a7e4b817599968a4dc7e88aff2`이며 별도 worktree와 브랜치에서 작성했다. 기존 LOCAL-P1-V1 계약, V2 receipt, 감사 기록의 원본 파일을 그대로 보존했다. 현재 새 독립 감사는 PENDING이며 RF 실행은 수행하지 않았다.

사용자의 최대 32개 논리 작업자 요청에 따라 917개 신규 pose를 64개 고정 shard로 분할했다. 각 pose는 정확히 한 shard에 속하며 원래 257개 주파수 bin과 독립 Native LoS/Full 계산을 따른다. 동시 작업자는 1·2·4·8·16·32 실측 결과 중 합산 처리량이 가장 큰 값을 선택한다. 처리량이 같으면 작은 작업자 수를 선택한다. 모든 단계의 과학 검사 PASS가 필요하다.

실행 자원은 CPU affinity 0–31과 cgroup 메모리 정확히 144 GiB로 고정했다. 실행 시 실제 affinity와 cgroup 제한을 검사하며 환경 및 벤치마크 receipt에도 같은 자원 제한을 기록한다.

벤치마크는 작업자당 서로 다른 pose 두 개를 계산한다. 단계의 작업자 수를 $n$, 작업자 번호를 $w$, 작업자 내부 순번을 $j$라 하면 pose ID는 `((2*(n-1)+2*w+j)*137+75)%917`이다. $n$은 1·2·4·8·16·32, $w$는 0부터 $n-1$, $j$는 0 또는 1이다. 총 126개 pose가 중복 없이 사전 지정된다.

측정 원본은 기존 계약 SHA `50265967634461b281ec10c7c806d34d5b4d2c0a01ef2911cfd902ad79be2727` 아래에서 계산된다. 벤치마크의 `contract_sha256`은 실제 측정 원본을 유지하고 `production_contract_sha256`에 새 자원 계약을 별도로 연결한다. 수집기는 두 계약의 geometry·population·inputs·RF·runtime·threshold·replay·source code·정밀도 adapter·Python·신규 수집 정책을 동일 fingerprint로 검사한다. 현재 Native 수집기 SHA는 기존과 동일하다.

새 V2 receipt는 기존 12개 pose의 정밀도 산술 증거와 원본 receipt의 SHA를 계승한다. 원래 과학 상태 `HOLD_RF_PARITY`, `science_signoff=false`, `production_authorized=false`를 유지한다. 이번 자원 변경에는 새로운 RF 측정 결과가 포함되지 않는다.

실행 승인은 새 계약·plan·독립 감사·환경·전체 벤치마크의 실제 SHA와 연결한다. 기존 supervisor, 전역 STOP, 작업자 동시성 제한, 검증된 checkpoint 재개, 시도별 partial 보존을 사용한다. 과학 검사 실패는 후속 pose 예약을 중단한다.

`INDEPENDENT_P0_AUDIT_PENDING.json`은 감사 요청 상태를 명시한다. 별도 감사자의 결과를 확보한 뒤 plan의 감사 첨부를 갱신한다. 감사 첨부를 제외한 production spec SHA는 고정된다.
