# D3 최종 — P2 저장된 네 미수렴 사례의 수치 원인 확정과 RF/DR 영향 분리
> **용어 정정(D3B):** 이 문서의 `r_DR_prior=h_r(mu^-)`는 RF를 전혀 사용하지 않은 **독립 DR-only**가 아니라, 이전 RF 융합을 포함한 **MAP prior**의 거리 예측이다. 이 문서의 4/4 비교는 **MAP prior vs 현재 RF**에 한정된다. 후속 [D3B 독립 DR-only 분리 재검증](D3B_DR_ONLY_MAP_PRIOR_RF_FINAL_KO.md)에서 **RF가 순수 DR-only보다 정확한 경우 3/4, MAP prior보다 정확한 경우 0/4**임을 확인했다. 네 솔버 미수렴의 수치 원인은 변하지 않았다.\n\n작성일 2026-10-14 | **범위: 네 개의 보존된 합성 P2 MAP 실패 입력, 새로운 알고리즘/재귀 평가 없음.**

## 1. 감사·실행 및 출처
- D3 실행 브랜치 `research/ekf4-d3-four-failure-rootcause-20261014`.
- 기준 소스: EKF4 `2781ee299f6908399acbb6bec91efb6e81cdc366` 및 원 cloud run `38526390416`의 frozen `core.py`, `stable_descent.py`, `synthetic.py`, `P2_SPEC.json`. 이 파일들을 변경하지 않았다.
- 재현 대상: [P2 원본 아티팩트 ID 11875912063](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526390416/artifacts/11875912063), SHA256 `d25e96077a6b487fd0d90591362e141ee3908457808edf8688a7d3a480bad26b`.
- 새 [D3 GitHub Actions Run 38530999947](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38530999947), `success`. GitHub-hosted Python 3.11.11, NumPy 1.26.4, SciPy 1.13.1, mpmath 1.3.0.
- 실행 **전에** 소스·진단 코드 감사 `SOURCE_AUDIT.json: GO (14 checks)`, 원본 네 NPZ/JSON·source identity/CRC 감사 `INPUT_AUDIT.json: GO (10 checks)`. 초기 자동 감사 run `38530906878`은 workflow command 검색의 과도한 정적 규칙이 파일 경로 선언을 명령으로 착각하여 `HOLD`; 그 감사 코드만 수정하고 새로운 run에서 재검증. 원 FAIL 기록은 변경하지 않았다.
- [D3 원시 아티팩트 ID 11877607344](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38530999947/artifacts/11877607344), SHA256 `a8258567bd04d4178cd8dbe7f2dc19b242bea7ddc209c972a963c99a787bfca9`. 다운로드 아카이브 SHA256·ZIP CRC 독립 읽기 확인.
- 본 작업은 원 저장 입력을 다시 읽은 **고정 입력 수치 진단**이다. 원 P2 전체 600 trial과 새 R3 solver, RF G2/G3, 실제 RF 측정은 실행하지 않았다.

## 2. 확정된 주요 수치 원인 — 네 건 모두 같은 형태
기존 목적함수는 `J(y)=0.5*(||y||² + ||L_R^-1[z-h(mu+L_P y)]||²)`. 현행 `R2 core.map_update`는 float64로 비용을 평가하고, `ARM IJO_DIRECT` 라인서치가 먼저 시험된다. 직접 acceptance가 실패할 때의 별도 적분 가드는 `abs(J_new-J_old)<=64eps*scale` 등의 좁은 조건을 요구한다.

원 실패 지점에서 **full Gauss–Newton step 하나**를 적용한 비교:

| 경로/모델, 시간 | 실패시 `||g||∞` | float64 `ΔJ` | 80자리 독립 `ΔJ` | full GN 후 `||g||∞` |
|---|---:|---:|---:|---:|
| straight/MAP3, 28s | 1.296329e-8 | +8.337775e-14 | **-1.618216e-16** | 9.448545e-11 |
| straight/MAP4, 30.5s | 1.776606e-8 | +6.972201e-14 | **-2.606232e-16** | 1.939978e-10 |
| turn/MAP3, 32s | 1.221433e-8 | +5.151435e-14 | **-7.435726e-17** | 8.469558e-11 |
| return/MAP3, 32s | 1.666096e-8 | +5.462297e-14 | **-2.464183e-16** | 1.438006e-10 |

