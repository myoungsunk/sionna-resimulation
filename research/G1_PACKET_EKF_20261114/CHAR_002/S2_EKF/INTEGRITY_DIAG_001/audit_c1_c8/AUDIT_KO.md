# G1-INT-001 · KS·C1–C8 코드 감사와 궤적별 실패 원인 (2026-11-16)

- **대상:** `6f8443a` 기준 `continuation_ks/ks_replay.py`, `run_ks.py`(noise_for, read_setup), `continuation_checks_c1_c8/run_followup.py`(C1–C6, C4).
- **방법:** 재생은 하지 않았다. 코드 정독과 저장 trace(Git LFS) 분석만으로 판단했다.
- **분석 스크립트:** [audit_traces.py](audit_traces.py). 실행 방법은 아래와 같다.

```
python audit_traces.py --release <R*_B0_Full_10__evaluator.npz 폴더>
```

## 1. 코드 감사

| # | 항목 | 판정 | 근거 |
|---|---|---|---|
| F1 | Schmidt 갱신 (`_augmented_prior`, `_augmented_update`) | 결함 없음 | 교차 공분산 F·P_nl·α, latent α²P+(1−α²), 항법 gain (P_nn Hᵀ + P_nl Dᵀ)S⁻¹, latent gain 0, 전체 Joseph이 식과 일치. 기존 합성 검사(독립 latent의 주변 일치, GM batch 일치)도 통과 |
| F2 | 분산 예산 `_partition`, causal kernel `_kernel_extra` | 결함 없음 | W 하한 → 빠른 성분 → 느린 성분 순 배정, 합 = R_ref. kernel은 2Σ√(V_iV_j)e^{−Δu/ℓ}이며 10 s / 100 packet 제한. 완전 상관 N개 블록에서 평균 N·V를 재현 |
| F3 | C1 KI | **oracle 한정** | KI가 V3(a) KS 궤적의 패킷별 V_l_op와 causal_l을 그대로 재사용(고정 스케줄). donor 크기로 KI를 돌린 결과는 없음 |
| F4 | C4 `directional` 특징 | **설계 결함** | 특징 H_j²P_jj/R의 P를 학습은 donor E0-LORO prior에서, 적용은 KS 자신의 prior에서 가져옴. 분포가 다르고, P가 R을 바꾸는 되먹임이 생김. `norm_full`과 `norm_xy`는 H만 써서 해당 없음 |
| F5 | 거리 채널 | **설계 공백** | 모든 KS/KI arm에서 거리 채널은 기준선 백색 R_rr 그대로. 편파를 할인하면 거리의 상관 오차가 cross-track과 heading을 끌고 감(§2 R5) |
| F6 | 판정 지표 | **공백** | 단일 앵커의 거울해(y ↔ −y)로 빠지는 branch 실패를 포함률 지표가 따로 식별하지 못함 |
| F7 | 기타 | 경미 | σ_b 조회는 rho_before(직전 posterior), KS 조회는 prior 거리를 씀(E0에서 상속). latent 상관은 이동거리만 쓰므로 제자리 회전에서 α=1 |

**구현 오류로 결과가 바뀐 흔적은 없다.** 다만 F3–F6은 결과의 해석 범위를 제한한다.

## 2. 궤적별 실패 원인

기하: 앵커 B는 (10, 0)이다. 세 궤적 모두 x 1–19 m 복도를 |y| ≤ 0.5 m로 주행하며 앵커 옆을 지난다. 따라서 거리 측정은 주로 x(복도 방향)를 알려 주고, y(cross-track)는 거의 heading을 통해서만 정해진다. y와 −y는 같은 거리를 주는 거울해다.

| 궤적·arm | heading95 | heading / XY RMSE | 통과 5초 전 y 오차 / sd_y | 거울면 반전 |
|---|---|---|---|---|
| R5 E0-LORO | 96.8% | 0.89° / 5.0 cm | 6/7, 3/4, 3/3 cm | 없음 |
| R5 C5 distance | 31.9% | 4.57° / 45.4 cm | **−87/8**, −47/5, −36/3 cm | **1·2회차 통과** |
| R5 C4 norm_full | 34.9% | 4.88° / 39.8 cm | **−81/9**, −44/5, −34/3 cm | **1·2회차 통과** |
| R5 C5 conservative | 100% | 1.21° / 9.0 cm | 7/8, 1/6, 3/3 cm | 없음 |
| R4 E0-LORO | 21.7% | 1.50° / 9.1 cm | **14/4** cm | 없음 |
| R4 V3(a) / C1 KI | 94.3 / 100% | 1.05 / 0.76° · 5.9 / 4.1 cm | 5/4, 4/4 cm | 없음 |
| R2 C5 conservative | 86.4% | **2.53°** / 12.2 cm | 3/10, 6/7 cm | 없음 |

