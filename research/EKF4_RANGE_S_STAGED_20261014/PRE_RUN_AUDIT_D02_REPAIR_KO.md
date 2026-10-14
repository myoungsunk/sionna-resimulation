# PRE-RUN D0.2: 선택적 로그 접근의 누락 위치 보완

[두 번째 사전 감사 run 38526261348](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526261348)는 동결 synthetic checksum 보정 후에도 **HOLD**였다. `test_solver_regression.py`의 핵심 assert에는 이미 선택적 필드 보호를 적용했지만 마지막 `print('R1_TERMINAL',... first['direct_cost_difference'] ...)`에서 여전히 분기 의존 출력값을 무조건 인덱싱했다. 사전 감사는 옳게 이 추가 실제 결함을 검출했다. 같은 오류가 과학적 수렴 판단과 무관한 출력에서 검사 전체를 중단시킬 수 있으므로, 두 로깅 접근도 `.get`으로 바꿨다.

이 run은 여전히 모델/진단/실험 시작 **이전** HOLD로 종료됐다. 기존 연구/수식 데이터는 변경하지 않았다. 자동 정적 감사의 결과를 그 자체로 독립 과학 감사라고 주장하지 않는다. 원시 artifact [ID 11875792050](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526261348/artifacts/11875792050), ZIP SHA256 `cc8f92c670d4022591161a24ae4bdf9bacf68c722d260df5bbf38ed6252a4e33`.
