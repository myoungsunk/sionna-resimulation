# 전 거리 POWER 편파 평균 A/B 결과

**사용자 승인 탐색 실행 40개 조합과 자기 검사를 완료했다.** 과거 동결 기준선 재현은 계속 미통과이며 독립 확인·모델 채택은 수행하지 않았다.

B0 XY 비율 1.42113 / B0 Heading 비율 1.32013 / L2_GYRO_ARW XY 비율 1.39883 / L2_GYRO_ARW Heading 비율 1.29457. 비율은 각 seed의 POWER/기준 RMSE 중앙값이며 1 미만이 개선이다. 아래 CI와 경로별 결과를 함께 해석한다.

## 개입과 실행

- 기준 F2SKRWV는 0–6 m Kriging / 6 m 이상 POWER. 시험 F2SKRWV_POWER_ALL은 모든 거리에서 동결 POWER `mu_s[i]`를 사용한다.
- 기존 `baseline_packet.muMB`를 그대로 쓰도록 후보의 Kriging 평균 덮어쓰기를 껐다(`mu_s_fn=None`). 거리 평균, c1/c0 V 표, GM·KI·NIS·Q, 입력과 scorer 정의는 그대로다. 분산은 각 모델의 자기 prior 거리에 같은 표를 적용하므로 상태가 달라지면 실제 조회 값은 달라질 수 있다.
- B0/L2_GYRO_ARW 각각 seed30–49 20개, R2/R4/R5. 참조 H2/H2S도 같은 입력으로 재생했다. 새 seed나 독립 환경을 추가하지 않았다.
- 재생 코드 커밋 `48b37b9de34014b0d5364af123fda8bd0181b8e3`. Snowball KMS, 고정 image `sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`, Python3.11.15/NumPy2.4.6, BLAS/OMP 1 thread, 원본·bank 읽기 전용 mount.
- 사용자 지시와 이전 기준선 불일치 계속 승인 범위는 [실행 계약](../PLAN_KO.md)에 기록했다. 기존 허용치 `1e-8`을 변경하지 않았다. 이 시험은 앞선 원거리 시험 결과를 본 후의 탐색이다.

이번 복원 환경에서는 전 거리 POWER의 pooled XY·Heading RMSE가 두 조건 모두 20/20 seed에서 악화했고, 모든 경로·지표의 paired 비율 95% 구간이 1보다 컸다. 기존 0–6 m Kriging을 제거하는 변경은 이 탐색에서 유리하지 않았다.

## Pooled 지표

각 seed의 R2/R4/R5 pooled 지표를 구한 뒤 조건별 20개 seed의 중앙값을 표시한다. 기준 → 전 거리 POWER, coverage 단위 %.

| 조건 | XY RMSE (cm) | Heading RMSE (°) | Pose95 (%) | Heading95 (%) | XY95 (%) | mean NEES3 |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 6.6481 → 9.9332 | 1.0545 → 1.4090 | 93.4949 → 81.3935 | 98.3897 → 86.9260 | 90.5931 → 81.2022 | 2.8696 → 5.6529 |
| L2_GYRO_ARW | 6.7383 → 9.9387 | 1.0925 → 1.4146 | 93.2876 → 81.6167 | 98.3418 → 87.9624 | 90.7844 → 81.4413 | 2.8803 → 5.4524 |

Coverage 상승이나 NEES 감소만으로 일관성 개선을 확정하지 않는다.

## Seed별 paired RMSE 비율

각 seed에서 POWER/기준을 구한 뒤 중앙값을 취했다. 개별 모델 중앙값의 비율과 다를 수 있다. 고정 bootstrap seed 20261119, 10,000회 seed 재표본 95% 구간이다. 독립 환경 반복이나 다중 비교 보정 결과가 아니다.

| 조건 | 경로 | 지표 | 비율 중앙값 | 95% CI | 개선 seed / 20 |
|---|---|---|---:|---:|---:|
| B0 | R2 | XY | 1.16429 | [1.15038, 1.17788] | 0 |
| B0 | R2 | Heading | 1.10290 | [1.08413, 1.13913] | 0 |
| B0 | R4 | XY | 1.97351 | [1.71199, 2.55137] | 0 |
| B0 | R4 | Heading | 1.75628 | [1.44497, 1.92449] | 0 |
| B0 | R5 | XY | 1.46776 | [1.42464, 1.69518] | 0 |
| B0 | R5 | Heading | 1.44478 | [1.28096, 1.69017] | 1 |
| B0 | pooled | XY | 1.42113 | [1.35661, 1.51201] | 0 |
| B0 | pooled | Heading | 1.32013 | [1.21854, 1.40026] | 0 |
| L2_GYRO_ARW | R2 | XY | 1.16124 | [1.14561, 1.17418] | 0 |
| L2_GYRO_ARW | R2 | Heading | 1.09973 | [1.07827, 1.13731] | 0 |
| L2_GYRO_ARW | R4 | XY | 1.91099 | [1.63583, 2.39921] | 0 |
| L2_GYRO_ARW | R4 | Heading | 1.76922 | [1.45057, 1.94167] | 0 |
| L2_GYRO_ARW | R5 | XY | 1.43931 | [1.40333, 1.59758] | 0 |
| L2_GYRO_ARW | R5 | Heading | 1.43056 | [1.23606, 1.55661] | 3 |
| L2_GYRO_ARW | pooled | XY | 1.39883 | [1.32209, 1.46304] | 0 |
| L2_GYRO_ARW | pooled | Heading | 1.29457 | [1.19897, 1.35624] | 0 |

