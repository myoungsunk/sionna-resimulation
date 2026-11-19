# Corridor 원거리 Kriging A/B 실행 패키지 (2026-11-19)

## 현재 상태
- **후속 전 거리 POWER 시험 완료:** 같은 조건의 별도 시험에서 pooled XY/Heading RMSE가 두 조건 모두 20/20 seed에서 악화했다. [전 거리 POWER 결과·검사](../power_all_ab_20261119/execution_20261119/RESULT_KO.md).
- **사용자 승인 전체 탐색 실행 완료:** 기준선 미통과를 유지하고 B0/L2 seed 30–49 전체 40조합을 실행했다. R4/R5 일부 개선, R2 악화, pooled RMSE 개선 근거 없음. [전체 결과·검사·실행 근거](authorized_exploration_20261119/RESULT_KO.md).
- **이전 재현 원인 조사·수정 재검증 (2026-11-19):** Kriging 150번째 이웃 경계의 수치 불안정성을 확인하고 결정적 동률 처리 수정 후보를 검증했다. 두 환경 간 X/P/R/mask는 일치하지만, 수정 후보도 과거 동결 기준선 `1e-8` 게이트에 실패해 전체 A/B는 실행하지 않았다. [재검증 결과·한계](revalidation_20261119/RESULT_KO.md).
- **STOP_BASELINE_PARITY_FAIL (2026-11-19)**: Snowball에서 smoke 재생을 실행했으나 기존 F2SKRWV Heading RMSE 오차 `1.1128e-5°`가 동결 허용치 `1e-8`을 초과했다. 계약에 따라 전체 A/B와 집계는 실행하지 않았다. [실행 결과와 검증 근거](execution_20261119/RESULT_KO.md).
- 실제 A/B 수치는 위 승인 탐색 결과에 기록했다. 과거 동결 기준선 재현과 독립 확인은 미통과·미실시 상태이며 과학적 채택으로 해석하지 않는다.
- 비교: frozen `F2SKRWV` vs `F2SKRWV_FAR_K`; 주 변경은 **6–10 m 편파 평균 `mu_s`** POWER → 동일한 sweep Kriging (`e_s|2`).
- 변경 없는 요소: 근·중거리 Kriging, 거리 평균·분산, F2 `c1,c0`(V 표), GM 상태, KI, gyro Q, NIS, seed/route.
- 사전 계약: [PLAN_KO.md](PLAN_KO.md).

## Snowball의 기존 M8 작업 공간에서 재생

현재 원본 자산 경로가 유지된 환경에서 실행:

```bash
# (권장) 실행 전 현재 코드/입력 계약 대조
python research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8/far_kriging_ab_20261119/run_far_kriging_ab.py smoke

# 기존 Phase B 30–49 seed, B0/L2 각각 20개 재귀 실행
python research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8/far_kriging_ab_20261119/run_far_kriging_ab.py explore

# 40개 결과가 모두 존재해야 집계
python research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8/far_kriging_ab_20261119/aggregate_far_kriging_ab.py
```

1. 데이터 전제: `/home/claude/m8/inputs_ext/{B0,L2_GYRO_ARW}/seed30..49/` 와 원본 `m8cal/SWEEP_CAL_B.npz`, `SWEEP_FEATURES.csv.gz`, `KRIGE_PARAMS.json`, `SWEEP_TABLE_V.json`.
2. **중단 조건**: freeze `POINT_B.csv` 기준 `H2,H2S,F2SKRWV` 5개 절대 수치 × 4 그룹의 재생 최대 오차 >1e-8; 누락/잘못된 데이터/상태; 원본 R/Q와 비교 불가.
3. 결과 위치: `/home/claude/m8/far_kriging_ab_20261119/explore/`, `.../summary/`.
4. 출력: `FAR_AB_POINTS.csv`, `FAR_AB_DECISIONS.csv`, `FAR_AB_PAIRED.csv`, `SUMMARY.json`. 근거를 보존하고 실행 후 별도 결과로 GitHub에 업로드할 수 있도록 설계. **위 일반 게이트 경로의 출력은 생성하지 않았다. 사용자 승인 탐색의 별도 결과는 `authorized_exploration_20261119/`에 있다.**

## 이미 확보된 정적 근거(이번 실행 결과가 아님)
기존 station 제외 교차검증에서 원거리 `e_s|2` Kriging MSE `0.010570`, 거리-bin 평균만 사용한 기준 `0.027719`(약 62% 낮음). 이것은 **실제 POWER_BIN_JOINT 대비 A/B도 아니고 EKF 성능도 아니다**.

## 해석상의 주의
- 이전 B단계 seed 30–49는 모델 설계에 간접 사용되었다. 새 독립 confirmation이 아니다.
- Kriging의 초모수 `e_s|2`는 이미 이전 검토에 포함됐으므로 새 과학적 가설은 'far mean branch replacement'이다.
- Phase B 기본 G-T2/G-V 봉인은 건드리지 않는다.
- 모델이 바뀌면 자신의 posterior와 선형화 지점이 달라지는 것이 정상이다. **같은 이전 입력을 쓰는지**는 baseline parity 및 입력 동결로 확인한다.
