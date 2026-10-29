# MB_VAR 대조조건 재검증 — E2/E5 수정 및 R5-B 초기상태 분리

## 범위와 완료 상태

원본: `research/mbvar-control-correction-20261029`, snapshot `422b6c0`, run `40820579727`.
이 폴더는 별도 브랜치 `research/mbvar-e2-e5-revalidation-20261029`에 추가했다. 원본 코드와 원본 실행 산출물은 변경하지 않았다.

- E2/E5 계산: run **40830330560**, 12/12 계산 shard 성공. E2 점수 행 504개: 기존 기준선 120, seed0 legacy 24, full Jacobian 240, frozen donor 120.
- 첫 집계기는 `E2R_*_lo.csv`에 `E2R_ACF_*_lo.csv`까지 포함해 중복 검사에서 실패했다. 계산 결과는 손상되지 않았고 모두 게시했다. 이 run 전체를 성공이라고 부르지 않는다.
- 수정 집계 및 기존 C0/E1/E2/E4 재집계: run **40831583667**, 성공. `aggregate_recovery.py`가 명시적 6 case × 2 part 파일만 읽는다.
- R5-B 초기상태/센서 seed 교차 실험: run **40830802359**, 성공, 4×4×3 arm = 48회 재귀 실행.

최종 표: `results/final_run_40831583667/`.
E2/E5 원 계산: `results/run_40830330560/`.
R5-B 실험: `results/seed_run_40830802359/`.

모두 mount 0, B0이다. E2는 6 case × 10 sensor/initialization seed(0–9), E5는 seed0, R5-B는 사후 선택 seed 0/3/8/9이다. 동일 corridor RF를 재사용한다. 기존 24조건(4 gyro-bias 수준) 전체를 재실행한 것은 아니다. E7 nested LORO와 새 환경은 미실행이다.

## 1. E2 수정

원 평균 학습 표본과 Ridge 모델은 유지했다. 두 계약을 분리했다.

1. `FULL_JAC_COND`: 상태 의존 평균을 관측함수로 취급한다. `h_eff(x)=h(x)+m(x)`, `H_eff=H+dm/dx`. H에서 파생된 특징의 미분도 포함한다.
2. `FROZEN_COND`: 보정 없는 donor 필터의 해당 시점 prior로 계산한 평균을 고정한다. 보정된 필터의 상태에 대한 미분을 넣지 않는다. 이는 다른 추정기이며 full-Jacobian과 동일하지 않다.
3. `FULL_JAC_SHUF`: 같은 full-Jacobian 구현에 shuffled-label mean을 적용한 대조군.

기존 mean을 prior 조건부 외생 보정으로 해석하면 dm/dx를 반드시 넣어야 한다고 단정할 수 없다. 이번 수정은 상태 의존 관측함수와 고정 prior 보정의 의미를 분리한 것이다. 기존 full-state mean fit이 유효해졌다는 주장이 아니다.

### MB_VAR, 10 seed, paired 변화 중앙값

아래 delta는 각 seed에서 새 모델-원 MB_VAR를 계산한 후 중앙값을 취했다. 음수는 개선이다.

| case | Full-Jac ΔHeading [deg] | ΔXY [cm] | 동시 개선 | Frozen ΔHeading [deg] | ΔXY [cm] | 동시 개선 |
|---|---:|---:|---:|---:|---:|---:|
| R2-A | +1.3564 | +27.3701 | 0/10 | +0.8117 | +25.0394 | 0/10 |
| R2-B | +7.0953 | +101.7348 | 0/10 | +1.0027 | +24.1839 | 0/10 |
| R4-A | +2.6238 | +26.1748 | 0/10 | +2.4983 | +23.6783 | 0/10 |
| R4-B | -0.0592 | -2.5040 | 9/10 | -0.0332 | -2.2928 | 7/10 |
| R5-A | -0.1835 | -3.9607 | 6/10 | -0.4207 | -5.8539 | 8/10 |
| R5-B | +2.8887 | +74.8550 | 0/10 | +2.3843 | +61.1769 | 0/10 |

미분 처리만 고쳐도 기존 conditional mean은 전역 해법이 되지 않는다. R4-B의 국소 개선은 확인되지만, '긴 시간상관이 조건부 평균 때문인가'라는 일반 가설은 여전히 미확정이다. R5-A full-Jac의 worst seed Heading은 10.34 deg로, 중앙값만으로 강건성을 주장하면 안 된다.

