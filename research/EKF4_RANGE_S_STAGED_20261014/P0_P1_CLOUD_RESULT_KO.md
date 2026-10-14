# P0/P1 최초 GitHub Actions 실행 결과

- 실행 소스: `a2087b952d958dc6ac932f1c597b57520ed3946f`
- Run: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514101901
- Job: 115688899211, GitHub-hosted Ubuntu 24.04, conclusion=success.
- 실행: 2026-10-14 04:58:03 UTC. Python 3.11.11, NumPy 1.26.4, SciPy 1.13.1, pytest 8.3.5.
- P0: 16 tests PASS, errors/failures/skipped=0.
- P1: 8 tests PASS, errors/failures/skipped=0.

## 수치

| 검사 | 최대 절대 차이 |
|---|---:|
| 독립 복소지수 적분 vs 원호 운동 | 1.1102230246251565e-16 |
| 4-state F vs 중앙차분 | 5.478822950877316e-10 |
| 4-state G vs 중앙차분 | 3.043112428713357e-10 |
| 상관 잡음 포함 선형 공동/순차 비교 | 4.440892098500626e-16 |
| 반복 선형 MAP vs 한 번의 Kalman 갱신 | 4.440892098500626e-16 |
| 합성 RF Jacobian vs 중앙차분 | 4.5766893053134083e-10 |
| 독립 SciPy solver와 MAP 목적함수 | 4.6629367034256575e-15 |
| 독립 SciPy solver와 MAP 상태 | 6.273089492303541e-09 |

추가 통과: bias 조건부 모멘트 복원, bias 분산의 t^2 누적, 3-state 제한, 원본 배열 비변경, 무잡음 정답 불변성, 각도 주기 경계, 비정상 공분산 차단, gate 거부 시 공분산 유지, 미수렴의 명시적 상태 반환.

## 증빙

- Artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514101901/artifacts/11871250751
- ZIP SHA256: `331307d4c3adb3f145c439486d9431587b00f6c6e47241df60d01213347fdde8`
- core.py SHA256: `33d9fa3e3b2dd2de790406d1422e00ca33d7936ec36e277fec2788b693a02e1e`
- P0.log SHA256: `bb2704e5603b69b449e582ca03d0984e631b8709fa2a737db5c6ec9984d3ee38`
- P1.log SHA256: `e87d103794bd174568ca92b59773ae03d377c5d129a7107c44e24e36a03a7d57`

수치 계약·국소 최적화 검증이다. 실제 FFD, 재귀 성능, 큰 초기불확실성, 다봉 적분, 독립 장면 일반화 검증이 아니다. P2–P6은 이 run에서 NOT_RUN, scientific_PASS=false.

Actions가 고정된 Node20 기반 action을 Node24에서 실행했다는 플랫폼 경고가 기록됐다. 두 action과 artifact 업로드는 성공했다. 이 경고를 수학적 가설 실패로 분류하지 않는다.
