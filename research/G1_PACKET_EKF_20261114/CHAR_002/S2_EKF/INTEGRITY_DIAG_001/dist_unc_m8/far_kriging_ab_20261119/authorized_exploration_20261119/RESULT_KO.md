# Corridor 원거리 Kriging 전체 A/B 탐색 결과

사용자의 “우선 그냥 진행하도록 해” 지시에 따라 **기준선 재현 실패를 유지한 채 전체 40개 조합을 실행했다.** 실행과 자기 검사는 완료했지만 원래 기준선 재현·독립 감사·모델 채택은 통과한 것으로 표시하지 않는다.

결과: **pooled XY·Heading RMSE 개선은 확인되지 않았다.** R4 Heading과 R5에서는 개선이 있었으나 R2는 악화했다. 이 복원 환경의 paired 탐색 결과로만 해석한다.

## 실행 범위와 변경

- B0와 L2_GYRO_ARW 각각 seed 30–49 20개, R2/R4/R5. 40개 seed·조건 조합, 480개 trace.
- F2SKRWV: 0–6 m Kriging, 6 m 이상 POWER. FAR: 0–10 m Kriging, 10 m 이상 POWER. 나머지 필터·평가 정의 동일.
- 원래 `krige_online.py` 사용. 결정적 이웃 동률 처리 수정 후보는 적용하지 않았다.
- 과거 `1e-8` 기준선 허용치는 유지했다. 사용자가 진입 중단만 해제했으며 [승인 범위](../AUTHORIZED_EXPLORATION_KO.md)를 기록했다.
- 재생 코드 커밋: `46eb586c9737138ce87da713e3609ec38f1a1512`. Snowball `KMS`, 고정 Docker image `sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`, Python 3.11.15/NumPy 2.4.6, BLAS/OMP 각 1 thread. 원본·은행 자료는 읽기 전용 mount.

## Pooled 지표

각 seed에서 R2/R4/R5를 pooled한 지표를 계산하고, 아래에는 조건별 20개 seed의 중앙값을 표시했다. Coverage 단위는 %. 각 열은 기준 → FAR이다.

| 조건 | XY RMSE (cm) | Heading RMSE (°) | Pose95 (%) | Heading95 (%) | XY95 (%) | mean NEES3 |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 6.6481 → 6.7876 | 1.0545 → 1.0993 | 93.4949 → 93.8935 | 98.3897 → 99.0593 | 90.5931 → 91.3584 | 2.8696 → 2.7982 |
| L2_GYRO_ARW | 6.7383 → 7.0097 | 1.0925 → 1.1406 | 93.2876 → 93.7978 | 98.3418 → 98.7404 | 90.7844 → 91.5976 | 2.8803 → 2.8315 |

NEES 감소나 coverage 상승만으로 일관성 개선을 확정하지 않는다. 명목 coverage와 정확도·거울해·통합 기준을 함께 평가해야 한다.

## Seed별 paired RMSE 비율

비율은 각 seed의 FAR/기준을 구한 뒤 중앙값을 취했다. 1보다 작으면 개선이다. CI는 고정 bootstrap seed 20261119, 10,000회 seed 재표본의 95% 구간이다. 개별 모델 중앙값의 비율과는 다를 수 있다. 동일 RF/환경의 seed 반복이며 독립 환경 확인은 아니다.

| 조건 | 경로 | 지표 | paired 비율 중앙값 | 95% CI | 개선 seed / 20 |
|---|---|---|---:|---:|---:|
| B0 | R2 | XY | 1.05309 | [1.01138, 1.09921] | 5 |
| B0 | R2 | Heading | 1.11341 | [1.08677, 1.23390] | 2 |
| B0 | R4 | XY | 0.96683 | [0.93489, 1.08389] | 12 |
| B0 | R4 | Heading | 0.83104 | [0.77343, 0.86687] | 20 |
| B0 | R5 | XY | 0.94235 | [0.92851, 0.98491] | 15 |
| B0 | R5 | Heading | 0.93025 | [0.86001, 0.95873] | 17 |
| B0 | pooled | XY | 1.01601 | [0.97160, 1.06182] | 9 |
| B0 | pooled | Heading | 1.02307 | [1.00037, 1.06810] | 6 |
| L2_GYRO_ARW | R2 | XY | 1.04951 | [1.00716, 1.09372] | 5 |
| L2_GYRO_ARW | R2 | Heading | 1.12955 | [1.07606, 1.23281] | 2 |
| L2_GYRO_ARW | R4 | XY | 0.96977 | [0.93691, 1.04834] | 12 |
| L2_GYRO_ARW | R4 | Heading | 0.83204 | [0.78295, 0.87062] | 19 |
| L2_GYRO_ARW | R5 | XY | 0.94750 | [0.93351, 0.98285] | 15 |
| L2_GYRO_ARW | R5 | Heading | 0.93806 | [0.87034, 0.96544] | 17 |
| L2_GYRO_ARW | pooled | XY | 1.01690 | [0.96895, 1.05656] | 9 |
| L2_GYRO_ARW | pooled | Heading | 1.02441 | [0.99097, 1.07429] | 7 |

