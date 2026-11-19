# 단·중·장거리 POWER 평균 A/B

전체 40개 조합(B0/L2 × seed30–49), 480개 trace의 재생·집계·자기 검사를 완료했다. 전 거리 POWER는 기존 F2SKRWV보다 pooled XY/Heading RMSE가 두 조건 모두 20/20 seed에서 악화했다. 과거 동결 기준선 재현 미통과는 유지한 사용자 승인 탐색이다.

- [전체 결과: RMSE·coverage·NEES·거울해·판정 규칙](execution_20261119/RESULT_KO.md)
- [실행 계약·개입 및 통제](PLAN_KO.md)
- [실행 영수증과 컨테이너 명령](execution_20261119/EXECUTION_RECEIPT.json)
- [평균 역산·분산 및 기준군 궤적 검사](execution_20261119/summary/TRACE_SELF_CHECK.json)

시험군은 `baseline_packet.muMB`에 이미 들어 있는 동결 POWER 평균을 쓰도록 `mu_s_fn=None`으로 설정한다. 나머지는 원래 replay/scorer를 재사용한다. 기준군은 0–6 m Kriging / 6 m 이상 POWER다. `run_power_all_ab.py run`과 `aggregate`는 원래 복원 작업 공간을 요구한다. 실행 인자·환경·소스 커밋·입력/출력 hash는 영수증과 `RUN_*.json`에 기록했다. `verify_power_traces.py`는 앞선 원거리 시험의 기준군 trace와 대조하며, native model/GM prior와 innovation으로 실제 적용 평균을 역산한다.

독립 감사·새 환경 확인·모델 채택은 수행하지 않았다. 원격 NPZ trace는 보존하고 GitHub에는 수치 결과·자기 검사·로그·hash를 게시했다. 공용 집계기의 후보 중앙값 필드 이름만 게시 단계에서 POWER로 정규화했으며 원본 집계도 함께 보존했다.
