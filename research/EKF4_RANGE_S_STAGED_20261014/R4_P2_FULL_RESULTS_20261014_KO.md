# R4 P2 전체 재실행 최종 결과 (2026-10-14)

## 결론

**P2 synthetic numerical execution PASS; original P2 main hypothesis SUPPORT on all three registered routes with bias +0.05°/s.** No estimate was replaced by prediction or silently dropped. `scientific_PASS=false` remains the global *real-RF/generalization* claim status; P2 synthetic SUPPORT is not P3–P6 validation.

## Source and immutable artifact provenance
- GitHub-hosted Actions [run 38568036257](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38568036257), successful.
- Exact numeric experiment commit: `b8fc45ee0db5ce4e293066b75dc5456a24019b52` (branch `research/ekf4-r4-full-p2-audited-20261014`).
- Reuses the **unchanged** stable objective descent implementation from prior `a52bedcbbea2b0619ac5e2f8efbe73bd5fd4c624`; this is **not** identical to the earlier R3 branch `2547f147ea347563a186a886bd25a543871825f3`. No changes to P2 scientific model, generator, noise covariances or thresholds.
- Artifact [11896549139](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38568036257/artifacts/11896549139), ZIP SHA256 `0c7f3a711106f7815d45540a161eed97336e179e90d30f014847040f1931f4ab`; downloaded and verified. Contains 5550 archive entries, **600 raw INPUTS.npz, 2400 complete state/covariance trace NPZ, 2400 model result JSON**, plus registered metric/CI and gate receipts.
- Frozen `P2_SPEC.json` SHA256 `548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7`; `synthetic.py` SHA256 `c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643`.

## Mandatory audit and numerical eligibility
- Mandatory pre-execution static source audit **GO**; P0/P1, R1, R2 baseline gates **PASS**.
- Earlier frozen 4-failure regression **PASS**; later R3 5-failure archived cases (run 38562146793) × two initial states **10/10 PASS** after archive SHA256/CRC + individual frozen NPZ SHA validation.
- Representative 6 route/bias cases × four estimators = **24/24 VALID**.
- Full phase repeated pre-execution audit **GO**.
- Entire pre-registered 3 routes × 2 biases × 100 seeds = **600/600 complete paired trials**; **2400/2400 individual model cases VALID**; **0 solver invalid**. Original finite stationarity criterion `gradient_tol=1e-8` and `MAP_max_iter=80` unchanged.
- Independent post-run archive receipt **PASS**, zero errors; exactly **5407 manifest SHA256 checks**. Source model-reconstruction score verification performed in experiment generator on every model trace.
- Independently decoded `TRIAL_METRICS.csv`: 2400 unique `(path,bias,trial,model)` keys, all 18 original paired contrasts recomputed with original 10000-draw seed-771 percentile bootstrap to tolerance 1e-12 against original `PAIRED_CI.json`: **18/18 matched**.

## Primary scientific comparison: MAP4 − MAP3

Heading RMSE unit degrees; MSE delta and CI unit deg². Every bias group has 100 complete paired trials (no selection-conditioned missing observations).

| Path | True bias (°/s) | MAP3 heading RMSE | MAP4 heading RMSE | Relative RMSE change | Mean paired MSE Δ (MAP4−MAP3) | 95% bootstrap CI for Δ | Verdict |
|---|---:|---:|---:|---:|---:|---|---|
| straight | 0.00 | 0.4425° | 0.5594° | +26.4% | +0.117100 | [+0.099743, +0.134614] | worse secondary |
| straight | +0.05 | 0.9961° | 0.5699° | −42.8% | −0.667514 | [−0.722206, −0.614857] | **SUPPORT** |
| turn | 0.00 | 0.4480° | 0.5849° | +30.6% | +0.141443 | [+0.115301, +0.168262] | worse secondary |
| turn | +0.05 | 1.0329° | 0.5918° | −42.7% | −0.716734 | [−0.786106, −0.650154] | **SUPPORT** |
| return | 0.00 | 0.4518° | 0.5709° | +26.4% | +0.121814 | [+0.097369, +0.147960] | worse secondary |
| return | +0.05 | 0.9563° | 0.5738° | −40.0% | −0.585209 | [−0.644793, −0.527816] | **SUPPORT** |

**Scientific interpretation**: Registered primary hypothesis "nonzero known true bias +0.05°/s gives negative MAP4−MAP3 trial mean Heading MSE" is supported in straight, turn and reverse-driving return. The zero-bias loss is material and is **not** suppressed. Extra bias DoF is a trade-off, not a universally superior estimator.

## Supplementary comparisons
- For +0.05°/s, MAP3 → MAP4 **position RMSE (m)**: straight 0.06883→0.06571; turn 0.06500→0.05504; return 0.07637→0.05938.
- **Heading 95% coverage** on +0.05°/s fixed-bias trials: MAP3→MAP4 = straight 35.14%→96.42%; turn 37.42%→96.49%; return 37.53%→95.68%. Coverage is conditional on fixed true bias and source matched synthetic assumptions; not prior-predictive real-RF calibration.
- All six `MAP4−EKF4` paired Heading MSE 95% CIs include zero. In this specific matched synthetic benchmark, extra 4-state bias modeling (vs 3-state) dominates gains over local nonlinear MAP-vs-EKF algorithm choice.

## Precision and limitations

The `~10^-14` float64 absolute cost jumps from previously failed terminal steps are **not physically meaningful RF accuracy targets**. They matter only because naive absolute cost comparison can reject a valid local optimizer step and invalidate a 120-step recursive run. This replay uses an already verified stable residual-difference objective representation with independent finite-gradient and local covariance regression. It does *not* claim that every floating-point detail is certified, and does not relax any gradient condition to force success.

**Not validated**: real LoS/Full RF, measured multipath, external office scenes or sensor hardware, nonlinear/multimodal posterior reference, independent-scene generalization and P3–P6 stage receipts. These require distinct stage audits; do not promote P2 synthetic support to broad RF scientific PASS.

## Historical evidence retention defect addressed

Prior full execution run 38561439520 produced 2400 VALID in logs but its GitHub artifact list mistakenly included `p2_preflight/**` rather than actual output `p2_full/**`, so independent inspection of raw full results was blocked. This run explicitly fixes upload path, retains full raw traces, and independently checks the complete manifest and the paired contrasts.
