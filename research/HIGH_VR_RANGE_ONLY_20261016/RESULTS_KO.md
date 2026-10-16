# High-power Range variance-only 검증 결과 (2026-10-16)

**최종 판정: 실행 PASS, 독립 재감사 PASS. High-power Range Vr 하한만으로 Mount 45° 조건부 XY 과신을 해결하는 가설은 지지되지 않았으며, 새 모델 채택은 보류한다.**

## 1. 실행과 원본 감사

- [실제 재귀 GitHub Actions Run 38848652316](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38848652316) — [전체 재귀·One-step·원본 소스 감사 artifact ID 12023958123](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38848652316/artifacts/12023958123), ZIP SHA256: 71b5433020133af75386edd03410bcf073b47a9d17f4cb749d0bf7c24b761475.
- [독립 재집계 Run 38849209005](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38849209005) — [감사 결과 artifact ID 12024154363](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38849209005/artifacts/12024154363), ZIP SHA256: 9815d188ed81dbd81472cfcf344db1716a8c12b00b21ea56a7ccbb38e506e778.
- 코드 소스 감사 및 주파수/FFD/물리 Odometry 입력 보존, ZIP SHA/CRC, 상관 공분산 SPD, Joint4/whitened SR4 선형 동등 canary PASS. 원본 POWER Full 16개와 원본 LoS R0 16개 총 32개 원본 state/P/Gate parity PASS.
- 2 Mount×4 Bias(B0/L0/L1/L2)×2 solver(J4/SR4)×7 Full RF 정책=**112개 진짜 재귀 결과**. 각 R2 979 원본 시점, 그중 829개 평가시점. 별도의 동일 POWER prior One-step 대조 112개, 원본 LoS R0 16개 대조.
- R2는 하나의 복도 RF 장면과 Gyro/Odom motion seed 0을 공유한다. 16개 구성이 16개 독립 RF 환경은 아니다.

## 2. 개입 정의와 물리적 제약

R4/R5 학습 전력 cutpoints를 그대로 적용:

- Low/Mid: q = −4.468198151
- Mid/High: q = −3.4490846059
- Full R2 829 평가시점 중 High-power Mount0 = **189**, Mount45 = **196**.

기존 POWER의 Range 공동 오차분산은 Low Vr=0.032977809 m², Mid Vr=0.0137682116 m², High Vr=0.0036739224 m².

원본 R0,r=0.0068578637 m²를 사용하여 High bin에서만 다음 사전 지정 대조를 적용한다.

$$
V'_{r,k}=\max(V_{r,k},aR_{0,r}),\quad a=1,2,4
\quad\text{if }q_k\geq -3.4490846059.
$$

| High Vr 변형 | Vr_high (m²) |
|---|---:|
| Original POWER | 0.0036739224 |
| R0 floor | 0.0068578637 |
| 2R0 floor | 0.0137157274 |
| 4R0 floor | 0.0274314548 |

**유지:** signed mean mu_r/mu_s, marginal Vs, original Crs, raw dual-LP power and s, LUT/Jacobian, original Q, NIS threshold, motion data, case/seed and detector. Low/Mid bin Range Vr도 모두 원본과 비트 동일하게 유지.

**중요:** Vs와 Crs를 고정해도 s|r의 조건부 분산 Vs−Crs²/Vr은 변화한다. High bin에서 본래 0.00297387→R0 floor 0.00298900→2R0 0.00299773→4R0 0.00300210. 본 실험은 오직 marginal Vr 원소만 변경했으며, 실제 correlated SR4 조건부 정보에는 작은 이차 효과가 있다.

## 3. 주요 결과: L2 Full RF Joint4 natural Gate

| Mount | Vr high 모델 | Heading RMSE (°) | XY RMSE (m) | Bias RMSE (°/s) | Cond XY NEES | Narrow-axis NEES | Pose NEES | Pose95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0° | original | 1.9914 | 0.19168 | 0.03266 | 7.9186 | 6.3340 | 12.8896 | 45.72% |
| 0° | R0 floor | 1.9562 | 0.19359 | 0.02956 | 7.9040 | 6.3078 | 12.6521 | 45.96% |
| 0° | 2R0 | 1.9018 | 0.19007 | 0.02760 | 8.1662 | 6.2720 | 12.8039 | 45.36% |
| 0° | 4R0 | 1.7963 | 0.16999 | 0.02653 | 8.5296 | 6.2765 | 13.3943 | 45.24% |
| 45° | original | **0.7274** | **0.07859** | 0.01231 | **16.0579** | 13.7739 | **18.5797** | **12.30%** |
| 45° | R0 floor | 0.7416 | 0.08513 | 0.01222 | 16.2146 | 13.4946 | 18.6240 | 12.06% |
| 45° | 2R0 | 0.9077 | 0.11310 | 0.01325 | 17.7986 | 13.9863 | 21.0296 | 10.49% |
| 45° | 4R0 | 1.0205 | 0.14466 | 0.01403 | 19.8862 | 14.8030 | 23.7684 | 6.88% |

Mount45에서는 High-power Vr 증가가 XY accuracy와 conditional-XY NEES를 동시에 개선하지 못했고, 높은 하한에서는 오히려 둘 다 악화됐다. Mount0에서는 일부 Heading/Bias RMSE가 개선되나 conditional XY NEES는 4R0에서 7.919→8.530으로 악화. **두 Mount에서 균형 잡힌 개선이 재현되지 않았다.**

