# N4-A2 극단 시점 단기 사건 검증: Range/s innovation → Gate → 조건부 XY 작은 고유축

**2026-10-15 · 계산·실험 PASS, 전체 인과 일반화는 미확정**

## 0. 고정 입력·감사 영수증

- 최종 실행: [GitHub Actions Run 38705800027](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38705800027)
- 원시 결과: [Artifact 11958301967](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38705800027/artifacts/11958301967), ZIP SHA256 `58da3505d56c1a4068a911b134ac7f122685974a1665b4a6a713dd58ca4801c3`
- 소스 커밋: `eb144fd26a97e4a169a79f475ee4475e10c97da5`.
- 원본 RF / N1 / N4-A / B0 물리 품질 예측 결과의 SHA256+ZIP CRC 검사 PASS.
- 이전 N4-A `decompose` 및 N1 `x/P/status` 총 11,748 시점 원본 정합 PASS.
- 합성 수치 테스트: Schur, eigen 분해, 시간 episode grouping, Kalman gain, Gate 계약 PASS.
- RF 채널·원본 Joint4/S4/SR4, G5 학습, LoS LUT, 추정기 업데이트 정책은 **일절 수정하거나 재학습하지 않음**.
- 극단 시점은 오프라인 Ground Truth 기반 *기존* Pose NEES로 선택. 이벤트 연관과 독립 평가 성능은 별개.

## 1. 극단 사건: L2, Full RF, Mount 0°

G5 Signed Mean+`R_s` 모델의 평가 829시점에서 Pose NEES 상위 5% = 42개 시점이 **181.8~190.0초에 하나의 연속 episode**로 집중.

첫 시점 `k=909, t=181.8s, pose_id=909`가 **최대 NEES 799,207.94**.

| 요인 | 기존 J4 같은 시점 | G5 Mean+Rs 같은 시점 |
|---|---:|---:|
| Anchor 수평거리 **GT** (m) | 0.522447 | 0.522447 |
| Anchor 수평거리 **RF 직전 prior** (m) | 0.112368 | **0.008728** |
| `||H_s,xy||` (1/m) | 0.96975 | **192.5994** |
| `H_s,ψ` (1/rad) | 0.32382 | 1.68696 |
| s innovation (정규화 이전) | −0.004059 | **−0.693781** |
| 사전 예상 innovation 분산 `S_s` | 0.0082503 | **6.217249** |
| Joint NIS | 0.10197 | **0.15690** |
| Gate | APPLIED | JOINT (수용) |
| 업데이트 이후 조건부 XY 작은 `λ` (m²) | 1.13503e−4 | **2.18033e−7** |
| 업데이트 이후 Pose NEES | 216.70 | **799,207.94** |

Frozen LUT 편파 Jacobian의 `∂s/∂x,∂s/∂y`는 송수신 방위각 변환 과정에서 `1/ρ` 형태의 근접 특이 민감도를 포함. G5 prior가 앵커의 XY 투영에 **8.7 mm** 이내로 진입했지만 실제 로봇은 **522 mm** 떨어져 있음. `p3_rf_adapter4.FrozenLut.quality`의 `near_anchor_pole=(ρ<=0.1m)` 진단은 G5에 해당하나 기본 Joint RF 갱신에서 이를 자동 차단하지 않음.

**매우 중요한 관찰:** G5의 큰 s innovation(−0.694)은 작은 것이 아니다. 그런데도 Jacobian의 매우 큰 위치 민감도에 의해 예측 innovation 분산이 6.217까지 커져, NIS가 0.157로 낮게 나온다. 99% Joint Gate 9.210보다 훨씬 낮아 갱신을 수용. NIS만으로 EKF 국소 선형화가 유효한지 보장할 수 없다는 실제 사례.

## 2. 같은 G5 사전상태를 공유하는 직접 반사실(한 번의 RF 갱신)

t=181.8s 한 시점에서 **동일한 G5 prior** `(x^-,P^-)`를 사용, 다음 갱신을 단발 비교했다. 새로운 필터 궤적을 재귀 실행한 것은 아님.

| 해당 패킷 한 번의 적용 | Pose NEES | 작은 조건부 XY λ (m²) | XY 위치오차 (m) |
|---|---:|---:|---:|
| **RF 갱신 생략** | 8,055.42 | 1.9520e−5 | 0.5273 |
| 원본 관측+R0 | **799,184.29** | **2.1803e−7** | 0.5247 |
| Signed Mean+R0 | 799,207.94 | 2.1803e−7 | 0.5247 |
| Signed Mean+G5 Rs | 799,207.94 | 2.1803e−7 | 0.5247 |

즉, 이 시점의 RF 갱신은 **위치오차를 겨우 약 2.6 mm 줄이면서 공분산의 가장 작은 방향을 약 89.5배 더 좁히고**, Pose NEES를 약 99.2배 상승시켰다.

본 시점의 G5 `R_s=0.0081`은 원래 R0와 같으므로 `Mean+R0`와 `Mean+G5 Rs`가 일치. 따라서 **181.8초 단일 갱신의 폭발을 물리 G5 Rs inflation 자체가 직접 유발한 것으로 해석하면 안 됨.**

숫자 대조:
```
R_s / ||H_s,xy||² = 0.0081 / 192.5994² ≈ 2.18361e−7 m²
observed post conditional XY λ_min          = 2.18033e−7 m²
```
강한 국소 편파 Jacobian이 EKF에 비현실적으로 큰 위치 정보량을 주어 조건부 공분산을 축소하는 **near-anchor projection/Jacobian over-information** 메커니즘과 정량적으로 일치한다. 비교는 개념적 근사이며 이 등식이 일반 정리라는 뜻은 아니다.

