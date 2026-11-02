# 독립 감사 — DLP-LUT-BB-MB-MATCHED-001

판정: ACCEPT. 감사 actor는 /root/independent_audit이며 구현자와 별도 하위 에이전트이다.

거리 LUT 24 trace와 보존 SourceFFD 24 trace의 Heading·XY·NEES·coverage를 원자료에서 독립 재집계했다. 총 2144개 검사를 통과했다. 추가 필터 재생은 수행하지 않았다.

동결 계약/237개 입력 해시, 출력 manifest, 이전 MB12 trace의 X/P/R/used/J 완전 일치, 원 donor/관측/초기화, 직전 posterior 거리 분산, 동역학과 과정공분산, innovation·gain·NIS·self gate·Joseph 갱신, 양의 정부호와 최초 divergence를 확인했다. 전체 packet 수치미분 기록이 동결 기준을 통과했으며 수치미분 검사는 코드를 별도로 검토했다.

새 LUT 개선/악화 집계: {"head_rmse": {"improved": 11, "worsened": 1, "tied": 0}, "xy_rmse_cm": {"improved": 8, "worsened": 4, "tied": 0}}. Source 참조 집계: {"head_rmse": {"improved": 12, "worsened": 0, "tied": 0}, "xy_rmse_cm": {"improved": 8, "worsened": 4, "tied": 0}}.

발견한 coverage 정의 차이는 해소됐다. 보존 역사 기준(1.96/5.991)은 유지하고 정확한 계약 χ² coverage를 별도 ledger에 제공했으며 독립 재계산과 일치한다. 필터나 동결 계약은 변경되지 않았다.

과학 결과: MIXED. 한 환경·한 RF realization·동일 seed의 결합 개입 비교에만 수용한다. 작은 NEES를 일관성 입증으로 보지 않는다. 성능 차이를 평균/분산/gate의 순수 기여율로 분해할 수 없고 실측 전이·일반 성능 우위를 주장할 수 없다. 모델/원고 채택은 수행하지 않았다.

실행 자체의 Source 상태 재현은 보존 trace와 구현자 실행의 동결 parity ledger를 확인했으며 독립적인 두 번째 필터 구현/재실행은 하지 않았다. 감사 코드와 세부 검사는 INDEPENDENT_AUDIT.json 및 independent_audit.py에 기록했다.
