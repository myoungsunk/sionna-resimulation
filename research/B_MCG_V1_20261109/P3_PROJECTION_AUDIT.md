# P3: 국소 nuisance 투영의 설명력과 한계

## 실행

`audit_projection.py`로 B_FROZEN의 모든 유효 5초 창 **3,061개**를 검사했다. R2 954개, R4 717개, R5 1,390개이다. 각 창은 RF 갱신 전 anchor에서 raw ds/gyro를 적분하고, 현재 target을 제외한 과거 25개 관측만 사용한다. 원본 SourceFFD와 원본 transition을 사용했으며 Q·보정·B detector를 바꾸지 않았다. evaluator truth와 clean RF는 읽지 않았다.

원본 B trace의 고정 `Reff`로 잔차와 Jacobian을 whiten하고, nuisance 좌표를 ±0.5 m, ±0.5 m, ±30°, ±0.2°/s로 정규화했다. `rcond=10⁻³`의 무제약 국소 최소제곱으로 `r_perp=(I−AA†)r`를 계산했다. 이 값은 기술 통계이며 χ² 또는 독립 관측잡음의 확률이 아니다.

## 결과

| Route | 창 수 | nuisance 허용범위 밖의 국소 해 | 투영 후 잔차 에너지 비율 중앙값 | gyro-bias 좌표만 범위 밖 |
| --- | ---: | ---: | ---: | ---: |
| R2 | 954 | 91.30% | 0.5813 | 85.95% |
| R4 | 717 | 74.90% | 0.5393 | 66.25% |
| R5 | 1,390 | 88.99% | 0.6557 | 77.05% |

`A`의 operational rank=4인 창은 각각 850 / 717 / 1,138개다. **rank가 4라는 사실만으로 유효한 물리 범위에서 nuisance가 식별됐다고 볼 수 없다.** 허용범위를 넘는 gyro-bias 및 y 위치 변화로 잔차를 설명하려는 국소 해가 많다.

사전에 정한 매 50번째 유효 창, 총 **63개**에서는 동일한 무제약 해를 clipping하지 않고 exact nonlinear SourceFFD에 넣었다.

| Route | exact 점검 수 | 기준 운동참조보다 잔차 에너지가 커짐 | 허용범위 안의 해 |
| --- | ---: | ---: | ---: |
| R2 | 20 | 16 | 1 |
| R4 | 15 | 4 | 1 |
| R5 | 28 | 19 | 5 |

63개 중 56개는 nuisance 범위 밖의 해다. 따라서 큰 nonlinear 악화 수치를 bounded profile 구현의 실패율로 해석해서는 안 된다. 이 검사는 **국소 선형 투영의 잔차 감소를 실제 모델의 설명 가능성으로 바로 바꾸면 안 된다는 것**을 확인한다. Bounds 안의 7개도 별도로 보고했지만, 표본이 작고 규칙적으로 고른 표본이므로 전체 nonlinear 성공률을 추정하지 않는다.

## 계산 감사

- Retained SVD subspace와 투영잔차의 직교성 오차 최대: `2.45×10⁻¹²`.
- 정규화한 에너지 분해 항등식 오차 최대: `4.74×10⁻¹³`.
- exact 비교 63개 모두 finite, 계산 실패 0개.
- Motion strata는 truth 없이 5초 동안 이동거리 0.02 m, 누적 회전 2° 경계를 미리 사용했다. 현재 3,061개 창은 전부 `TRANSLATING_ROTATING`에 속한다. 이 자료로 정지 또는 5초간 거의 무회전인 별도 strata의 성능을 주장할 수 없다.

## 설계에 주는 의미

작은 `r_perp`는 허용 nuisance 변화와 관측오차의 혼동 가능성을 보여준다. s나 heading을 복원했다는 뜻이 아니다. 큰 `r_perp` 역시 RF 다중경로만의 고유 신호는 아니다. Motion mismatch, 시간변동 bias 등도 별도 원인일 수 있다.

B-MCG는 국소 rank나 선형 잔차 감소만으로 갱신 강도를 결정하면 안 된다. 구현의 bounds 검사, exact nonlinear 재검사, target prediction spread, UNKNOWN 처리가 필요한 이유가 이 자료에서 확인된다. 이 P3 결과 자체로 정책의 순이득을 승인하지 않으며, P4 utility와 실제 폐루프 검증을 별도로 요구한다.

근거: `PROJECTION_SUMMARY.json`, `PROJECTION_WINDOWS.csv`, `EXACT_BOUND_STRATA.json`, `NUISANCE_BOUND_COMPONENTS.json`. 재현 코드: `audit_projection.py`.