### R5 붕괴: 거울해 고착이며 코드 결함이 아니다

1. **0–30 s, 앵커로 다가가는 구간.** heading 오차가 −2°에서 −7°로 자란다.
   - donor 모수의 latent가 편파의 절대값을 할인한다.
   - 추정 상태에서 heading 감도 |∂s/∂ψ|가 70–110 패킷 평균 −0.02까지 떨어진다(E0-LORO는 0.34). 편파가 heading을 교정하지 못한다.
   - 같은 구간에서 거리→y gain이 −0.33(E0-LORO 0.08)이다. 백색으로 모형화한 거리 innovation의 편향(−2~−6 cm)이 cross-track을 계속 민다.
2. **통과 직전의 과신.** 첫 통과 5 s 전 y 오차는 −87 cm인데 sd_y는 8 cm다(z ≈ 10). 앵커 근처에서 거리가 |y|를 알려 주면서 P_yy가 틀린 쪽 모드에서 줄어든다.
3. **통과 후 고착.** 참 y = +0.44 m에서 추정 y ≈ −0.43 m로 거울면에 고착된다. 거리는 일관되므로 NIS가 작고, gate로 걸러지지 않는다. 이후 b_g 추정이 −0.004 rad/s로 틀어져 heading 오차가 5–7°까지 간다.
4. **비단조성의 설명.** 분산이 큰 conservative arm은 30 s 이후 편파가 감도를 되찾아 통과 전 y 오차를 7 cm로 회복했다. 결과는 통과 시점의 cross-track 오차가 측면 offset(약 0.45 m)을 넘느냐에 달린 분기다. 분산 크기와 단조 관계가 없다.

### R4: 느린 편파 오차의 추종 (기준선 실패)

- **편파가 주원인이다.** E0-LORO에서 오차 방향 heading 갱신 기여가 편파 +9.8°, 거리 +3.0°, 예측 +5.2°다. V4 상관 0.935와 일치한다.
- **cross-track도 과신한다.** 통과 전 y 오차 14 cm, sd_y 4 cm다.
- **크기를 맞추면 사라진다.** oracle 크기(V3(a), C1 KI)에서 둘 다 해소됐다. donor 크기는 근거리에서 oracle의 1/6–1/3.5라 부족하다.

### R2: 편파 할인의 정확도 비용

- conservative arm(×5.43)에서 heading RMSE가 1.19°에서 2.53°로 늘었다. 통과 시 y 오차가 작아 반전은 없었다.
- distance와 C4 norm_full은 R2 기준을 통과했다(heading95 95.5%, 100%).

### C4 pooled 미달의 재해석

- C4 pooled 미달은 R5 거울해 붕괴가 지배한다.
- R2는 norm_full이 통과했고, R4는 norm_full 78.0%로 V3(c)와 같은 수준이다.
- 따라서 "배분 변수 실패"로 읽으면 안 된다.

## 3. integrity에 대한 함의

- **편파 할인은 안전하지 않다.** 이 기하에서는 heading 관측성이 떨어지면 cross-track이 측면 offset을 넘고, 앵커 통과에서 거울해로 비가역적으로 실패한다. "덮일 때까지 R을 키우는" 방식은 R4에서 통하지만 R5형 구간에서는 위험하다.
- **integrity 해의 조건은 두 쪽이다.** (i) R4형 느린 오차에는 충분한 팽창이 필요하다. (ii) 그 팽창이 다른 구간의 heading 관측성을 거울해 경계 아래로 떨어뜨리면 안 된다.
- **판정에 branch 실패를 명시해야 한다.** 앵커 통과 전 y 오차/sd와 거울면 반전을 별도 실패 조건으로 등록할 것을 권한다.

## 4. 남은 확인 (integrity 우선)

| # | 확인 | 이유 |
|---|---|---|
| N1 | **KI에 donor 크기를 넣은 재생** (distance, ×k, C4 norm_full 크기). R2/R4/R5 전체, 통과·반전 지표 포함 | C1의 KI 우위는 oracle 스케줄에서만 확인됐다(F3). 1차 구조 후보를 실제 이전 조건에서 시험 |
| N2 | **R5 분기 확인:** C5 distance에서 0–45 s만 E0-LORO 가중을 쓰고 이후 KS로 전환. 반대 순서도 실행 | 붕괴가 접근 구간의 heading 손실에서 시작된다는 인과 확인 |
| N3 | **거리 채널 상관 오차:** 편파를 할인한 arm에 거리 느린 성분 KI를 추가 | F5. 거리 편향이 cross-track을 미는 경로 차단 |
| N4 | **F4 수정:** C4 directional을 donor와 같은 정의의 P로 재적합하거나 폐기 | 되먹임 제거 |
