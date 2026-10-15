# R5 S0 R2 Fast11 / Wide19 원본 LoS LUT 곡선 추출 결과 (2026-10-15)

## 소스·감사
- [GitHub Actions Run 38677812640](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38677812640), 실행 소스 `b7c61e9ec4922d5d1c4d35faaeef532d8634fc3f`.
- [원시 CSV/JSON/PNG artifact 11946880593](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38677812640/artifacts/11946880593), ZIP SHA256 `fd8a1bcf5e49eb6c7cde4d418d6bb072eee1bad4a19f816121127b705d1e998b`.
- 원 RF archive `11782748118`, SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`. 파일별 source/FFT/LUT 보존, 사전감사 GO, ZIP CRC PASS, `scientific_PASS=false`.
- Frozen R2 Anchor A/mount0/45, t=60s and 120s, same stored DR prior at each time. Four pose/channel pairs, `theta/phi_tx/phi_rx` estimated via frozen original P3 geometric forward model. All exported samples are **theoretical LoS-LUT predictions**, *NOT* real Full RF yaw-sweep measurements or Heading GT.

## Yaw sweep definitions
- Fast11: `[-10,-8,...,+8,+10]°` (11 measured-relative yaw offsets).
- Wide19: `[-45,-40,...,+40,+45]°` (19 offsets).
- Wide11_CONTROL: `[-45,-36,...,+36,+45]°` (11 offsets at same wide span). This isolates angular span from number of observations.
- At fixed center and antenna lever arm neglected, yaw changes only `phi_rx→phi_rx−delta`, not `theta` or `phi_tx`. Source LUT is 46×180×180 2° trilinear; its phase-free `s=(P1−P2)/(P1+P2)`, TX0(+45 LP), RX ±45 LP. Source LUT interpolation metadata maximum error 0.023972 exceeds 0.01 acceptance limit — source fidelity is a limitation.

## Original s predicted dynamic range
| Case/time | Fast11 span | Wide19 span | Wide11 span |
|---|---:|---:|---:|
| R2 A mount0 t60 | 0.100 | 1.441 | 1.441 |
| R2 A mount0 t120 | 0.169 | 1.288 | 1.274 |
| R2 A mount45 t60 | 0.689 | 1.973 | 1.973 |
| R2 A mount45 t120 | 0.147 | 1.529 | 1.516 |

## Unknown common s-offset projected shape self-match
- For `psi0` equal to the **controlled LoS template generator's own input yaw** (not independent physical yaw truth), generate `s_i=LUT(theta,tx,rx−alpha_i)`, then compare against candidates `psi0+Delta`. Project a free common nuisance `c` out of Gaussian covariance; assumption `R_s=0.0081`, noise uncorrelated for the table, `x,y` fixed without uncertainty.
- The `Delta J<=chi2_1(.95)=3.84146` set is a *mathematical shape-identifiability window*, **not observed 95% frequentist coverage**. Full RF angle-specific NLoS, measured yaw uncertainty, model/LUT calibration error and position uncertainty are not included.

| Case/time | Fast11 ideal 95% candidate window | Wide19 ideal window | Wide11 ideal window |
|---|---|---|---|
| mount0 t60 | [−3.8,+7.7]° | [−1.5,+1.4]° | [−1.9,+1.9]° |
| mount0 t120 | [−5.4,+5.6]° | [−2.0,+2.0]° | [−2.7,+2.7]° |
| mount45 t60 | [−7.2,+7.6]° | [−2.6,+2.6]° | [−3.3,+3.3]° |
| mount45 t120 | [−30,+12.7]° (scan reaches the ±30 search bound; **uninformative/truncated**) | [−3.0,+3.2]° | [−3.8,+4.2]° |

## Scientific meaning
1. Yaw-sweep curve **shape** contains more information than one `s` measurement under the LoS source model, but a locally affine Fast11 response combined with an unknown shared multipath offset can be near-unidentifiable.
2. Increased span and increased number of angles are different effects. Wide11/Wide19 equal-span controls permit the separation.
3. Absolute `s` swing is not a reliable surrogate for heading Fisher information after nuisance elimination; long wide sweeps can create more distinctive shapes even when Fast11 point-to-point variation appears large.
4. No Full angle-specific `H(f,psi+delta)` samples exist in this frozen archive. Valid Full RF improvement requires actual yaw-resolved multipath channel generation or physical measurement, together with calibrated angular error covariance and packet deduplication.
5. No RF packet should be applied in the ordinary per-step filter and again as independent scan-derived factor; `ScanHeadingLikelihood` should preserve posterior modes, relative yaw quality and used packet IDs. Source state remains `scientific_PASS=false`.

Result provides S0 **prediction curves and model identifiability** only. The next study must acquire angle-resolved Full observations and assess robust likelihood calibration, not claim heading improvement from self-matched LoS source curves.