## 2. E5 수정

기존 구현은 `I_normalized = I / outer(sd,sd)`였다. `delta x = D delta xi`이면 올바른 무차원 정보는 `D.T @ I @ D`이다. 기존 나눗셈은 단위 변경에 대한 불변성도 만족하지 않으며, 그 고유값 수치와 경로 간 배수 비교는 철회해야 한다.

추가로 다음을 계산했다.
- STATIC: 올바른 정규화만 적용한 정적 정보 합.
- DYNAMIC_NO_Q: 관측 Jacobian을 F로 창 시작 상태에 운반한 정보.
- DYNAMIC_Q: 기존 process Q를 주변화한 관측 혁신 정보. 합성 선형 모델에서 stacked covariance 직접 계산과 일치 확인.
- PRIOR_DIAG 척도와 모든 경로에 같은 FIXED_PHYSICAL 척도(0.1 m, 0.1 m, 5 deg, 0.2 deg/s)를 분리.
- 4상태 고유값, gyro-bias를 고정한 3상태 pose 정보, prior를 더하고 gyro-bias를 Schur 주변화한 정보도 별도로 저장.

### MB_VAR, seed0, 공통 60–120초 창

DYNAMIC_Q / FIXED_PHYSICAL / gyro-bias 고정 pose 블록의 최소 고유값:

| case | 최소 고유값 |
|---|---:|
| R2-A | 0.121571 |
| R2-B | 1.602910 |
| R4-A | 0.394814 |
| R4-B | 22.316696 |
| R5-A | 0.122234 |
| R5-B | 0.351311 |

R5-A는 R2-A와 거의 같은 값이다. 따라서 'R5-A가 다른 모든 경로보다 10–1000배 약하다'는 결론은 유지되지 않는다. 공통 물리 척도에서 각 FAIL 창의 최소 고유벡터는 접선 성분 0.988–0.998이지만, PRIOR_DIAG 척도에서는 혼합 방향이 된다. 방향 해석에는 척도를 반드시 명시한다.

이 수치는 기존 white Q/R와 선형화 궤적에 조건부인 nominal information이다. 실제 상관 RF의 Fisher 정보량이나 모든 seed의 관측 가능성 증명은 아니다. 약한 정보, 초기 prior, 비선형성 및 시간상관의 상호작용은 추가로 분리해야 한다.

## 3. R5-B seed 오류 수정 및 실제 교차 재실행

원본 점수에서 'seed 3/8/9가 BB_ORIG까지 모두 실패한다'는 설명은 틀렸다.

| seed | BB_ORIG Heading | MB_ORIG | MB_VAR |
|---|---:|---:|---:|
| 3 | 0.9412 | 4.8222 | 5.1585 |
| 8 | 6.1920 | 6.2431 | 5.5543 |
| 9 | 0.8812 | 0.7087 | 4.6839 |

새 실험은 control/noise seed와 initial-state seed를 독립적으로 0/3/8/9에서 교차했다. BASE mask는 각 조합에서 다시 생성했다. 대각선 12개 score는 원본과 최대 4.52e-7 이내다.

### MB_VAR Heading RMSE [deg]

| control seed / initial seed | 0 | 3 | 8 | 9 |
|---|---:|---:|---:|---:|
| 0 | 0.5402 | 4.7156 | 5.3752 | 4.8845 |
| 3 | 0.7950 | 5.1585 | 5.7918 | 5.3158 |
| 8 | 0.6684 | 4.8256 | 5.5543 | 4.9851 |
| 9 | 0.5711 | 4.5333 | 5.2400 | 4.6839 |

시험 범위에서 큰 오차는 control seed보다 initial-state seed를 따라갔다. initial8은 세 arm 모두에서, initial3은 MB_ORIG/MB_VAR에서, initial9는 MB_VAR에서 큰 오차가 유지된다. 즉 초기상태 의존 취약성과 mean/variance 변경의 상호작용을 구분해야 한다.

initial heading errors: seed0 +0.4613 deg, seed3 -6.6951 deg, seed8 -10.5210 deg, seed9 -5.9316 deg. 그러나 위치 초기오차도 함께 달라지므로 Heading 초기오차만이 원인이라고 확정하지 않는다. mask 재생성 효과도 포함된다. 이 4개 seed는 사후 선택이므로 실패 확률 추정에 쓰지 않는다.

