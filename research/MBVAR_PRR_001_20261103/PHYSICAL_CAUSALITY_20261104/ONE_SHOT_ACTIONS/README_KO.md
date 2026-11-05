# PR36 4-runner 실행 준비

이 변경은 실행 준비 요청을 반영한다. push는 원본 SHA·재사용·키 분할 검증만 수행하며 Native RT는 호출하지 않는다. 4개 runner × 각 4개 worker는 총 16개 논리 CPU에 제한한다. 공개 ubuntu-24.04 runner, 컨테이너별 CPU 4·RAM 12 GiB, 내부 스레드 각 1개다.

기존 단일 서버 세션 조건을 단일 workflow의 canary gate → 4개 shard → 통합 인계로 바꾼다. B0 4키는 기존 raw를 전수 검증하고, 원래 요청서대로 새 실행 환경에서 R4 pose 194·234 Full/LoS canary 1,028회를 먼저 수행한다. canary PASS 후에만 4개 본 계산 shard를 시작한다. 기존 B0 raw는 덮어쓰지 않는다. 이후 모든 신규 키도 원본 Full/LoS archive와 비교한다. 새로운 호스트에서의 solver 동등성은 실제 계산 전에는 미검증이다.

PR35 G2 4개는 prerequisite이며 신규 큐에 없다. G3 20개 완료 raw와 GO/code/condition binding은 기존 SHA로 고정했다. 전체 400키 중 92개를 재사용하고 원래 복도 308개 키를 Full/LoS 균형을 맞춰 77개씩 배분한다. 각 shard 19,789회, 합계 79,156회다. canary 1,028회와 본 계산 79,156회를 합한 실행 상한은 80,184회다.

수치 기준은 원래 LoS 상대 L2 1e−5, Full 1e−3, producer 순서의 ray 재합성 상대 L2 및 최대 정규화 오차 1e−8, 직접파 지연 1e−12초, 원본 FP tap 일치다. NumPy 1.26.4를 포함한 기존 버전을 고정한다. 입력과 재사용 raw는 INPUT_RELEASE.json의 영구 release에서 가져오며 ASSETS.json의 모든 part SHA 및 source 파일 SHA를 검사한다.

등록된 단일 실행의 4-worker 묶음만 처리한다. 실패 즉시 로컬 STOP을 만들고 다른 runner에 release marker를 게시한다. 다른 runner는 10초마다 확인하며 네트워크 요청은 최대 20초다. 진행 중 호출은 raw를 저장한 뒤 다음 호출을 막는다. 네트워크 확인 실패도 로컬 중단이다. 분산 환경의 실패 전달은 즉시 동시 중단을 보장하지 않는다. 재시도는 0회다.

RT 예측 60~90분은 runner 실측 전 추정이다. 보수적인 준비 상한은 PREPARED_BUDGET.json에 기록했다. 준비·전수 검증을 각 runner에서 반복하므로 파일시스템과 네트워크 비용이 영향을 준다. 실제 runner 벤치마크 없이 1시간 완료를 보장하지 않는다.

실행은 workflow_dispatch의 execute=true 및 APPROVE_PR36_80184_16_WORKERS가 모두 필요하다. 이 preparation은 dispatch하지 않는다. GitHub가 기본 브랜치에 workflow가 있어야 dispatch를 노출하는 경우 병합 또는 별도 명시적 실행 진입 절차가 필요하다.

원본은 실패해도 각 shard의 draft release에 보존하고 최종 400키 상태를 작성한다. 성공 시 전체 신규·재사용 raw와 입력을 handoff.tar.gz로 묶고 GitHub Release에서 재다운로드해 SHA를 확인한 뒤 공개 완료 상태로 바꾼다. Actions artifact는 보조 복사본이다. 진행 중 강제 job 취소나 runner 자체 소실은 업로드 전 파일 손실 위험이 있어 자동 fail-fast 취소는 사용하지 않는다.

판정은 사용자 승인 기반 비독립 탐색 수집이다. 계산 중 과학적 결과에 따라 새 pose나 yaw를 추가하지 않는다. EKF·논문 채택은 이 workflow의 완료 기준에 포함하지 않는다.
