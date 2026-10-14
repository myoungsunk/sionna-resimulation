# PRE-RUN D0: 최초 감사 HOLD와 최소 수정

실제 GitHub-hosted [run 38526067163](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526067163)에서 테스트/진단/P2는 **0회 실행**. 최초 정적 사전감사가 `HOLD`를 반환한 이유:

1. `synthetic.py`의 실제 동결 SHA256은 `c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643`이며 변경되지 않았다. 제가 새 `pre_run_audit.py`, `p2_v2.py`, V2 계약·51개 대응표에 기록한 문자열에는 중간 `53f55f5`가 누락됐다. **소스 파일 자체는 정상이며 감사/설정 코드만 잘못되었다.**
2. `test_solver_regression.py`의 `first['gradient_integral_difference']`는 `step_acceptance` branch 확인 내부에 있었음에도 좁은 AST 감사가 무조건 존재해야 하는 잘못된 검사로 오인했다. 해당 값은 선택적 진단 필드이므로 테스트에서 `.get`과 기본값을 사용하도록 명시했다. **수렴 검사는 원래 gradient 조건 그대로**이다.

결정: 이 실패는 `DIAGNOSTIC_AUDIT_IMPLEMENTATION_DEFECT`로 분류하며 P2 알고리즘·bias 물리 가설에 대한 반증이 아니다. 기존 runner의 실패는 원본 artifact로 보존했다. P2_SPEC, synthetic.py, Q/R 및 core 수치 코드는 변경하지 않았다. 수정 뒤 정확한 동일 P2 조건에서 static audit → P0/P1 → R1/R2 → representative P2 순으로 **새 run**을 수행할 수 있다. 이전 run을 성공으로 소급하지 않는다.

원본 artifact: [ZIP](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526067163/artifacts/11875821615) (SHA256 `a8f6d37733d74b18cb5f83dfbaa767eea669583cf4a3219204700b7a1cf23cc7`).
