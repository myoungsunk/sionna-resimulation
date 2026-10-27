# 코드 QA 결과 (2026-10-27)

## 실제 수행한 검사

`python -m compileall -q run.py dsreassess` 구문 검사 통과.

`python -m pytest -q tests` 수행 결과 **8 passed**. 테스트는:

1. 4상태 motion transition에서 상태 Jacobian `F` 및 입력 Jacobian `G`를 중앙차분과 비교.
2. Joint Kalman update와 Joseph covariance, 거절 시 prior/P 그대로 유지, PSD 검산.
3. Range Kalman gain의 접선 투영만 제거하고 편파 gain 및 ψ/b_g range gain은 보존함을 검산.
4. 5상태 residual range bias 관측/Jacobian 및 process noise 반영 검산.
5. Contiguous block-bootstrap 및 route-heldout covariance에서 target route 제외 확인.
6. 상관된 R을 갖는 joint update와 whitened likelihood update의 posterior 동등성 검산.
7. 세 합성 route × B0/L2를 이용해 **1–6단계 전체 코드**의 출력 폴더/기본 stage 함수 실행 성공 확인.
8. Single-anchor **range-only 회전 gauge**가 4상태 window Fisher에서 rank 결손/무한 접선 불확실성으로 재현되는지 확인. 모델 편파 관측 추가 시 gauge stiffness 증가 확인.

테스트 코드 `tests/test_numerics.py`, `tests/test_synthetic_stages.py`.

## 수행하지 않은 검사 / 아직 미확정

- 사용자의 로컬 `execution_33e9849` frozen source/bank/`p2_artifacts` 및 Git LFS NPZ를 이 작성 환경에서 사용할 수 없었다.
- 따라서 **원본 E1 A0/A1 과 1e-10 이내의 실제 상태/공분산/h/H/K/혁신 replay parity, 전체 14 case-bias 재귀 시뮬레이션, 실제 Full RF FP detector vs E1 1e-9 대조, 원본 native CIR 해시 검증**은 실행하지 않았다.
- synthetic 테스트 통과는 실제 RF 성능이나 인과가설을 입증하지 않는다.
- 새 앵커의 RF ray tracing, 실측, GT가 없는 실제 온라인 환경의 성능은 생성/확인하지 않았다.

## 실행 순서에 따른 판정

실제 실행자가 `--step preflight`에서 source SHA/bank/sample/LFS를 확인하고, `--step 1`에서 원본 E1 parity를 통과해야 후속 코드 경로의 재현성을 확보한다. Parity 실패는 **실험 결과를 채택할 수 없는 STOP**이다. 명세에 맞추기 위해 임계값을 임의 상향하거나 기존 source를 덮어써서는 안 된다.