네 건 모두 독립 80자리 물리 전방식과 posterior gradient 계산에서 **실제로 목적함수를 감소**시키는 full GN step이 존재하며, **원 수렴 기준 1e-8**을 바꾸지 않고 통과한다. 별도의 고정밀 stationary point도 모두 존재한다. 역오차 재구성 `||y_reconstructed-y_saved||∞ <= 1.2e-16`; 원 R2 코드의 `LINE_SEARCH_FAILED`가 재현됨.

**확정 원인:** 기존 double 정밀도 목적함수 값의 미세 차가 실제 감소의 부호를 뒤집어 `full GN step`을 허용하지 못한다. 코드는 대신 아주 작은 fraction(2^-24 등)을 수용하고 여러 번 반복하여 gradient가 1e-8 근처에서 정체된다. 사용된 GN 정보행렬 조건수는 약 1.04–1.07로, 네 사례에서 심각한 선형계 악조건이 원인이라는 증거는 없다. 원 정규화 objective를 변경할 필요성도 드러나지 않았다.

**이전 부정확한 추정 수정:** MAP4 기록에 float64 `J` 증가 후 `ARMIJO_DIRECT` accept된 step이 존재했기 때문에 이전 보고서에서는 '실제로 올라가는 스텝을 승인한다'는 가능성을 제기했다. 그러나 저장된 전체 승인 스텝을 80자리로 다시 계산한 결과 **진짜 목적함수를 증가시킨 승인 스텝은 네 사례 모두 0건**이다. 따라서 확인된 문제는 **거짓 양의 step 수용**보다, **유효한 큰 step의 거짓 기각→미세 step 후퇴→정체**이다. float64 값이 증가한 듯 보였던 것은 정밀도 부족에 의한 부호 오류였다.

추가로 기록된 `roundoff=4eps*max(1,|cost|)`와 적분 guard의 `64eps` 조건은 실제 P2 소스에 존재하는 제한이다. 이 조건들이 특정 입력에서 어떤 branch로 진입하는지 원시 history와 코드로 대조했다. **전체 네 건의 정확한 스텝 규모는 1e-8 근방(백색화 좌표)**이며 비용 변화는 1e-16 수준이라 float64 비용값의 직접 뺄셈만으로 종결을 보장할 수 없다.

## 3. DR–RF 불일치가 네 수치 실패를 유발했는가?

현재 연구 P2는 `SyntheticRF` (matched model, Range noise SD 0.05 m, gate OFF)이고, 별도 `research/rf-range-sign-audit-g2g3-20261014`는 실제 동결 RF 교정 출력·DR-only 비교 연구다. 서로 다른 조건/실험이다. 진단은 P2 저장 prior에서 `r_DR=h_r(mu^-)`, `r_RF=z_r`, `r_true=h_r(truth)`를 독립 계산했다. **truth는 사후 점수에만 사용**.

| 실패 | 실제 Range | MAP prior 예측 Range | RF Range | MAP prior 절대오차 | RF 절대오차 | Range NIS |
|---|---:|---:|---:|---:|---:|---:|
| straight/MAP3 | 8.633078m | 8.622149m | 8.682670m | **0.010930m** | 0.049591m | 1.3939 |
| straight/MAP4 | 9.106201m | 9.101890m | 9.002875m | **0.004311m** | 0.103327m | 3.7352 |
| turn/MAP3 | 8.858883m | 8.853999m | 8.936751m | **0.004884m** | 0.077868m | 2.6033 |
| return/MAP3 | 8.633078m | 8.622081m | 8.532245m | **0.010997m** | 0.100834m | 3.1053 |

