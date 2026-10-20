# POWER_JOINT — 유해/유익 RF 극단구간 물리 비교, 재생성 Mount 45°, 수정 시간기억 모델
2026-10-20 · 연구 재현 보고 · **기존 Full RF / 독립 장면 수 2개(복도·오피스)**

## 0. 근거와 검증 수준
- GitHub 신규 C01–C03/O01–O03 Full/Native-LoS 원본 9개 앵커·주로 조합의 모든 257-bin complex H에서 동일 Hann 4N, strongest-RX 30% leading-edge 관측기 재처리. [Source discovery/CRC](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39277485012), [new physical observer](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39349484700).
- 기존 30개 국소 RF-skip 및 신규 47개 국소 RF-skip의 이후 Heading RMSE 변화는 **별도 재귀 실행 결과**에서 인용. 이번 물리 재처리는 이 재귀 변화를 재실행한 것이 아니라 같은 구간의 `Full−LoS` 복소 RF를 기계적으로 설명한다.
- 새 12개 사전 선택 이벤트의 물리적 예측력 [descriptive discrimination](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39349944791); 불균형·선택 편향과 동일 공간/경로의 시계열 의존성 때문에 모수적 일반화 금지.
- 재생성 R4/R5 M45 [release R4](https://github.com/myoungsunk/sionna-resimulation/releases/tag/legacy-rf-r4-20261019-r02), [release R5](https://github.com/myoungsunk/sionna-resimulation/releases/tag/legacy-rf-r5-20261019-r02), [T10 mapping audit](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39350247894), [native physical audit](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39350526645). H/CFR는 유효하지만 원 Tnone 전체 경로에 행순서 그대로 붙이는 것은 불가. 재생성 R4/R5 M45 **자연 재귀 결과는 이 보고서에 없음**.

## 1. 기존 R5의 정의와 강한 쌍별 반례
물리 지표는 `|s_LoS|>.95` (포화에 가까운 관측비, *고유한 방향 정보량의 동치 아님*), `|∂h_s/∂ψ|<.2 rad⁻¹` (weak-slope *진단 임계치*, 최적 경계 아님), 참 XY 고정 ±45° 안의 조건부 관측곡선 **두 개 이상의 실제 numerical roots**. Root count는 prior와 위치 불확실성을 포함하지 않으므로 *real posterior multimodality*로 단정하지 않음.

| 기존 R5A M0 x10–16 방문 | 후속 30s RF-skip RMSE 개선 | weak slope | LoS |s|>.95 | multi-root |
|--|--:|--:|--:|--:|
| V1 | **+7.751°** | 약39.5% | **100%** | **35/38, 92.1%** |
| V2 | **−1.025°** | **0%** | **0%** | **27/38, 71.1%** |

**다중해만 존재한다고 유해한 RF는 아니다.** 극값·낮은 민감도·prior 및 실제 RF contamination이 결합하는 경우와 구별 필요. V1 한 구간의 접어둔 Range/s/gyro bias 연결은 이전 수행 파일 `POWERJOINT_R5_SITE_CAUSAL_AND_SEPARATE_CONTROLS_20261019.zip`의 00_REPORT 및 CSV를 정본으로 보존.

## 2. 신규 주로 Full/LoS complex H 직접 물리 분해

`c_F=c_L+c_M`; LoS FP에서 `s_L`, Full 채널을 LoS FP에 고정한 `s_F(t_L)`, 실제 Full의 검출 tap `s_F(t_F)` 사용. 다음 망원경 항등식은 모든 직접 LoS 유효 프레임에서 최대 오차 < 3e−16:
`Δs = [s(|c_L|²+|c_M|²)−s_L] + [s_F(t_L)−s(|c_L|²+|c_M|²)] + [s_F(t_F)−s_F(t_L)]`.
이는 **반사 성분 무간섭 전력 추가/복소 간섭/검출시점 이동**의 정확한 순차 분해이며 세 RMS를 원인 퍼센트로 합산할 수 없음.

| 같은 원인? | 사례 | 기존 RF-skip 후속 Heading RMSE 개선 | 원 Δs RMS | 복소 간섭 항 RMS | FP 이동 항 RMS | FP mismatch |
|--|--|--:|--:|--:|--:|--:|
| harmful | **C01 A M45 x16–21 V1** | **+5.393°** | **.506** | **.433** | .065 | 90.2% |
| harmful | C01 B M45 같은 위치/시간 | +4.340° | .161 | .074 | **.098** | 100% |
| **RF helpful** | **C01 A M45 x10–16 V1** | **−3.079°** | .189 | .126 | .120 | **86.7%** |
| harmful | C02 A M45 x4–10 V1 | +1.775° | .111 | .077 | .046 | 30.0% |
| **RF helpful** | **O02 O0 M45 y4–8 V1** | **−4.330°** | .181 | **.178** | .014 | 10.0% |
| weak RF corruption but skip helpful | C03 A M45 x1–4 V1 | +.767° | **.01087** | .0110 | 0 | **0%** |

**C01 A worst vs C01 A helpful:** FP mismatch 90.2% vs 86.7% 유사한데 RF-skip 효과는 정반대. 따라서 FP mismatch만 보고 RF를 거절하는 규칙 **반증**.
**C01 A worst vs O02 RF helpful:** 오염 간섭 RMS .433 vs .178, 둘 다 간섭이 있지만 후자는 RF가 필요. 간섭 절댓값만으로 RF 거절 불가.
**C01 B worst:** 상대 반사파/직접파 전력비 중앙값 .0178인데도 FP 100% 이동, 검출시점 효과가 간섭보다 큼. ‘큰 반사 전력비가 유해함’의 충분조건/필요조건 가설 부적합.
**C03 A x1–4:** LoS−Full Δs 매우 작고 FP 변환 0인데도 RF 생략 효과 +.767°; 물리 다중경로만이 아니라 prior/가중치/관측모델/계산 초기화 등을 확인해야 한다. 이 사건은 t≈0–5s이며 다른 사건의 post-30s score와 구간 진입조건이 다르므로 직접 비교 주의.

### O03: 동일 물리 복도의 반례와 서로 다른 물리 원인, 직접파 부재의 의미
`y4–8` 첫 방문(상대 안테나 yaw 중간 약 −85.5°) RF-skip +1.798°, DirectLoS 존재 **2/20**; 두번째 방문(yaw +95.2°) RF-skip **−15.347°**, DirectLoS **3/20**. 둘 다 대부분 blocked. 따라서 ‘blocked→RF skip’도 반증. Full−LoS Δs .187/.157은 LoS가 실제 존재한 **2개/3개 프레임에서만** 계산됐으므로 구간 전체 오염으로 인용하면 안 된다. FP 및 ratio도 동일.

## 3. 물리량 하나로 예측할 수 있는가? negative control
사전에 매칭한 신규 RF-skip 사건 **12개** 중 기준 개선 +.2° 초과 **7개**, RF 생략 불리 혹은 미개선 **5개**. 새로운 분류기를 훈련하지 않고 scalar ordering AUC를 진단:
- |`Δs`| RMS AUC **.400**, 복소 간섭 RMS **.400**, FP mismatch **.471**, port alignment **.571**.
- Direct LoS 존재 ≥75% 사건 10개만 남기면 |`Δs`| RMS **.333**, 복소 간섭 RMS **.333**, FP mismatch **.438**.
- 이는 **엄밀한 heldout AUC나 신뢰구간이 아닌 탐색적 12-event 순위 결과**. 각 사건은 독립 RF 환경이 아니고, 상관된 시간 샘플·표본선정 영향이 있음. **단일 물리 스칼라로 유해/유익 업데이트를 가려낼 수 있다는 주장은 불충분**.

## 4. 물리 근본 개입의 제한적 증거
**Full−LoS 차이 복소 진폭을 인위적으로 절반**으로 만든 `H=.5 H_FULL+.5 H_DIRECT_LoS`의 257-bin CFR를 동일 관측기로 다시 읽으면:
- C01 A x16–21 worst: `Δs` RMS .506→**.255**;
- C01 A x10–16 beneficial: .189→**.079**;
- O02 y4–8 beneficial: .181→**.088**.
물리 간섭 크기를 줄이면 관측 오염이 감소함은 확인되나 **유익한 RF 구간에서도 감소**함. LoS component를 사전에 알고 절반으로 재합성하는 *oracle causal intervention*이며 온라인 구현 방법이 아니고, **EKF Heading RMSE 개선은 검증하지 않았다**.

## 5. 신규 R4/R5 M45 physics, original T10 catalog only
R4 source R4_A/B x10–16 first: 330 pose each, Direct LoS 100%; A |`Δs`| RMS **.190**, FP mismatch **62.7%**, near-saturation LoS `|s|>.95` **24.8%**; B .066, 23.6%, 27.9%.
R5 source R5_A/B x10–16 first: 204 pose each; A `Δs` RMS **.221**, FP mismatch **70.6%**, near-sat **7.35%**; B .058, **29.4%**, **5.39%**. R5 A second visit x10–16 `Δs` .204, FP same70.6%, near-sat 0%.
기존 R5 M0 V1 `|s_LoS|>.95` 100%와 새로운 M45 first7.35%는 가설상 Mount가 LoS 포화를 크게 줄일 수 있음을 시사하지만 **M0 Tnone과 M45 T10 first catalogue는 완벽한 same-pose/time 대응군이 아님**. 물리 구역 비교이지 실시간 EKF heading 개선 증거는 아니다.

## 6. Corrected 6-state RF memory is not universally harmful: where is it usable?
Causal baseline after fixing `ν=z−h−μ−β`, 2-state beta memory, same total packet variance without double counting, B0:
| Frozen valid case | POWER1 Heading RMSE | beta memory | nominal 95 coverage POWER→memory |
|--|--:|--:|--|
| R2 A M0 | 1.799° | **3.023° worse** | 68.6→77.2% |
| R2 A M45 | .983° | **.857° better** | 63.6→92.4% |
| R2 B M0 | 1.516° | **1.105° better** | 64.8→96.1% |
| R4 A M0 | .659° | **1.040° worse** | 46.8→75.2% |
| R4 B M0 | 1.508° | **1.325° better** | 13.2→47.0% |
| R5 A M0 | 4.556° | **7.630° worse** | 39.7→16.1% |
| R5 B M0 | 1.056° | **.819° better** | 97.2→100% (potentially overly wide) |
B0 개선4/7, 악화3/7. L2: R2 A M0 1.559→2.957 worse; R2 A M45 .942→.768 better; R5 A M0 4.790→7.940 worse; R5 B M0 .695→.809 worse. R2 M45 상대 방향 front+side 구간은 memory 유리, back 구간은 일부 악화. **Mount 45° 한 조건의 호전만으로 Mount만 보고 켜는 규칙은 정당화 불가; 앵커/입사각/FP 상태/식별성도 영향**. 새로운 C/O 및 R4/R5 M45의 memory recursive는 아직 실행하지 않았으므로 해당 구간의 실효성 불명.

## 7. 공통 원인? 가장 좁힌 사슬
`RF 물리 오염`은 다수의 불리한 구간에서 확인되지만 종류가 다르다 (LoS 근방 slope/multiroot: R5 M0, 강한 coherent interference: C01 A, FP selection: C01 B, blocked LoS: O03). *LoS weak slope나 coherent MP 둘 중 하나가 모든 사건의 동일 원인*이라는 주장은 다수 반례로 기각.

현재 남는 공통 후보는 **오염 또는 약한 정보가 당시의 prior와 Gain/Gate에 의해 잘못된 상태/bias로 흡수됨**이다. 이를 online gate로 주장하려면 실제 필요:
1. 최악/최선 구간의 공통 진입 prior에서 Range-only / s-only / Kψrνr, Kψsνs 분해, Gate 및 기하 변화 직접 재귀
2. 실제 개입후 종료 상태·공분산 교차 반환; 이후 동일 Full RF 지속
3. **경로별 heldout** 및 새로운 office **scene-out** 조건에서 Heading RMSE, signed bias, nominal95 coverage, interval width 모두 비교.
4. Memory candidate는 **기억 없음 동일 총분산** 대비 방향/FP 전환 기반 forgetting 및 식별성 제한 후보로 실험해야 하고, GT 기반 위험구간 인식/LoS direct reference는 온라인 입력에 사용 금지.

**판정: 원인 유형별 분리·후속 재귀 검증은 GO, 하나의 universal physics gate / orientation-only memory switch / 특정 문제 해결 완료 선언은 NO-GO.**
