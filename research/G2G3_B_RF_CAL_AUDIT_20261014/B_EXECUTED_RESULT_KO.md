# B 추가 검증 최종 기록 — RF 오차 지표와 RF–DR 거리 우위 확률
날짜: 2026-10-14
코드 브랜치: research/g2g3-B-rfcal-audit-20261014
최종 평가 코드 commit: 1a555ee7a1399ab1334178ce1a818312e78aa8be
최종 Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38545314173
최종 Artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38545314173/artifacts/11884710190
최초 TypeError 실행/실패 보존: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38545120474
사전 리뷰: SOURCE_REVIEW_KO.md; source-bound audit PRE_RUN_{bootstrap,fixture,acquire,evaluate}.json
소스 코드: b_audit.py; 수식 계약: CONTRACT.json
source audit standard: 9beb061f354edef18e1f977f5d462d7e0d8b1f2e

## 핵심 결론
(1) RF error metrics can inform an RF error distribution, but **cannot alone equal the event probability that RF beats DR**. To infer that event requires the joint error model including the DR uncertainty and the measured DR–RF distance difference.
(2) Method-wide RF signed Gaussian is a valid toy density, and event-probability algebra passed independent quadrature with max difference 2.220446049250313e-16 over six fixtures.
(3) Cross-route heldout tail coverage and probability reliability show **substantial failures**, especially E1's long negative tail and a misspecified DR fault distribution at L2. Consequently these are NOT calibrated probabilities on independent RF scenes.
(4) Only Stage B numerical/diagnostic validity is PASS; independent-scene calibration and practical online fault/CIR quality dependence are CLAIM_BLOCK. G2/G3 actual nonlinear performance/recursive pose is not run.

## B.1 RF signed error indicators (6,201 unique RF rows per model)
epsilon_R=z_RF-r_true. Negative error is a shorter-than-true corrected RF distance.
| channel/model | mean (m) | sd (m) | RMSE (m) | P(epsilon<0) | P(epsilon<-.10m) | P(epsilon>+.20m) | q05 (m) | q01 (m) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LoS/B_OLD | -0.0026 | 0.0459 | 0.0459 | 51.70% | 0.34% | 0% | -0.0737 | -0.0915 |
| Full/B_OLD | +0.0503 | 0.1276 | 0.1372 | 34.27% | 3.39% | 6.76% | -0.0865 | -0.1328 |
| Full/E1 | -0.0049 | 0.1066 | 0.1067 | 59.15% | 9.71% | 2.89% | -0.1307 | -0.1943 |

- Bias/scale are ingredients of signed likelihood f(epsilon|Q).
- Negative/positive tails and bounded error probabilities are distinct indicators for possible over-correction vs multipath excess.
- Empirical q05/q01 permit a descriptive one-sided distance upper-margin tau_95/99, but ARE NOT route-independent confidence guarantees.
- RF-quality indicator candidates for later audit: CIR first/peak, leading-edge confidence, delay between first and peak, first-path/total power, RSSI/noise/SNR, path delay spread. The archived A ZIP does not include these CIR metadata values. No predictive claim about them was evaluated in THIS run.

Observed corrected-range bin conditional P(epsilon<-.10m):
| channel/model | z_RF<5m | 5<=z_RF<10m | z_RF>=10m |
|---|---:|---:|---:|
| LoS/B_OLD | 0% | 0.46% | 0.80% |
| Full/B_OLD | 2.37% | 5.07% | 2.26% |
| Full/E1 | 0.62% | 9.85% | 27.95% |

Range bin conditioning is useful as a DESCRIPTIVE risk predictor. It **cannot** be inserted naively as f(e|z_bin) in a generative p(z|r,Q), because z_bin is a function of z and the conditional selection/normalization must be accounted for. Q may also be correlated with DR geometry and S likelihood.

## B.2 Cross-route calibration diagnostics
For each RF method we fitted signed Gaussian mu/sigma and empirical one-sided error quantiles using OTHER routes; evaluate on one heldout route. RF scene overlap persists: this is not the frozen 0.5m spatial independence requirement. Original H3 feasibility has zero valid training observations for held-out R2 and R5 in that strict split.

Selected heldout tail results:
- LoS/B_OLD heldout R2: nominal 95% one-sided cover = 91.11%; nominal 99% cover = 97.02%. Heldout R4: 97.89% / 100%; R5: 96.48% / 99.68%.
- Full/E1 heldout R2: 94.45% / 99.92%; R4: 96.71% / 98.40%; R5: 94.27% / 98.02%.
- Full/B_OLD heldout 95% cover ranged 94.34% to 95.49%, 99% cover 98.74% to 99.24%.
Thus route transfer is not stable enough to assert independently calibrated 95/99% bounds. Full/E1 route-out normal PIT KS statistic ~0.1696–0.2452 also shows substantial Gaussian fit problems.
No parameters/tolerances were retrospectively changed based on these results.

## B.3 Mapping error distributions to RF superiority probability
Define e_D=d-r_true, e_R=z-r_true and delta=d-z=e_D-e_R.
The event for RF strictly better in radial absolute error is
delta>0: e_R> -delta/2
delta<0: e_R< -delta/2.
Therefore the correct general posterior is based on the JOINT error density:
p(e_R | delta,Q,U) proportional to p(e_R,e_D=e_R+delta |Q,U).
If conditional independence is justified, only then factor:
p(e_R | delta,Q,U) proportional to f_R(e_R|Q) f_D(e_R+delta|U).
For delta>0:
P_RFbetter= [integral from -delta/2 to +inf f_R(e|Q)f_D(e+delta|U)de] /
           [integral from -inf to +inf f_R(e|Q)f_D(e+delta|U)de].
