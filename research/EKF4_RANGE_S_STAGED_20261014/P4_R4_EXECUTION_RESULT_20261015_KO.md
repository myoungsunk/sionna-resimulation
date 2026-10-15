# R4 P4 동결 RF 전체 One-Step 실행 결과 — 2026-10-15

## 결론

**P4 고정 선형화: 기술적 PASS. P4 비선형 MAP: 전수 평가 완료, numerical validity 미충족.** `scientific_PASS=false`.

실행 [GitHub Actions Run 38658117256](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38658117256), source `46d679a32f55cae460d9ed35b4bb944bc48cc4ce`. 원 frozen RF [artifact 11782748118](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118) 및 P3 검증 [artifact 11904127597](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38583064582/artifacts/11904127597)를 source SHA+ZIP SHA+CRC로 확인. P3 기존 소스의 독립 SHA와 현재 코드 SHA 일치 확인. 실행 **전 감사 GO/fatal 0**, math regression **13/13 PASS**, 대표 canary/전체 fixed/MAP/오프라인 scoring/독립 결과 감사 순으로 성공적으로 실행.

원시 결과 [artifact 11937707221](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38658117256/artifacts/11937707221), ZIP SHA256 `db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4`; **4,205 files**, ZIP CRC PASS. 최종 `P4_FINAL.json`: `status=P4_COMPLETED_WITH_SCOPED_NUMERICAL_INVALIDS`, `exit_code=0`, `audit_errors=[]`, `fixed_technical_PASS=true`, `full_MAP_numerical_PASS=false`. Results contain 4,124 raw model-specific failure snapshots and SHA256 manifest for 4,184 files.

## 1. Frozen input & assumptions

- 총 7 case × LoS/Full=14 traces, seed0 `noise_pair`, 14,502 timesteps. 범위 단일 corridor, archive original EKF3 one-step; **one-step counterfactual이지 full recursive RF fusion 아님**.
- 원 3-state DR-only `mu3,P3`에서 `mu4=[mu3,0]`, `P4=diagblock(P3,(0.1°/s in rad/s)²)`라는 zero-cross augmentation. H_b=0; 따라서 J3/J4 pose 동일. One-step에서 b=0으로 남는 것은 정상 동작이며 gyro bias의 실제 재귀 추정은 P6.
- Original 2D R0 joint gate 9.210340371976184, archived sensor `[s,r]`→P3 canonical `[r,s]`. `Rs=0.0081`, `Rr=0.0068578637m²`, `Rrs=0`(독립성 미보정), `B_old=-0.5315983906250129m`. Same prior/gate in all arms.
- Joint reference LoS original all 7,251 accepted; Full 6,935 accepted + 316 rejected; **14,186 accepted + 316 rejected = 14,502**. Evaluation window `t>=30s` LoS 6,201 and Full 6,201 timestamps; Full 304 rejected there.

## 2. P4 fixed-linear mathematical results

- Canaries 80 case/time combinations inspected, MAP 18 numerical-invalid outcomes (M4-P9, M4-R9), fixed methods valid.
- J3 vs original archived joint C posterior, J3 vs J4 pose, J4 vs range-first frozen sequential and s-first frozen sequential all pass on 14,502 timelines.
- Largest frozen-state/covariance parity discrepancy **3.552713678800501e−15**. Source J3 original comparison max pose similarly `3.552713678800501e−15`. No hidden gate difference, no RF double counting, no state carry-over.
- Under zero pose–bias cross prior, `K_b=0`, no one-step bias information added, as required. Synthetic SPD prior with nonzero pose–bias cross confirms b CAN be updated indirectly, but was not substituted into real frozen RF comparison.
- `P4_FIXED_LINEAR_PARITY_PASS`. Success does NOT mean nonlinear estimator science or RF calibration PASS.

## 3. Full MAP numerics

P4 ran `M4_P` (original prior initialization) and `M4_R` (Range-first initialization with identical posterior). P2 R4 MAP solver was unmodified: `max_iter=80` and `||grad_y J||inf<=1e−8`.

| Channel | Gate-eligible steps | Total model attempts | Converged | Invalid | Invalid share |
|---|---:|---:|---:|---:|---:|
| LoS | 7,251 | 14,502 | 12,618 | 1,884 | 12.99% |
| Full | 6,935 | 13,870 | 11,630 | 2,240 | 16.15% |
| **Total** | **14,186** | **28,372** | **24,248** | **4,124** | **14.54%** |