## 4. Gate 고정과 동일 prior One-step

자연 Gate 조건은 항상 원본 2-DoF 99% NIS threshold 9.21034를 사용했다. 원본 POWER가 허용한 시간별 mask를 새 candidate에게 **그대로 강제**한 offline 별도 재귀 대조를 수행했다.

- L2 J4 Mount0: 812/829 수용(High 189개), 원본과 R0/2R0/4R0 후보의 Gate mask 완전 동일. 성능 변화는 Gate 수용수 변화가 아니라 Range 가중치와 재귀 state/P 차이에서 발생.
- L2 J4 Mount45: 기존 POWER 785/829 수용(High 195개), R0 floor natural 786/829 수용(High 196개); 추가 High 패킷 1개가 결과에 영향. 같은 POWER mask로 고정했을 때 R0 floor의 Heading 0.8077°, XY 0.08739m, 조건부 XY NEES 15.6509, Pose95 11.34%. 원본 0.7274°, 0.07859m, 16.0579, 12.30%와 비교하면 Cond XY NEES만 소폭 감소하고 점추정은 악화.
- 원 POWER와 **동일 RF 갱신 직전 상태·공분산**을 주는 one-step 반사실적 시험에서도 High만 효과가 나타나고 Low/Mid 패킷 업데이트는 원본과 정확히 동일. L2 Mount45 R0 floor의 one-step 평균 Heading 오차제곱 변화는 +0.000271°²이며, 전체 RMSE의 더 큰 차이는 재귀적으로 상태가 누적되기 때문임.

## 5. 물리적 Range 정보 차단효과 확인

L2 J4 High-power subset의 **각 정책 자체 prior**에 대한 선형화 Joint4 Range→XY gain 크기 중앙값:

| Mount | Original | R0 floor | 2R0 floor | 4R0 floor |
|---|---:|---:|---:|---:|
| 0° | 0.06407 | 0.04274 | 0.02504 | 0.01428 |
| 45° | 0.07886 | 0.05090 | 0.03176 | 0.01934 |

이 표는 동일 prior의 Gain은 아니고 실제 재귀마다 달라진 prior를 포함한다. 그러나 Range weight가 강하게 축소되는 실험에서 Mount45 XY 위치 정확도가 크게 나빠짐은 High-power Range가 **일부 유용한 실제 위치 정보를 공급**할 가능성과 일치한다. High Vr가 R0보다 작은 것 자체로 위험한 관측이라는 결론을 내릴 수 없다.

## 6. 독립 재감사와 최종 연구 판정

[Run 38849209005](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38849209005)에서 original archived GT로 모든 112개 후보의 Heading/XY/Pose/condXY/Gate 점수를 별도 재계산하고, 16개 Full 원본 POWER x/P/Gate 대비 출력 parity, low/mid unchanged, Vs/Crs bit exact, High-only Range variance update, SPD, fixed-gate exact mask, 모든 112 one-step Low/Mid delta=0을 확인 PASS.

모든 16개 Full 조건에 대해 Heading/Bias/XY/condXY NEES/Pose95의 비악화를 동시에 만족하는 후보는 없음(원 R0 floor, 2R0 floor, 4R0 모두 scientific all-condition PASS=false).

**최종:** High-power-only Vr floor는 Mount45의 조건부 XY narrow-axis covariance overconfidence를 해결한다는 가설의 반례. Baseline POWER_JOINT 유지. 이 결과는 기존 물리 Q가 Sensor-v2 생성 노이즈와 정합함을 확인한 앞선 ODOM-Q 감사와 같이 보존한다. 다음 우선 검증은 RF Range의 signed mean mu_r, RF Gate, 조건부 XY 좁은 고유축의 Range Jacobian 정렬 및 site-time 지속 오류다.

### 실험 한계

- Original R0_r은 실제 LoS thermal range variance의 인증된 물리적 하한이 아니라 연구 기준.
- 동일 전력 bin에서 Vs,Crs는 고정하지만 conditioned-s noise covariance는 Vr 변화에 따라 달라짐.
- 정상 Native LoS R0 기준선만 정합 확인. Full 학습 POWER를 Native LoS에 전이한 안전성은 본 시험에 포함하지 않음.
- R2는 이미 여러 번 관찰한 단일 RF 복도/seed, 최종 독립 일반화 판정 불가.

### 원시 산출물

메인 artifact에는 SOURCE_AUDIT.json, HIGH_VR_FINAL.json, HIGH_VR_ALL_RECURSIVE.csv (112개), HIGH_VR_ONE_STEP_FIXED_PRIOR.csv (112개), HIGH_VR_SOURCE_PARITY.csv (32개), HIGH_VR_LOS_R0_GUARDS.csv (16개), HIGH_VR_POWER_STRATUM.csv (2개), 16개의 VR_ONLY_CASE_BIAS_SOLVER.npz 원시 재귀 상태/P/NIS/Gate/K/R packet.
독립 artifact에는 PRE_AUDIT.json, INDEPENDENT_FINAL.json, INDEPENDENT_PAIRED_ALL.csv (48개), INDEPENDENT_GATES.csv (3개).
