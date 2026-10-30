# IMPLEMENTER_REPORT_S0 — POL-XCORR-001 v1.0

**역할:** IMPLEMENTER. This is **technical execution and contract-rule mechanical classification**, NOT independent scientific audit/verdict.  
**계약:** POL-XCORR-001 v1.0 FROZEN, \`SELF_REVIEW_ONLY\` pre-run audit.  
**결론:** **S0 TECHNICAL_QA_ONLY COMPLETE**; H1 \`FAIL\`; R-03 \`REDESIGN_REQUIRED\`; **M1/M2 STOP**, P1/P2 HOLD, P3/RT NOT_RUN.

## 1. 실행 근거와 고정 버전

| 항목 | 잠금/근거 |
|---|---|
| Freeze base branch | \`research/pol-xcorr-freeze-v1-20261030\` (SHA \`50703065b8ba716fe50e13bae0ae6fd38eacc3c3\`) |
| Science contract | \`contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md\` SHA256 \`c36c1c56d4db59d39ea85e1d87c1efe622325730a6b4fbc595fc95e583cde219\` |
| Frozen config | \`config/PLAN_PARAMETERS_v1.0.json\` SHA256 \`a16e8226f2766f4188c144228f99276c0102532667eb1e46816c0b4e0ff42658\` |
| Science spec | \`SCIENCE_SPEC_v0.3.md\` SHA256 \`5db75dcc0a332833de50d87ba2081bea5ca0cd74e7e093ae00ce987728368450\` |
| Input lock | \`config/INPUT_LOCK_v2.json\` SHA256 \`bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184\` |
| Governance SHA | \`d5f84d9d04d28d465f3357e9299352eb184e6bfc\` |
| Base data/source SHA | \`250d617ad89a4105fa1af546cc83ceed9de98f42\` |
| Successful S0 execution source SHA | \`248b172eb0f188169a31fa4b299e6ec61a7fe207\` |
| Successful S0 script SHA256 | \`7ee7b2b5c1c87bf4c2183bf512c18571779336d0d252357a3ea613ca4a4b3c54\` |
| LoS floor input | \`results_p0/run_40867521966/LOS_FLOOR.csv\` SHA256 \`d2c08dbac53975d13b880cc93f3293c9eaaf8f4ae75c4fe07a7eee1cdaf24dd6\` |

## 2. GitHub Actions / 실패 기록 보존

- **Run [40989019866](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40989019866): SUCCESS.** S0 script exit 0; frozen hashes, 257-bin frequency lock, P0 LoS floor checksum, synthetic fixture, LAW+PHYSICAL sweep, q_ref/R03 and noise sweep all executed and recorded.
- **Run [40988893943](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40988893943): FAILURE preserved** under \`results_s0/run_40988893943/\`. Root cause: gain invariance F3 fixture redetected n0 after port-gain change. This compared two DIFFERENT windows, whereas F3 is a fixed-J/fixed-W identity. Fixed the *test* by checking F3 on the same pre-gain n0, with original gain tolerance \`1e-12\` unchanged. Re-detection effect remains logged separately; operational invariance is NOT claimed.
- Earlier first workflow config push \`40988841358\` failed YAML parsing (unquoted step-name colon). Fixed and replaced by the two jobs above; no science calculation occurred in that invalid job.
- Both results and failures retained append-only. The v1.0 contract, original frequency H, P0/P0V3 outputs and original reference data were never overwritten.

## 3. Registered S0 synthetic result

### LAW / PHYSICAL, H1

- Exact 257-bin \(H(f)=a e^{-j2\pi f \tau_0} + b e^{j\psi} e^{-j2\pi f(\tau_0+\delta)}\) with frozen first-path observer and Hann/4N IFFT.
- LAW grid \(\delta=0:0.05:4\) ns, 16 \(\psi\), five wedge values, four amplitude levels: **25,920 rows**.
- PHYSICAL \(\psi=-2\pi f_c\delta\), for each wedge/amplitude/delta: **1,620 rows**; no slope verdict.
- LAW valid 25,920; rank-one parallel Jones q bound checked over **5,184** rows.
- LAW n0 switches: **11,793** (captured in \`S0_LAW.csv\`, no silent deletion).
- Fixed-n0-segment log-log slope: **30 PASS, 139 FAIL, 9,274 NOT_EVALUABLE** (additional 2,621 parallel-Jones negative-control segments and 49 predefined near-cancel segments); frozen fit interval 0.05–1.0 ns, tolerance 1.9–2.1.
- **H1 mechanical gate = \`H1_FAIL\`.** A discrete tap/phase test failure is NOT a falsification of the separate continuous-time small-\(\delta\) determinant identity. Source-model and test-assumption mismatch must be reviewed.

**Critical interpretation problem needing proposer decision/amendment (do not silently fix):** The freeze instructs a *fixed \(\psi\) coefficient* in \(H(f)\) while retaining absolute RF frequency \(f\) in \(\exp(-j2\pi f\delta)\). The effective carrier-relative phase is \(\psi-2\pi f_c\delta\), so it is NOT held constant under the LAW delay sweep. Large n0 switching reflects a moving detector and rapidly rotating phase as well as envelope effects. The PHYSICAL mode separately sets \(\psi=-2\pi f_c\delta\), potentially double-counting carrier phase under this interpretation. Any replacement with centered \(f-f_c\) or fixed effective phase changes the frozen protocol and requires an explicit amendment/new \`EXPLORATORY\` run.

### R-03 q_ref / LoS floor

- Exact frozen D6 q_ref vectors: \(a=(1,1)/\sqrt2\), \(b=10^{-0.5}(\sqrt{0.91}a+0.3a_\perp)\), \(a_\perp=(1,-1)/\sqrt2\), \(\delta=1\) ns, \(\tau_0=20\) ns, 16 phase points; arithmetic mean across 16 admissible phases.
- **q_ref = 0.0010961014111595176**.
- Exact P0 LoS TIMELINE (n=7251), \`np.quantile(...,0.95,method='linear')\`: **q95 = 0.0062089980405863505**.
- \(q95/q_{\rm ref}=5.66462005921343\).
- Therefore registered fixed rule: **\`REDESIGN_REQUIRED\`**. Synthetic sensitivity \`a=(1,0.3j)/norm\` q_ref = 0.0010811232350918373 (report-only, not chosen for verdict).
- Per v1.0 contract/handoff, **M1/M2 STOP; no threshold relaxation or redefinition.** This result means the specific reference single-reflection signal fails its registered LoS-floor guard; it is not a universal impossibility theorem for all reflection configurations.

### Synthetic fixtures / noise

- Fixed-frequency-flat single elliptical path: \`q_W=0\`, \`phi_fp=-pi/2\`, \`S3_fp=-0.55046\`; parallel Jones five \(\delta\) cases all q=0.
- F3 **fixed-W** gain invariance relative error \(2.40\times10^{-14}\) (contract limit \(1e-12\)). Under gain-induced re-detection, n0 changed 36 → 35 and epsilon_rho changed; explicitly reported, not treated as invariant.
- Complex frequency-bin AWGN at first-path SNR 30/20/15/10 dB × port delay 0/25/50/100/250 ps × PCG64 seed 0..199 = **4,000 valid samples**, 20 summary groups. No invalid seed.
- Illustrative q_W q95: 30 dB/0 ps = 0.00055556; 30 dB/250 ps = 0.00714393; 10 dB/0 ps = 0.05304140. These are **synthetic** LoS noise+offset floor values, not hardware measurement or cross-scene generalization.

## 4. Output and provenance

**Implementation files created:** \`scripts/s0_synthetic_v1.py\`, \`.github/workflows/pol-xcorr-s0-v1.yml\`.

**Successful append-only evidence directory:** \`results_s0/run_40989019866/\`.

Contains: \`S0_LAW.csv\`, \`S0_SLOPES.csv\`, \`S0_QREF.json\`, \`S0_NOISE_FLOOR.csv\`, \`S0_NOISE_SEEDS.csv.gz\`, \`S0_OFFSET_NOISELESS.csv\`, \`S0_FIXTURES.json\`, \`S0_DECISIONS.json\`, \`S0_STATUS.json\`, \`MANIFEST.json\`, \`IMPLEMENTER_REPORT_S0.md\`.

\`MANIFEST.json\` contains the pre-run frozen contract/input hashes, source code SHA, full execution git SHA, environment, seed scheme, command, checks and output checksums (self/manuscript excluded to avoid cyclic self-hashing). Failed run directory preserved separately. The existing P0-v0.3 and frozen-science docs were intentionally untouched.

**Scientific status:** \`TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE\`; science verdict NOT_ISSUED. No Full channel H, stored e_s/e_r/eta, metric–label/AUC analyses, new RT, P1, P2 or P3 executed.

## 5. Unresolved gates and mandatory handoff

1. **P0-to-S0 key science blocker:** R-03 \`REDESIGN_REQUIRED\`. Contract's M1/M2 **STOP** must remain active. Before any reattempt, proposer must examine the LoS q-floor nuisance and explicitly decide whether to abandon the proposed local-window M1, redesign/condition it, or pursue a separately frozen alternative. Do not change q_ref post hoc to rescue this run.
2. **H1 test design:** The fixed-\(\psi\) absolute-RF spectral formula does not fix *effective* carrier phase, and n0 switches repeatedly. Proposer/auditor must distinguish discrete-observer deviations from validity of the formal \(\delta^2\) derivation; any new synthesis convention requires separately documented amendment or exploratory status.
3. **R-10:** Independent auditor signature still absent. Neither proposer self-signature nor our implementation self-check is independent science audit.
4. **P1/P2:** HOLD under v1.0 D5 (the transmittal explicitly requests **S0 only then stop**). No irreversible label opening, S0 PR contains no P1 trigger.
5. **P3, P4, RT:** Not run; R-07/R-08 external and R-11 budget/holdout are unchanged. R-01 T4_ONLY_BLOCKED remains.
6. **Next allowed action:** independent scientific review of S0 evidence and proposer redesign/amendment decision. New contract+pre-run audit and user authorization must precede any P1/P2 stage.

**Implementer conclusion:** S0 implemented and executed reproducibly under the pinned v1.0 contract, but original physical-gate expectations **are not supported** in this run; downstream M1/M2 paused in accordance with the registered STOP rules.