## 4. 기존 결과의 집계 수정

### E1
원 `JUDGE_E1_SEEDS`는 sx만 집계해 seed1–9, 총9개였다. 새 `E1_PAIRED_ALL10.csv`는 seed0을 추가했다. 반복을 seed별 평균한 뒤 paired delta의 중앙값을 계산한다.

MB_VAR, m8:

| case | RSC_TOTAL ΔHeading | ΔXY | RSC_S ΔHeading | ΔXY |
|---|---:|---:|---:|---:|
| R4-B | -0.2164 | -1.1794 | -0.5790 | -2.2418 |
| R5-A | -1.4737 | -15.7360 | +0.0706 | +9.1701 |
| R5-B | -0.0998 | -0.1333 | +3.5777 | +49.9526 |

R5-A에서 s만 할인한 MB_VAR는 단순히 효과가 작은 것이 아니라 이 대조에서 악화한다. 관측 빈도와 가중치가 RAND 구간 안에 함께 있다는 사실은 통계적 동등성 증명이 아니다. 위상분산/RAND분산<1도 관측 선택의 효과가 없다는 증명이 아니다.

### E4
기존 manipulation eligibility는 `lag1_s<0.1`이므로 큰 음의 상관이 통과할 수 있다. 원 사전 판정은 보존하고, `abs(lag1_s)<0.1`과 `abs(lag1_r)<0.1`을 모두 요구한 사후 민감도 분석을 추가했다.

840은 arm/mask를 포함한 결과 행 수이며 독립 순열 수는 390이다. 원 제외는8/390(16행), 강화 기준 제외는51/390(110행)이다.

강화 기준에서도 R5-A MB_VAR 기준1–3 동시 충족은9/10, R4-B는0/10이다. R5-B 악화도 남는다. 따라서 전역 H_TC 기각과 R5-A의 조건부 지지는 유지된다. 이는 새 RF 재생이 아니라 같은 순열 원자료 재집계다.

### C0
비선형 나머지가 크다고 state covariance mismatch의 근거가 모두 없어지는 것은 아니다. 선형 투영 He와 직접 state NEES를 함께 본다. R5-A MB_VAR의 median E[(He_s)^2]/E[(HPH)_ss]는6.91, NEES4는11.26이다. 'P 과신의 증거는 R4에서만 있다'는 결론은 유지하지 않는다. 단일 corridor 시계열의 정식 독립 표본 검정으로 해석하지 않는다.

## 5. 검증 결과와 주장 한계

- baseline120개 replay의 기존 CSV score 최대차:4.93e-7 (CSV 반올림 수준, 상태 exact parity 주장 아님).
- raw output hash66개 검사: 실패0.
- Jacobian QA576점 중 분기 경계 교차7점. 안정 구간 상대오차95%값2.45e-9. 경계에서 최대 상대오차1.48이므로 전체 비매끄러움이 해결됐다고 주장하지 않는다.
- effective observation decomposition 최대오차4.44e-16.
- 정보행렬 단위변환 불변성 최대상대오차4.38e-16.
- process-Q 주변화와 stacked covariance 합성 검산 최대차1.42e-14.

미확인: online 조건 분류/가중치의 held-out 성능, E7 nested LORO, 다른 corridor/실측, geometry×temporal-correlation 상호작용의 완전한 분해, initial position와 initial heading의 개별 영향, 모든 seed의 regen-mask E4, 모든 가능한 공분산 모델/mean 모델의 유효성.

## 재현

```
# GitHub의 같은 locked inputs를 사용한다.
REFLECT_ROOT=<inputs> python revalidate.py --case R5_aA_m0 --part lo --out <shard-output>
REFLECT_ROOT=<inputs> python seed_isolation.py --control-seed 0 --out <seed-output>
# canonical aggregator: 명시적 파일명을 사용하는 수정본
python aggregate_recovery.py --input results/run_40830330560 --out <corrected-output>
python audit_existing.py --input ../mbvar_control_correction_20261029/results/run_40820579727 --out <audit-output>
```

각 실행의 입력 hash/설정/명령/시각/code hash/output hash는 results의 MANIFEST 파일에 있다. 파일 이동·삭제는 없으며 원 연구 branch/main을 변경하거나 PR을 만들지 않았다.
