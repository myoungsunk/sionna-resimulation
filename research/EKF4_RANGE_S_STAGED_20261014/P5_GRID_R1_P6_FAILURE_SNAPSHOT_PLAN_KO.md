# P5 격자 TV 진단·수정 및 P6 실패 스냅샷 보존 사전등록 — 2026-10-14

## P5 확인된 코드 문제
첫 GitHub-hosted [38537305223](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38537305223)에서 `P5.status=NUMERICAL_LIMIT_FIXED_POSITION`: TV(720→1440)≈0.040/0.016, TV(1440→2880)≈0.020/0.008. 기존 비교 코드는 인접 2개 fine mass `p[2i]+p[2i+1]`을 coarse mass `P_i`와 비교했다. 그러나 coarse grid node와 fine grid node가 원점 `-π`에 함께 놓인 periodic *grid-node midpoint* 규약이므로 coarse cell 경계는 coarse node ±Δ/2다. fine grid는 해당 경계를 가로지르므로 `p[2i]+p[2i+1]`은 coarse 셀을 반 칸 이동시킨 비교이다. 따라서 이 TV를 수치 비수렴의 증거로 사용하면 안 된다.

## 수정 가설
정렬된 periodic fine-grid 확률질량 재격자화:
`m_coarse(i) ≈ p_fine[2i] + 0.5*(p_fine[2i-1]+p_fine[2i+1])`.
이 식은 fine 셀의 half-overlap을 포함하며 전체 확률질량을 보존한다. 좁은 Gaussian에 대해 offset을 없애면 수치 차이가 감소할 것이다. 실제 posterior의 분포/likelihood/grid/임계값/원본 RF 데이터는 변경하지 않는다. 이 formula는 smooth interpolation의 이산화 근사이지 position-integrated G3 reference가 아니다. 원 `NUMERICAL_LIMIT_FIXED_POSITION`는 이전 실행 결과로 보존하고 새 run에서 검증한다.

## P6 별도 문제
첫 P6에서는 `EKF3+EKF4`가 14채널×2=28/28 전체 재귀 완료했으나, `MAP4`는 14 중 2개만 전체 완료. 12개는 `LINE_SEARCH_FAILED`이며 그 상태에서 estimator 출력을 가짜로 채우지 않았다. 최초 실패 원인을 확인하기 위해 **모든 MAP4 실패 시의 정확한 prior_x, prior_P, z_r, z_s, frozen R0, model forward h/H, iteration/acceptance history**를 증빙에 포함한다. 수식·gradient_tol=1e-8·최대반복=80·gate/R0·관측·source data는 그대로 둔다. 기록 추가만으로 MAP4가 수렴했다고 주장하지 않는다.

## 단계별 감사
모든 재실행 전에 기존 `rf_stage_audit.py`의 source/input SHA, frozen P0/LUT/14 trace 검사. P3/P4는 같은 자료·모델·수식으로 얻은 기존 결과를 재사용하고, 실제 변경부 P5 TV와 P6 failure evidence만 집중 검증한다. `P5` 재격자화 수치 이슈는 해당 P5 **검사 유효성**에만 영향을 미치며 P6 baseline을 무효화하지 않는다.