B0 pooled XY 비율은 1.01601, Heading은 1.02307이다. L2 pooled XY는 1.01690, Heading은 1.02441이다. XY의 두 CI와 L2 Heading CI는 1을 포함한다. B0 Heading CI는 [1.00037, 1.06810]으로 이 탐색 집계에서 악화 방향이다. R2는 두 조건 모두 XY·Heading 비율 CI가 1보다 크다. 다중 비교 보정이나 독립 확인은 수행하지 않았다.

## 거울해와 기존 판정 규칙의 기술적 집계

거울해는 기준과 FAR 모두 B0 0/120 passages, L2 0/120 passages였다. 다음 N_I/N_A/N_J는 원래 평가 함수의 seed별 결과 합계이며, H2/H2S 참조에 대한 규칙이다. 직접 A/B 우월성 검정으로 바꾸지 않았다. 기존 `N_J≥18` 및 거울해 0 조건은 어느 행도 충족하지 못했다.

| 조건 | 참조 | 모델 | N_I | N_A | N_J | 거울해 passages |
|---|---|---|---:|---:|---:|---:|
| B0 | H2 | F2SKRWV | 16 | 12 | 9 | 0 |
| B0 | H2 | F2SKRWV_FAR_K | 16 | 9 | 8 | 0 |
| B0 | H2S | F2SKRWV | 16 | 20 | 16 | 0 |
| B0 | H2S | F2SKRWV_FAR_K | 16 | 19 | 15 | 0 |
| L2_GYRO_ARW | H2 | F2SKRWV | 15 | 11 | 8 | 0 |
| L2_GYRO_ARW | H2 | F2SKRWV_FAR_K | 17 | 9 | 7 | 0 |
| L2_GYRO_ARW | H2S | F2SKRWV | 15 | 20 | 15 | 0 |
| L2_GYRO_ARW | H2S | F2SKRWV_FAR_K | 17 | 19 | 16 | 0 |

## 재현 실패와 자기 검사

- 과거 동결 기준선: **40/40 조합 미통과**, 2400개 scalar 중 492개 실패. 실패는 모두 F2SKRWV였고 H2/H2S는 모두 허용치 이내였다.
- 최대 scalar 차이: B0 seed47 R5 XY RMSE, 과거 7.234476796455346 cm / 현재 7.2323251069985774 cm, 절대 차이 0.0021516894567685796 cm. 허용치 1e-8은 변경하지 않았다.
- 기준선 이웃 경계 수치 불안정성과 원본 실행 환경/trace 부재는 [선행 재검증](../revalidation_20261119/RESULT_KO.md)에 남겼다. 과거 seed30–49 원본 NPZ 배열과의 동일성은 입증되지 않았다. 이번 양쪽 모델은 동일한 복원 NPZ를 공유했다.
- 40개 고유 조건·seed 결과, 320개 A/B point 행, 16개 paired 행, 2400개 고유 기준선 scalar 및 480개 trace의 완전성을 확인했다.
- 480개 trace의 모든 숫자 배열이 유한하며 입력과 t/pose_id가 같았다. 120개 route·seed·조건에서 첫 개입 이전 A/B 상태·공분산·수용 mask 등이 정확히 일치했다.
- B0 seed30의 이전 NumPy 2.4.6 진단 trace와 H2/H2S/F2SKRWV의 X/P/mask/t/pose_id/Reff/prior/Pprior 72개 배열이 bit-exact했다. 이것은 과거 원본 trace 재현을 뜻하지 않는다.
- 기존 모델 코드 4개와 calibration 4개의 SHA256 일치, 120개 입력 hash, 40개 RESULT hash, 480개 원격 trace hash를 기록했다. 로컬 게이트 회귀 검사에서 기본 중단, 명시적 계속, 비유한 값/기준선 누락 시 중단을 확인했다.
- 재생 4개·집계 1개·trace 자기 검사 1개 컨테이너가 모두 exit 0으로 종료했다. 독립 감사는 수행하지 않았다.

## 산출물과 보존 위치

- [요약 JSON](summary/SUMMARY.json), [전 point CSV](summary/FAR_AB_POINTS.csv), [paired CSV](summary/FAR_AB_PAIRED.csv), [coverage·정확도 규칙 집계](summary/FAR_AB_DESCRIPTIVE_RULES.csv).
- [기준선 2400개 비교](summary/BASELINE_PARITY.csv), [완전성 검사](summary/VALIDATION.json), [trace 자기 검사](summary/TRACE_SELF_CHECK.json).
- [실행 영수증](EXECUTION_RECEIPT.json), `RUN_*.json` 입력·출력 hash/시각, 40개 조건별 `RESULT.json`, 컨테이너 로그.
- [480개 원격 trace hash 목록](summary/RETAINED_TRACE_MANIFEST.json). Trace 원본은 Snowball `/home/KMS/FAR_KRIGING_AB_20261119_01a1f269/authorized_explore_01/results/{condition}/seed{seed}/traces/`에 보존했다. GitHub에는 수치 결과·검사·hash·로그를 업로드하며 NPZ를 중복 업로드하지 않는다.
- 현재 판정: **전체 탐색 실행 완료 / 과거 기준선 재현 미통과 / pooled RMSE 개선 근거 없음 / 채택 미승인**.