## 3. RF 다중경로 오차, NIS 및 Gate가 주원인인가?

사건 구간 42개 시점(상위 5%)과 나머지 787개 평가 시점 비교:

| 항목 | 사건 42개 | 나머지 787개 |
|---|---:|---:|
| 평균 |Range 측정모델 오차| (m) | **0.0390** | 0.0852 |
| 평균 |s 측정모델 오차| | **0.00645** | 0.09044 |
| 평균 |Range innovation| (m) | 0.0685 | 0.0709 |
| 평균 |s innovation| | 0.0352 | 0.0888 |
| 작은 XY 축 λ 중앙값 (m²) | **4.234e−6** | 7.770e−5 |
| 작은 XY 축 실제 오차 투영 절댓값 중앙값 (m) | **0.4921** | 0.05483 |
| 두 모델 RF 갱신 모두 수용한 비율 | **100%** | 91.6% |

여기서 *측정모델 오차*는 원본 RF 관측과 GT pose에서 Frozen LoS LUT 모델의 차이이며, 순수 다중경로 원인만을 뜻하지 않는다.

따라서 해당 사건은 순간적으로 Range/s 모델 오차가 더 커져서 발생했다고 보기는 어렵다. 오히려 **잘못된 pose prior가 거의 앵커 바로 아래로 진입 → 거대 편파 위치 Jacobian → 잘못된 RF 정보량 부여 → 작은 XY 공분산 축 붕괴**라는 연결이 실제 관측 수치에 부합한다.

### Gate 전환 대조
L2 Mount0 전체 평가 829시점에서
- 둘 다 수용: 763
- G5만 수용: 46
- J4만 수용: 3
- 둘 다 거부: 17

총 수용수 J4 766, G5 809로 +43 증가했지만, **극단 사건 42시점에서는 전부 J4와 G5가 모두 수용**. 극단 시점을 G5만 수용한 Gate 변경의 직접 결과로 단정할 수 없다.

### 전반적인 물리적 Range 반례
k=909에서 GT Anchor 수평거리=0.522m, G5 prior는 0.0087m. RF raw Range innovation은 −0.0233m에 불과하다. 3D anchor 높이차 ~2.2m인 거의 수직 기하에서 Range는 수평 위치의 변화를 매우 약하게 볼 수 있어, 이 기하에서는 Range가 잘못된 2D 위치를 자동 복원해주지 않는다. `H_r,xy` 실제 수치와 독립 장면 적용은 후속 검증 대상.

## 4. 확인된 것과 아직 미확정인 것

**국소 메커니즘 강하게 지지:** prior의 앵커 수평투영 8.7mm 접근과 s Jacobian의 192.6/m 폭증, Gate 수용, 조건부 XY λ 붕괴 및 1-step 고신뢰 오류 급증.

**아직 미확정:** 이전 업데이트들의 어떤 편향·사전 상태/게이트 변화가 G5 궤적을 그 극단적인 near-pole prior로 이동시켰는지, 이러한 병목이 다른 장면·bias·seed에서도 반복되는지. 본 실험은 사건을 GT로 선정해 후험적 검증한 것이지, 실제 운용시점의 위험 검출기 성능을 측정한 것이 아니다.

**작업 결론:** N4-B에서 즉시 RF 오류 공분산을 더 학습하기 전, Frozen LUT `ρ` near-pole에서 Jacobian-linearized observation 사용의 유효조건을 감사해야 한다. 기존 `near_anchor_pole=ρ<=0.1m`는 로그/품질 신호로만 존재하며 필터에서는 Gate 제한이 없음.

권장 다음 최소 ablation: **원본 R0/G5 전역 결과는 동결**, 별도 실험 분기에서 (a) near-pole estimated geometry diagnostic-only, (b) `ρ`/state position uncertainty 기반 국소 선형화 유효성 guard, (c) 해당 경우 s-only RF 보류 또는 nonlinear measurement likelihood 비교. L0/L1/L2·mount0/45 paired 결과의 Heading·XY RMSE와 Pose NEES 동시 검사. 임계값을 GT-selected 극단 사건에 맞춰 사후 선택 금지.

## 5. 실행 산출물

Artifact `11958301967`의 구조:
- `N4AE_FINAL.json`: 실행 감사 및 compact 결과
- `N4AE_TOP_EPISODES.csv`: 한 연속 episode의 peak/start/end
- `N4AE_PEAK_TELEMETRY.csv`: 같은 극단 시점의 bias/mount/model telemetry
- `N4AE_PEAK_ADJACENT_GEOMETRY.csv`: k908/909/910의 추정 위치, Anchor distance, H, S, λ, NEES (L0/L1/L2 × Mount0/45 × J4/G5)
- `N4AE_LOCAL_SAME_PRIOR_COUNTERFACTUALS.csv`: 같은 prior에서 관측 가중치/평균 보정만 다른 one-step 비교
- `N4AE_EXTREME_VS_OTHER.csv`: 사건 구간과 나머지 평가 구간의 오차·공분산 비교
- `N4AE_GATE_COUNTS.csv`: L0/L1/L2, mount별 gate mismatch 2x2
- `N4AE_ALL_FRAME_ALIGNED_DIAGNOSTICS.csv.gz`: 약 11,748개 원본 정렬 프레임 및 Kalman Gain eigen축 투영
- `N4AE_SELECTED_EVENT_WINDOWS.csv.gz`: ±3초 사건 창의 맞춤 RF·상태 기록
- `PRE_AUDIT.json`, 수학 테스트 및 cloud run 로그

**판정:** `code_audit_PASS=true`, `event_source_parity_PASS=true`, `event_local_mechanism_confirmed=true`, `global_root_cause_confirmed=false`, `N4B_unconditional_GO=false`.
