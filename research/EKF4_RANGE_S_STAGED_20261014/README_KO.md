# 최신 후속 — Solver R1 한정 수정·실패 회귀검증 (2026-10-14)

**상태: P0 16 PASS / P1 8 PASS / R1 실패 사례 5 PASS, scientific_PASS=false.**
원래 P2의 첫 MAP3 `LINE_SEARCH_FAILED` 입력을 수정된 solver로 검증하여, 동결 gradient 기준 `1e-8`에서 `CONVERGED`를 확인했다. 원 기록은 수정하지 않았다.

- [목적함수 감사·solver 결정](SOLVER_R1_DECISION_KO.md)
- [실행 결과·한계](SOLVER_R1_RESULT_KO.md)
- [클라우드 감사 영수증](SOLVER_R1_CLOUD_RECEIPT.json)
- [GitHub Actions Run 38517841360](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38517841360)
- [원시 cloud evidence ZIP](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38517841360/artifacts/11873035416)

**중요:** R1은 수치 구현 결함의 국소 회귀검증으로, P2 전체/실 RF P3–P6/독립 검증은 **NOT_RUN**이다. 아래는 과거 P2 중단 및 D1 원인 진단 당시의 동결 이력으로 남긴다. 새 solver는 P2를 재개하지 않았다.

---

# EKF4 Range–s 단계별 구현 및 클라우드 실행 현황

## 현재 결론

4-state 운동·관측 수학과 국소 MAP solver를 구현해 GitHub Actions에서 검증했다. P0 16개, P1 8개 테스트를 통과했다. P2 재귀 합성 실험은 첫 paired trial의 MAP3에서 수치적 수렴 gate가 실패해 중단됐다. 이어 동일 실패 입력의 고정밀·독립 solver 진단 D1을 클라우드에서 실행해, double 목적함수 비교의 반올림이 유효한 최적화 스텝을 거부한 원인을 확인했다.

**전체 필터 개발·RF 성능 검증이 완료된 것은 아니다. P2의 bias 개선 가설은 평가하지 못했으며 P3–P6은 미실행이다.** 기존 실패를 성공으로 변경하거나 수렴 기준을 완화하지 않았다. 현재 workflow는 P0/P1 회귀검사 후 D1 진단만 실행하며 P2를 자동 재개하지 않는다.

## 저장소 및 소스

- 원본 기준: `32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20`.
- 브랜치: `research/ekf4-range-s-staged-20261014`.
- 최초 가설·중단기준 사전등록: `1e841933d9eb81b2d1a6ff383c4a8c93ab510fac`.
- 핵심 코드 원본 SHA256: `33d9fa3e3b2dd2de790406d1422e00ca33d7936ec36e277fec2788b693a02e1e`.
- 기존 EKF3/6-state, RF H, LUT, sensor generator, 과거 결과는 수정·삭제·이동하지 않았다. 새 연구 폴더 및 새 workflow만 추가했다.

## 구현 파일

| 파일 | 구현 내용 |
|---|---|
| core.py | 3/4-state 원호 운동, F/G, 전체 P 예측, joint Joseph update, 상관 RF 순차 whitening, bias 조건부 복원, 원 prior 고정 Range-first local MAP |
| test_core.py | 중앙차분, 독립 복소적분, 공분산, 상관 likelihood, 선형 동등성, SciPy 비교, 무잡음·각도경계·미수렴 검사 |
| validate.py | P0→P1 gate와 Git SHA/환경/코드·출력 해시/종료코드 기록 |
| synthetic.py | EKF3/EKF4/MAP3/MAP4 paired 재귀 runner, 원시 입력·상태·P·trial 지표 보존, trial bootstrap |
| P2_SPEC.json | 결과 확인 전 고정한 3경로×2bias×100trial, 60초 조건 및 판정 |
| FAILURE_SNAPSHOT.json | 최초 실패 prior, P, 관측, 종료 iterate 및 원본 artifact 출처 |
| diagnose.py | 동일 입력 재현, 80자리 목적함수·stationary point, 독립 SciPy 비교 |
| D1_PLAN_KO.md | 실패 후 수치 진단의 새 가설·실행 범위 |
| D1_RESULT_SUMMARY.json | 실제 D1 cloud 결과 요약과 원시 artifact 해시 |
| PLAN_KO.md | P0–P6 전체 로드맵, 원본 보호·가설·중단 규칙 |
| .github/workflows/ekf4-range-s-staged.yml | GitHub-hosted Ubuntu, 고정 Python/수치 라이브러리, 실패 증빙 업로드 |

다중 Heading branch 추적, 위치 주변화 기준 적분, 실제 FFD 어댑터, factor-graph smoother는 아직 구현했다고 주장하지 않는다. SyntheticRF는 명시적인 합성 관측함수이며 실제 FFD를 대체하지 않는다.

## 실제 실행 결과

