# Corridor 원거리 Kriging A/B 실행 패키지 (2026-11-19)

## 현재 상태
- **CODE_IMPLEMENTED / EKF_NOT_EXECUTED**: GitHub에서 읽을 수 있는 수치 결과만으로 새 재귀 EKF의 RMSE·coverage를 추정하지 않는다.
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
4. 출력: `FAR_AB_POINTS.csv`, `FAR_AB_DECISIONS.csv`, `FAR_AB_PAIRED.csv`, `SUMMARY.json`. 근거를 보존하고 실행 후 별도 결과로 GitHub에 업로드할 수 있도록 설계. **현재 이 파일들은 생성되지 않았다.**

## 이미 확보된 정적 근거(이번 실행 결과가 아님)
기존 station 제외 교차검증에서 원거리 `e_s|2` Kriging MSE `0.010570`, 거리-bin 평균만 사용한 기준 `0.027719`(약 62% 낮음). 이것은 **실제 POWER_BIN_JOINT 대비 A/B도 아니고 EKF 성능도 아니다**.

## 해석상의 주의
- 이전 B단계 seed 30–49는 모델 설계에 간접 사용되었다. 새 독립 confirmation이 아니다.
- Kriging의 초모수 `e_s|2`는 이미 이전 검토에 포함됐으므로 새 과학적 가설은 'far mean branch replacement'이다.
- Phase B 기본 G-T2/G-V 봉인은 건드리지 않는다.
- 모델이 바뀌면 자신의 posterior와 선형화 지점이 달라지는 것이 정상이다. **같은 이전 입력을 쓰는지**는 baseline parity 및 입력 동결로 확인한다.