- 실패 원시 출력 4,124개 개별 JSON에 exact `prior_mu4,P4,z,R,h,H,NIS,case,channel,k,t_s` 및 MAP original status/iteration/gradient/history를 저장. **No result fallback, no made-up RMSE**.
- 실패 종류: **`LINE_SEARCH_FAILED` 3,369**, **`MAX_ITERATIONS` 755**.
- 실패 최종 gradient∞ 중위수 `0.0206042`, Q1 `0.003298`, Q3 `0.053071`, 최대 `1.68612`; 이는 전형적 P2 `1e−8` 주변 비용 상쇄만으로 설명되지 않는다. 원인은 LUT piecewise-linear Jacobian discontinuity, 별개 모드/local chart, line-search 수용 등을 **새 고정입력 진단으로 확정해야 하며 아직 확정하지 않았다**.
- 실패 비중이 시간별/채널별 상이하므로 converged-only MAP 성능은 선택편향 가능성. 같은 기준과 공통 성공 마스크를 갖지 않는 전체 Joint EKF RMSE와 직접 superiority 비교 금지.

## 4. Offline truth evaluation (평가 전용)

원본 prior 기준 동결 one-step의 `t>=30s`별 모든 평가 시점을 원시 기록에서 재산정(각 mode 6,201 frames); 시간/seed 독립 scene인 척 bootstrap하지 않는다. 값은 시점별 squared error 합산으로 pooled RMSE 산출.

| Channel | Model | Position RMSE (m) | Heading RMSE (deg) | 평가 시점 |
|---|---|---:|---:|---:|
| LoS | D0 DR-only | 0.159116 | 0.496008 | 6,201 |
| LoS | J3/J4/SF4-R/SF4-S | 0.172392 | 0.751107 | 6,201 |
| LoS | SR4 relinearized | 0.175731 | 0.774252 | 6,201 |
| Full | D0 DR-only | 0.159116 | 0.496008 | 6,201 |
| Full | J3/J4/SF4-R/SF4-S | 0.573523 | 2.345435 | 6,201 |
| Full | SR4 relinearized | 0.581340 | 2.384062 | 6,201 |

이번 R0 조건의 Joint RF 갱신은 LoS/Full 모두 좋은 DR-only prior보다 악화했다. SR4 relinearization도 개선하지 못했다. Full 악화를 숨기거나 gate/R을 다시 맞추지 않았다.

**MAP 성공 부분집합만의 조건부 결과(전체 비교에 사용할 수 없음):**

| Channel | M4-P evaluated | M4-R evaluated | M4-P / M4-R Position RMSE | M4-P / M4-R Heading RMSE |
|---|---:|---:|---:|---:|
| LoS | 5,357/6,201 | 5,353/6,201 | 0.153564 / 0.153352m | 0.649981 / 0.650093deg |
| Full | 5,196/6,201 | 5,200/6,201 | 0.594129 / 0.593146m | 2.466002 / 2.464277deg |

`t>=30` MAP numerical invalid model-attempts = **3,698**. 위 MAP은 성공 집합이 원본 Joint/DR 전체와 달라 정확도 이득을 입증하지 않으며, MAP local GN covariance를 다봉 posterior covariance로 주장하지 않는다.

## 5. 완료·미해결 및 다음 진단 계약

- **완료:** 사전 감사, 동결 P3 영수증, 수학 13개, canary, 14,502 fixed all, 28,372 MAP attempts, post inference truth-only scoring, raw artifact read-back SHA/CRC and case counts.
- **수치 미해결:** R4 솔버의 LUT 기반 MAP nonconvergence. 4,124개 결과는 명시적으로 `CASE_RESULT_INVALID_NUMERICAL`. 신규 소스·원본 데이터 수정 없이 대표 실패를 골라 geometry/LUT knot proximity, one-sided vs central finite differences, GN descent direction, gradient-integral vs signed true cost, local Hessian, chart/mode를 **실행 전 감사 이후** 독립 진단. 실패를 간단히 `10−14`만의 문제로 처리하거나 gradient tolerance/Q/R/gate 변경 금지.
- P5 historical position-integrated G3 TV 0.387065>0.001 remains unresolved. P6 recursive RF results NOT_RUN in this branch.
- `scientific_PASS=false`. P4 fixed math pass와 RF performance/independent-scene claims는 분리한다.

**최종 판정:** `P4_FIXED_LINEAR_PARITY_PASS=true`, `P4_NONLINEAR_ONE_STEP_EVALUATED=true`, `full_MAP_numerical_PASS=false`; 4,124 cases scientific result invalid, preserved exactly.