| 실행 | 소스 commit | 결과 |
|---|---|---|
| [최초 P0/P1](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514101901) | a2087b952d958dc6ac932f1c597b57520ed3946f | P0 16 PASS, P1 8 PASS |
| [P2 재귀 합성](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514443823) | 35728c2e954bf9c38a616b376a7ab62533721282 | P0/P1 PASS 후 P2 FAIL_CLOSED |
| [D1 원인 진단](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514766913) | 7a6123e3045c89d3506ace71e26b0774f66ef862 | P0/P1 회귀 PASS, D1 고정 입력 가설 지지 |

P0/P1 대표 수치: F 중앙차분 최대 5.48e-10, G 3.04e-10, 상관 joint/sequential 4.44e-16. 독립 SciPy local MAP과 목적함수 차이 4.66e-15, 상태 차이 6.27e-9. 상세 결과는 P0_P1_CLOUD_RESULT_KO.md 및 각 실행 artifact에 있다. 테스트 성공은 전체 posterior 정확성이나 실제 센서 성능의 검증이 아니다.

## 예상과 달랐던 결과와 원인

예상: P0/P1을 통과한 backtracking local MAP가 정합 합성 재귀 실험에서도 동결된 gradient norm 기준 1e-8까지 수렴한다.
실제: straight / true bias=0 / trial0 / MAP3의 4.5초에서 LINE_SEARCH_FAILED. 남은 gradient norm은 5.2678999634681034e-8. 같은 trial의 EKF3·EKF4만 완료됐고 네 모델의 완전 paired trial은 0개다. 이 부분자료로 모델 순위 또는 bias 효과를 주장하지 않는다.

D1에서 원 실패를 그대로 재현했다. 저장된 마지막 iterate의 한 GN step에 대해:

| 지표 | 결과 |
|---|---:|
| double 비용 변화 | +4.6629367034256575e-15 |
| 80자리 독립 비용 변화 | -1.6056697178966146e-15 |
| step 후 gradient norm | 5.739139719018738e-10 |
| 원래 수렴 기준 | 1e-8 |
| 고정밀 Hessian 최소 고유값 | 1.0094477877098513 |

비용은 실제로 감소하지만 double 계산에서는 증가로 보였다. step을 취하면 원래 수렴 기준 안으로 들어간다. 독립 SciPy solver도 해석/차분 Jacobian 모두 성공했고, 최종 해석 gradient norm은 각각 1.06e-11, 1.14e-9였다.

따라서 이 고정 입력에서는 운동 수식, bias 추가, multipath 가설의 반증이 아니라 **최적점 근처의 유한 정밀도 비용 비교와 수렴 제어 결함**을 확인했다. 다만 한 실패 입력의 진단이 모든 실험에서 동일한 원인이거나 전체 solver 교체가 검증됐음을 뜻하지는 않는다. 순수 GN 무조건 full-step은 진단에만 사용했고 채택하지 않았다.

## 확정 / 미확정

확정: 새 4-state 기본식 구현, 지정 P0/P1 검사 통과, 클라우드 실행·원시 실패 보존, 최초 수렴 중단의 반올림 메커니즘에 대한 고정 입력 증거.
미확정: 새 구현의 gyro bias 개선 효과, 정상조건 정확도 손실, RF LoS/Full 성능, 위치 적분·다봉 posterior, 전체 재귀 일관성·일반화.

## 다음 방향: 확인 전 보류

다음 후보는 동일 목적함수와 **gradient 1e-8 기준을 유지하는** trust-region 또는 수치적으로 안정적인 step acceptance다. 먼저 실패 snapshot을 영구 회귀검사에 추가하고, 원본 대비 수렴 판정과 단위 테스트를 검증한다. 그 다음 동일 P2_SPEC과 모든 seed를 유지해 전체 실험을 새 run으로 재실행한다. 허용치 완화, R/Q 조정, 실패 trial 삭제, silent fallback은 하지 않는다.

이번에는 D1 가설 실행·진단에서 멈췄다. solver 수정·P2 재실행 방향은 확인 후 별도 commit으로 진행할 수 있도록 분리해 두었다. 자동 실행이나 배경 모니터링을 약속하는 문서가 아니다.

## 증빙

- [P0/P1 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514101901/artifacts/11871250751), ZIP SHA256 `331307d4c3adb3f145c439486d9431587b00f6c6e47241df60d01213347fdde8`.
- [최초 실패 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514443823/artifacts/11870794926), ZIP SHA256 `9a6e6b4def5c46881ba5fe0f54a6d5d9cbe211a957374dbef56e6d3e67a8d5e9`.
- [D1 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514766913/artifacts/11871162296), ZIP SHA256 `85c96b0a0168d21847ce0af2f423605d62e9834fa8d10208ccf6293a532c4d15`.
- D1_RESULT.json SHA256 `6ef4ae9c5a814e7485d7ba43adf5ba788d7c54ac0a25e82a5d4d9654d1e00e83`.
- Artifact 보존기간 30일. 내려받은 archive의 checksum과 P0/P1·P2 출력 manifest를 읽기 전용 검산했다. 로컬에서는 원 실험을 실행하지 않았다.

최종 상태: `P0=PASS, P1=PASS, P2=INCOMPLETE_BLOCKED, D1=SUPPORTED_AT_FIXED_INPUT, P3-P6=NOT_RUN, scientific_PASS=false`.