## 거울해와 원래 규칙의 기술적 집계

- B0: 거울해 기준 0/120 passages → POWER 0/120 passages.
- L2_GYRO_ARW: 거울해 기준 0/120 passages → POWER 0/120 passages.

N_I/N_A/N_J는 원래 scorer의 참조 H2/H2S 대비 seed별 규칙이다. 직접 A/B 우월성 검정으로 바꾸지 않았다. 규칙은 N_J≥18 및 거울해 0이며, 결과의 충족 여부는 기술적 수치로만 기록한다.

| 조건 | 참조 | 모델 | N_I | N_A | N_J | 거울해 passages | 규칙 수치 충족 |
|---|---|---|---:|---:|---:|---:|---|
| B0 | H2 | F2SKRWV | 16 | 12 | 9 | 0 | 아니오 |
| B0 | H2 | F2SKRWV_POWER_ALL | 0 | 2 | 0 | 0 | 아니오 |
| B0 | H2S | F2SKRWV | 16 | 20 | 16 | 0 | 아니오 |
| B0 | H2S | F2SKRWV_POWER_ALL | 0 | 3 | 0 | 0 | 아니오 |
| L2_GYRO_ARW | H2 | F2SKRWV | 15 | 11 | 8 | 0 | 아니오 |
| L2_GYRO_ARW | H2 | F2SKRWV_POWER_ALL | 0 | 3 | 0 | 0 | 아니오 |
| L2_GYRO_ARW | H2S | F2SKRWV | 15 | 20 | 15 | 0 | 아니오 |
| L2_GYRO_ARW | H2S | F2SKRWV_POWER_ALL | 0 | 5 | 0 | 0 | 아니오 |

## 검증·기준선 한계

- 과거 동결 기준선: 40/40 조합 실패, scalar 492/2400개 실패. 허용치 1e-8은 유지했다.
- 최대 차이: B0 seed47 R5 F2SKRWV xy_rmse_cm, 동결 7.234476796455346 / 재생 7.2323251069985774, 절대차 0.0021516894567685796.
- 과거 원본 seed30–49 NPZ/trace 및 정확한 생산 환경 부재는 해소되지 않았다. 이전 [재현 진단](../../far_kriging_ab_20261119/revalidation_20261119/RESULT_KO.md)의 한계가 유지된다.
- 앞선 원거리 A/B의 기준 H2/H2S/F2SKRWV 360개 trace와 2880개 상태·공분산·mask·시각·Reff·prior/Pprior 배열이 bit-exact했다. 역사적 기준선 통과를 뜻하지 않는다.
- 후보 120개 route·seed·조건에서 innovation과 원래 native model/GM prior로 실제 사용 평균을 역산했다. 동결 POWER mu_r/mu_s 대비 최대 절대차 8.3266726846886741e-17, 사전 허용치 1e-12 이내였다.
- 후보 c1/c0가 자기 prior 거리의 동결 V 표와 정확히 같았고, 기준 대비 R_ref/gyro_Q/dt/NIS threshold가 같았다. 480개 trace의 모든 숫자 배열이 유한하고 입력 t/pose_id가 일치했다.
- 40개 결과·320개 point·16개 paired 행·2400개 고유 기준선 scalar·480개 trace 완전성 확인. 120개 입력 hash를 앞선 실행과 대조하고, 코드/고정 자산/출력 hash와 실행 시각·명령을 보존했다.
- 재생 4개, 집계 1개, trace 자기 검사 1개 컨테이너가 모두 exit 0으로 종료했다. 원본 데이터와 선행 결과는 보존했다. 독립 감사는 수행하지 않았다.

## 산출물

- [요약 JSON](summary/SUMMARY.json), [전체 point CSV](summary/POWER_AB_POINTS.csv), [paired CSV](summary/POWER_AB_PAIRED.csv), [원래 규칙 집계](summary/POWER_AB_DESCRIPTIVE_RULES.csv).
- [기준선 비교](summary/BASELINE_PARITY.csv), [trace 검사](summary/TRACE_SELF_CHECK.json), [완전성 검사](summary/VALIDATION.json), [실행 영수증](EXECUTION_RECEIPT.json), `RUN_*.json`, 40개 `RESULT.json`, 컨테이너 로그.
- [480개 trace hash 목록](summary/RETAINED_TRACE_MANIFEST.json). 원본 trace는 Snowball `/home/KMS/FAR_KRIGING_AB_20261119_01a1f269/power_all_explore_01/results/{condition}/seed{seed}/traces/`에 보존했다. GitHub에는 수치·검사·hash·로그를 업로드하고 NPZ는 중복 업로드하지 않는다.
- [원본 공용 집계 출력](raw_aggregation/SUMMARY.json)은 보존했다. 게시용 SUMMARY/paired CSV에서는 공용 필드 `far_kriging_median`을 `power_all_median`으로 바꾸었고 수치는 동일하다. [스키마 기록](EXPORT_SCHEMA.json).
- 현재 판정: 전체 사용자 승인 탐색 실행·자기 검사 완료 / 과거 기준선 재현 미통과 / 독립 확인·채택 미실시.