- MAP prior–RF 차이 크기는 **0.0605–0.0990m**, Range 관측 표준편차 0.05m의 약 1.2–2.0배다. 기존 Range NIS 99% 참조 기준 6.6349를 넘는 케이스 **0/4**.
- **RF보다 MAP prior 거리 추정이 정확한 케이스 4/4.** 이 네 결과에 대해 RF 우선 가중치를 주장할 근거가 없으며 적용하면 오히려 측정 거리의 참오차를 더 신뢰하게 되는 문제가 생길 수 있다.
- 동일 원 prior/R/Q에서 관측 Range만 prior 예상값과 일치시키거나 `s`만 예상값과 일치시키는 **반사실적 진단**은 네 경우 모두 solver가 수렴했다. 이는 유한한 관측 잔차가 있을 때 float64 비용 정밀도 문제가 드러난다는 것을 설명하지만, 큰 DR drift가 수치 오류의 유일 원인이라는 증거는 아니다. 원 입력에 대한 정확한 수치해 존재가 별도로 확인됐다.
- **결론:** 별도 RF 연구의 핵심 사례(수 미터 DR 과대예측 / RF 0.06m 오차)와 본 P2 네 사례는 구조적으로 다르다. 이 네 경우에는 **'RF가 DR보다 정확하니 RF 우선' 규칙을 적용하지 않는다.** Heading·pose 전체 RF 성능 비교는 이 진단으로 결정하지 않는다.

## 4. 별도 RF 연구가 필요한 상황과 향후 반영 — P2와 별도

[별도 RF 연구 브랜치](https://github.com/myoungsunk/sionna-resimulation/tree/research/rf-range-sign-audit-g2g3-20261014) `e7ee115836bc...`의 원 보고:
- R2_aA_m0/L2/sample978에 대해 `r_true=3.60873`, `z_RF=3.67220`, `r_DR=6.41465` m (RF 상대적으로 훨씬 좋음).
- 그러나 Full/E1에서는 RF가 과소보정되어 DR보다 나쁜 반례 존재.
- 이것은 **향후 RF 관측 신뢰 모델을 고르는 참고 증거**이지, 본 D3에 구체적인 signed-Range/DR-fault/G2/G3 구현 방식을 복제하라는 지시가 아니다.
- 향후 실제 큰 DR–RF 충돌 조건에 한정해 RF가 독립 품질 지표·검증으로 우위에 있는 경우 RF likelihood 영향력을 유지/증가시키고, DR bias/fault와 RF outlier를 분리 검토한다. `RF shorter`/큰 NIS만으로 무조건 RF를 채택하지 않는다. 그 구현은 **별도 방향 결정 이후**, 이 연구 P2 원 조건과 독립적으로 시작한다.

## 5. 다음 원인 기반 수정(미실행)
현행 `core.map_update`와 `stable_descent.py`에서 **큰 유효 GN step이 float64 직접 비용 비교로 탈락하는 경로**를 수정 후보로 둔다. 예를 들면 우선 gradient/방향미분의 검증된 감소를 판단하고 직접 비용이 정밀도 바닥 아래면 높은 정밀도/잔차 변화형 안정식으로 교차 검사한다. **단순히 64eps 한도를 확대하거나 수렴 기준을 완화하는 것은 이번 결론으로 정당화되지 않는다.** 실제 R3 solver 선택/코드 수정 전 해당 변경이 조작할 수 있는 step·posterior·기각율을 사전 감사해야 한다. 동일 네 입력 → 음성 대조 → 작은 재귀 대표 → 전체 P2 순서. 이번 D3에서는 이 조치를 실행하지 않았다.

## 6. 확정 / 미확정 / 종료
**확정(이 네 합성 고정 입력):** 원 코드의 실패 재현, 독립 80자리 비용·gradient 일치, full GN의 유효한 감소 및 기존 기준 충족, 독립 stationary root 존재, float64 비용 부호 반전과 미세 step 정체, 입력 네 건에서 큰 DR–RF radial conflict 없음, RF보다 DR distance 참오차 작음.

**미확정:** 다른 seed/경로·나머지 시점에 대한 solver 수렴 보증; 실제 Full RF, correlated multipath 및 RF/DR 신뢰도 모델; 새 R3의 동작; MAP4의 과학적 bias 개선/불확실성 일관성; G2/G3 정밀 posterior.

**최종 상태:** `D3_SOURCE_AUDIT=GO`, `D3_INPUT_AUDIT=GO`, `D3_FOUR_CASE_NUMERICAL_CAUSE=SUPPORTED`, `R3=NOT_RUN`, `P2_FULL=NOT_RUN`, `P3–P6=NOT_RUN`, `scientific_PASS=false`. 요청한 진단 범위에서 종료.
