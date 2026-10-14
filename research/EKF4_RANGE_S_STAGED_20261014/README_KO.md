# EKF4 Range–s: 최신 상태

## P2 재개 및 한 번의 R2 해결 trial 후 STOP

**P2 R1 재개는 6.0초에서 수치 중단. D2 진단을 바탕으로 R2 solver를 구현했고, 기존 P0/P1/R1은 통과했다. 새 R2는 9/10 검사 통과 후 특정 내부 진단 로그 필드를 가정한 KeyError로 전체 gate FAIL. R2 전체 P2는 실행하지 않고 멈췄다.**

중요: R2의 해당 고정 입력은 수렴·gradient·목적함수·공분산 검사를 지난 후 진단 메타데이터 검사에서 실패했다. 이를 solver가 다시 미수렴한 것으로 해석하지 않는다. 반대로 전체 회귀가 PASS라고 표현하지 않는다.

- [최종 진행 흐름과 확정/미확정 보고서](P2_RESUME_FINAL_KO.md)
- [기계 판독 중단 상태](P2_RESUME_STOP.json)
- [새 R2 회귀 원시 로그](evidence/R2_TESTS.log)
- [R2 문제 해결 가설·범위](R2_PLAN_KO.md)
- [D2 고정 입력 진단 계획](D2_PLAN_KO.md)
- [새 6.0초 실패 스냅샷](RESUME_FAILURE_SNAPSHOT.json)
- [원래 P2 조건](P2_SPEC.json)

실행된 R2 코드는 연구 브랜치의 **미채택 후보**다. main 병합·배포는 하지 않았다. scientific_PASS=false, bias 효과 미평가, 실제 RF P3–P6 미실행.

## 클라우드 실행

| 범위 | 소스 commit | Run |
|---|---|---|
| R1 이후 P2 재개 | e4084b58e544 | [38518908286](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38518908286) |
| D2 원인 진단 | ae2c60c2f3a9 | [38519216213](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38519216213) |
| R2 회귀·P2 trial | 408020395928 | [38519821321](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38519821321) |

현재 보고서 commit은 문서/증빙만 갱신한다. 새 자동 실행을 시작하지 않으며 R2 테스트 수정·재실행은 이번 범위에서 하지 않았다.

## 이전 기록 보존

[원래 전체 이력 README(9485133c233e)](https://github.com/myoungsunk/sionna-resimulation/blob/9485133c233ec809ea11d92bf4be64d41e53e9f0/research/EKF4_RANGE_S_STAGED_20261014/README_KO.md)

[최초 P0/P1](P0_P1_CLOUD_RESULT_KO.md), [D1](D1_RESULT_SUMMARY.json), [R1 결정](SOLVER_R1_DECISION_KO.md), [R1 실행 결과](SOLVER_R1_RESULT_KO.md), [원 사전등록](PLAN_KO.md)은 변경하지 않았다.
