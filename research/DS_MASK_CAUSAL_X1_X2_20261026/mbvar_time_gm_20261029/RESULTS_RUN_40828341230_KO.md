# 시간 기반 FOGM 재시험 결과 — 2026-10-29

**실제 계산 완료.** 실험과 구현의 범위는 고정 BASE mask/같은 입력, mount 0, B0/L2, R2/R4/R5 x anchor A/B = 12조건.
- GitHub Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/40828341230
- 실행 SHA: \`7fab61cb1b26240b8031b77e277bc6ab92651245\`
- Workflow artifact ID: \`12877941768\` / zip sha256 \`304ac6178a681f16f9958ab43a3237e9b8837ac35670f29853567def8d5ac7db\`
- 완전한 산출물: \`FILTER_SCORES.csv\`, \`LORO_TIME_FITS.csv\`, \`TRAIN_ACF.csv\`, \`HELD_ACF_DIAGNOSTIC.csv\`, \`PARITY.csv\`, \`SUMMARY.csv\`, \`DIFFERENCING_MATH_TEST.csv\`, \`MANIFEST.json\` (artifact 내)
- 원본 비교: \`MB_VAR\`, \`GM03\`, \`GM1Y20\`; 재시험 \`GM_TIME_KEEP\`, \`GM_TIME_SPLIT\`.
- **기존 코드 및 입력 보존**. 새 실험 코드는 별도 디렉터리.

## 시간 기반 상관 모델

\[
\phi_k=e^{-\Delta t_k/\tau},\quad
b_k^-=\phi_k b_{k-1}^+,\quad
P_{bb,k}^-=\phi_k^2 P_{bb,k-1}^+ +\sigma_b^2(1-\phi_k^2)
\]
상태는 5차원. 시간상수 \(\tau\), 유색 편파 분산 \(\sigma_b^2\)를 오직 다른 두 route의 truth-referenced 편파 RF residual(B0, t>=30s) 자기공분산 lag1..8에서 적합한다. 학습 R2, R4, R5를 evaluation fold에 혼합하지 않는다. 다만 같은 corridor이며 최종 외부검증은 아니다.

## R2/R4/R5 held-out fit

| Held-out route | \(\tau\) (s) | \(\phi_{0.2s}\) | colored sigma | fitting ACF RMSE |
|---|---:|---:|---:|---:|
| R2 | 1.3120 | 0.8586 | 0.1488 | 0.0633 |
| R4 | 1.5308 | 0.8775 | 0.1435 | 0.0267 |
| R5 | 1.0716 | 0.8297 | 0.1553 | 0.0483 |

Held-out residual contrast \( \epsilon_{s,k} - \phi \epsilon_{s,k-1}\) lag1 autocorrelation:
R2-A +0.226; R2-B -0.120; R4-A +0.291; R4-B +0.136; R5-A +0.298; R5-B -0.181.
이는 단일 시간상수 + 백색 관측오차 구조만으로 충분히 설명되는지 추가 검증이 필요함을 뜻한다. 차분 후 남는 상관은 기본 백색오차의 MA(1) 성분일 수도 있음.

## 결과: B0, 6개 case 균등 평균

| 필터 | H RMSE (deg) | XY RMSE (cm) | MB_VAR보다 H/XY 동시 개선된 설정 수 |
|---|---:|---:|---:|
| MB_VAR | 1.530 | 13.33 | 기준선 |
| GM03 | 1.689 | 17.46 | 1/6 |
| GM1Y20 | 3.152 | 34.69 | 3/6 |
| GM_TIME_KEEP | 2.253 | 29.41 | 1/6 |
| GM_TIME_SPLIT | 2.296 | 29.90 | 0/6 |

KEEP: 기본 R 그대로 유지 + 유색 편파 상태. 유색 분산의 이중 계상 가능.
SPLIT: R_ss = max(0.05*Rbase_ss, Rbase_ss - sigma_b²). 이 모델은 산술적 sensitivity 실험일 뿐 자기일관된 교정된 covariance 모델이 아님.
SPLIT에서 5%-floor는 수용 packet의 약 58%–80%에서 활성화. 단일 sigma_b²가 여러 거리에서 Rbase를 초과하여 일관된 백색/유색 분해에 실패한다는 징후.

## 경로별 핵심 B0

| case | MB_VAR H / XY | GM_TIME_KEEP H / XY | GM_TIME_SPLIT H / XY |
|---|---|---|---|
| R4-B | 1.391° / 8.865cm | 0.711° / 8.275cm | 0.815° / 9.072cm |
| R5-A | 3.833° / 39.597cm | 5.171° / 65.603cm | 5.330° / 67.263cm |
| R5-B | 0.540° / 4.137cm | 1.648° / 15.616cm | 1.700° / 16.289cm |

L2에서 GM_TIME_KEEP의 6-case 평균은 H 2.817°, XY 31.76cm, MB_VAR는 H 1.574°, XY 13.82cm. 따라서 \`TIME_GM\`은 현 설정으로 개선 모델 채택 **불가**.

## 재현 및 수학 테스트

- 모든 12조건에서 기존 PB.run(MB_VAR)과 새 wrapper DG.run(MB_VAR)의 state/P 최대 절댓값 차이 0.
- \`DIFFERENCING_MATH_TEST.csv\`: φ=.8, Rwhite=.2, Qη=.1에서 차분 잡음 분산 .428, lag1 공분산 -.16 (PASS). **차분 EKF 구현·실행은 아직 하지 않았다.**
- 실행 요약 및 output SHA는 artifact MANIFEST.json에 기록.

## 해석 경계

1. 시간상관은 존재하지만 단일 AR1 FOGM이 잡음의 적절한 생성모델이라는 가설은 검증되지 않았다.
2. 일반적인 white R와 colored state의 분해가 아직 식별되지 않음: KEEP double-count, SPLIT floor 오버라이드, 모든 모델의 측정잡음 공분산은 검증 전.
3. 5상태 필터의 R4-B 개선이 있어도 R5-A/B 악화가 큼. 상태 식별성·편파 왜곡의 조건부 평균/공분산·관측 기하 영향 미분리.
4. LORO에서 훈련 잔차에는 truth 사용, 평가 때 state filter에는 truth 미사용. route 간 동일 corridor 의존이 있어 독립 RF 일반화 입증이 아님.
5. FIXED BASE gate에서만 평가; 자체 gate는 아직 재시험하지 않음.
6. 결과가 나쁘다는 사실은 상태 확장 원리나 모든 시간상관 모델이 틀렸다는 뜻은 아님.
7. Measurement differencing에 대해 \`MEASUREMENT_DIFFERENCING_MATH_KO.md\` 참조. 이전 상태오차 및 차분 후 MA(1) 잡음·교차공분산을 처리하지 않은 단순 방법은 잘못된 필터임.

## Next decision gate

FOGM 재튜닝 전에 (a) 같은 거리/기하에서의 조건부 잔차 평균 제거, (b) colored vs white 공분산 식별, (c) R5-A 장기 구간에 대한 per-window model adequacy, (d) 시간·거리·회전 기반 FOGM의 held-route 비교, (e) naive differencing과 exact linear covariance benchmark를 구분해서 수행해야 한다.