For delta<0 use integral -inf to -delta/2.

Trial independent Gaussian components:
e_R~N(mu_R,sigma_R²), e_D~(1-pF)N(0,sigma_D²)+pF N(0,sigma_D²+sigma_F²).
sigma_D² was reconstructed by subtracting frozen Rr ONCE from the archived sigma_innovation² (do not double count Range). pF=0 and pF=0.05,sigma_F=2m from PREVIOUS synthetic fixed contract; neither is calibrated.
For each DR component var_D, var_R, the conditional normal for e_R | delta:
V=var_D+var_R;
mu_post=(mu_R*var_D - delta*var_R)/V;
var_post=var_D*var_R/V;
weight_i proportional to pi_i Normal(delta; -mu_R, V).
Normal CDF over the corresponding half-line gives direct P_RFbetter.
Independent direct quadrature checked 6 cases, max p difference 2.22e-16.

### Probabilities are NOT yet calibrated
Leave-one-route-out method-wide Gaussian RF signed likelihood + prior trial scored on archived 223,236 paired rows, reusing RF across sensor conditions/seeds:
- Full/E1 nominal DR: Brier 0.2280, ECE 0.1270, high-confidence pwin>=0.95 selections 4,196, of which 117 RF-worse cases (2.79%).
- Full/E1 synthetic fixed 5% fault prior: Brier 0.2282, ECE 0.1268, high-confidence selections 5,325, of which 497 RF-worse cases (9.33%).
- Full/E1 gyro_bias L0 with fixed fault prior: 121 high-confidence selections and all 121 had RF worse. pwin>=.95 does NOT imply actual 95% correctness in these groups.
- LoS/B_OLD nominal Brier 0.1768, ECE 0.0559 over condition-aggregated paired rows (still spatial overlap).
These numbers are descriptive model validation scores only, not independent samples or production-grade probability calibration.

Under the more restrictive *RF shorter AND old NIS rejected* subset, some high-confidence selections are correct in this frozen data (e.g. gyro L2). But low-bias and RF longer controls remain necessary; a high pwin flag cannot guarantee an unconditional posterior mean is safe.

## B.4 DR fault prior cannot remain a fixed narrow Gaussian
Across archived DR-only predictions (LoS/B_OLD representative; conditions/paths reused across antenna cases):
Fraction where |DR radial error / DR prior predicted radial std| > 1.96:
- noise_pair L1 = 0.40%
- gyro_bias L0 = 0.37%
- gyro_bias L2 = **25.87%** (R2 31.26%, R4 1.01%, R5 32.21%).
Thus original DR prior confidence is very different across gyro conditions, with gross L2 undercoverage on R2/R5. A global fault rate 5% and width 2m chosen for synthetic trials cannot yet be called calibrated. p_fault(U) should be derived from ONLINE gyro/wheel incremental statistics, elapsed motion, turn geometry and reliability, and calibrated on independent heldout routes/scenes. Actual injected fault class/true bias cannot be used as a live feature.

## Four separate verdicts
1. **EXECUTABLE**: PASS for B-only cloud run 38545314173, exact approved source and archived input checks.
2. **NUMERICAL_VALIDITY**: PASS only for six analytical vs independently integrated pwin formula fixtures, and correctly computed descriptive route-out RF/DR scoring. Does NOT establish a calibrated likelihood.
3. **HYPOTHESIS_SUPPORT**: RF error indicators have distinct signed/tail/condition heterogeneity; RF-only accuracy metrics do not equal RF-vs-DR win probability. The hypothesis that the previously synthetic pF=.05 yields calibrated .95 event probabilities is NOT supported in pooled/low-bias subgroups.
4. **SCIENTIFIC_CLAIM**: CLAIM_BLOCK for independent scene calibration of f_RF, gyro/CIR-conditioned pDR fault probability, robust G2/G3 actual position/heading, and external generalization.

## Source audit and bounded repair chain
Initial Python script draft commit 4ccffcdf had an undefined second-component fault variable, detected by assistant SOURCE REVIEW and fixed in commit 96da3e63 before first cloud run.
First cloud run 38545120474 independently verified six formula fixtures and archived zip SHA but hit duplicated 'train_n' report keyword (TypeError) before completing route diagnostics. This was a **DIAGNOSTIC_DEFECT_OR_WARNING**, not mathematical model invalidity.
Fix commit 6ca9b9cf removed only duplicate output keyword, no change to likelihood, signed error values, tests, 0.95 threshold or training scope. Amended source approval and cloud rerun completed: 38545314173, artifact 11884710190.
Pre-run gate records before bootstrap/fixture/acquire/evaluate all GO_WITH_CLAIM_LIMITATION.

## Next B calibration validation (not yet completed)
To actually establish probability calibration:
(1) generate NEW independent RF scenes and Anchor placements, including heldout R2/R5 with 0.5m buffer, and take CIR raw quality Q at runtime.
(2) signed, normalized RF likelihood p(z_r,Q|r,channel) or properly normalized p(z_r|r,Q); choose robust signed tails and test PIT, heldout 95/99% coverage.
(3) calibrate DR p(e_D|U) / fault prior from online gyro/wheel/motion, not truth or manually known injected bias labels.
(4) capture cross-error dependence p(e_D,e_R|Q,U) if significant; independent product is only a tested approximation.
(5) heldout reliability diagram/Brier/log loss for p_RFbetter and low-bias false-confidence guardrail, then pose/Heading G2/G3.
Until then Stage B = DIAGNOSTIC_COMPLETE_WITH_CLAIM_BLOCK, not independently calibrated PASS. Stage C-F not executed by this workflow.
