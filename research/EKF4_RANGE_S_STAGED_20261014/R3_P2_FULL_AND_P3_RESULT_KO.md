# R3 → P2 전체 최종 합성 결과 및 P3 입력 감사 판정

## Provenance
- R3 실행 code commit `d11317b51e2ab4cedcb3dbc760822b4f0af9382a`
- P2 [GitHub Actions Run 38555752075](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38555752075), artifact [11888849050](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38555752075/artifacts/11888849050), ZIP SHA256 `580ad1fda06902aaa884d6b37ceb8882a9cf0644858e081e413315f271e4b914`
- 원 `P2_SPEC.json`과 `synthetic.py` 동결, R3 코드만 변경. 모든 단계 전 동일 Git SHA 소스 감사 GO; P0/P1, R1/R2, D3 저장 4 failure regression, representative, full P2 순서로 실행.
- Full 결과 `2400/2400` model-runs, `600/600` four-model paired trials; invalid cases=0. `scientific_PASS=false`는 실제 RF 일반화/외부 장면까지 검증되지 않았다는 의미.
- P3 [GitHub Actions Run 38556465417](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38556465417), artifact [11888714289](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38556465417/artifacts/11888714289) SHA256 `a036bb9d13e0b161788156fc6d476f30b75c1f17af16def5844b0da6c492b069`. 원 P0 입력 39개 해시/shape/pose 정합 PASS. P3 판정은 **자료 적격성**이며 estimator scientific PASS는 아님.

## P2 100 independent noise trials per route/bias · 60s each · matched SyntheticRF
| 경로 | 실제 bias | MAP3 heading RMSE (deg) | MAP4 heading RMSE (deg) | MAP3 95% heading 포함률 | MAP4 95% 포함률 |
|---|---:|---:|---:|---:|---:|
| straight | 0 | 0.442464 | 0.559352 | 95.21% | 96.88% |
| turn | 0 | 0.447961 | 0.584904 | 95.62% | 96.58% |
| return | 0 | 0.451831 | 0.570933 | 95.32% | 95.57% |
| straight | +0.05deg/s | 0.996146 | 0.569906 | 35.14% | 96.42% |
| turn | +0.05deg/s | 1.032944 | 0.591811 | 37.42% | 96.49% |
| return | +0.05deg/s | 0.956279 | 0.573812 | 37.53% | 95.68% |

MAP4-MAP3 paired Heading MSE changes (deg²) at bias +0.05deg/s:
- straight -0.667514, bootstrap 95% CI [-0.722206,-0.614857].
- turn -0.716734, bootstrap 95% CI [-0.786106,-0.650154].
- return -0.585209, bootstrap 95% CI [-0.644793,-0.527816].

All three are SUPPORT **only for the matched synthetic bias-positive claim**. At bias0, all three route RMSEs worsen significantly; adding an unnecessary bias state costs accuracy. At both biases `MAP4 vs EKF4` paired MSE CI include zero; solver iteration has no demonstrated incremental heading accuracy gain over 4state EKF in these conditions.

**Not independently established:** actual Full multipath/RF model mismatch, independent scene generalization, calibrated bias prior, complete nonlinear posterior or observed gyro bias inference robustness. Temporal samples within trial are not independent bootstrap units. Real RF gate false rejection and signed RF range findings remain separate research.

## P3 and next dependencies
- P3 frozen RF source/shape/pose-ready under original P0 input and observer/LUT rules. No need to reexecute P2 because P3 is logically input-eligibility independent.
- P4: actual LoS/Full identical-prior single-step 4-state joint vs sequential vs MAP relinearization, no final scientific claim until raw inputs/gate policy/solver source audit.
- P5: position-integrated nonlinear/multimodal reference; original G3 quadrature TV 0.387>0.001 remains FAIL. A local EKF/MAP cannot replace its probability reference.
- P6: recursive real RF evaluation only when necessary P4/P5 branches valid; generalization claim still requires held-out RF scenes and calibrated model errors.
