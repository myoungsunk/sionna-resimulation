# EKF4 P3–P6: 동결 LoS/Full RF 재사용, 단계적 계측·추론 계약 (2026-10-14)

## 연구 경계
P2 matched synthetic는 cloud 38535078022에서 600/600 complete로 종료했다. MAP4는 +0.05deg/s bias에서 세 경로 Heading RMSE 개선 및 bias=0에서 세 경로 악화가 관측됐다. **현재 RF 검증의 결정적 공통점이 아니다**. P3는 frozen RF input eligibility, P4는 3state R0 공동 관측과 4state RF adapter same-prior numerical parity, P5는 위치를 고정한 실제 LoS-LUT Heading posterior likelihood 수치 검증, P6는 안전하게 재구성 가능한 motion을 활용한 실제 RF R0 recursive 비교로 분리한다.

## 동결 입력과 증거 재사용
- original reference commit `32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20`.
- original P2 one-step cloud [38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521), artifact `11782748118`, archive SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`.
- previous P0 runtime report `PASS_LOCAL_SHA256_SHAPE_POSE_PREFLIGHT`, 39 assets, seven cases, three routes. Original P2 one-step 14 case-channel NPZ with raw `s,r`, frozen 3-state same-prior H/R/P, truth scoring. Do NOT describe 14 traces as independent RF scenes.
- `P0_INPUT_MANIFEST.json` and its LUT metadata; `hs_lut_2deg.npy` numeric 46×180×180 loaded without regeneration. Repeat only required asset SHA and observation parity. Original H FFT re-extraction NOT demanded when identical input archive is used.
- R0 comparison model `Rs=0.0081`, `Rr=0.0068578637m²`, `Rsr=0` unverified independence assumption, `range_offset=-0.5315983906250129m`; original 2D chi2 gate 99% 9.21034. Do not fix calibration by tuning after results.

## Mandatory audit
Each code/diagnosis/execution stage receives a **separate same-Git-SHA pre-run source+archive audit** receipt before importing numerical estimation modules. Verify archive + per-case frozen trace SHA, P0 manifest + LUT dimensions/SHA, truth isolation, model source and clock/pose alignment, phase-specific intended decision and numerical stop behavior. `scientific_PASS=false` until justified by independent physical/scene evidence.

## Stage results and stop
P3 source + frozen trace eligibility receipt. Failed missing/stale trace blocks this input, not unrelated P2 synthetic conclusions.
P4 compare archived frozen EKF3 joint C local Jacobian/innovation/gate/K/P with independently computed 3-state and 4-state **joint one-step using augmented zero-cross-bias prior**. The 4-state bias cannot be learned in a single step with zero cross-covariance; state this explicitly. No new 4state recursive effect claim from P4.
P5 fixed-position Heading posterior, with actual LUT and same RF s. Grid refinement 720/1440/2880; report TV/modes/coverage limitations. **This is NOT historical G3 position-integrated reference**. Historical G3 TV 0.387 numerical failure remains fail for that reference. P5 fixed-position can pass without fixing G3.
P6 true *recursive* state transfer using frozen `z_r,z_s` and reconstructed wheel+gyro controls from the stored DR-only trajectory. Independently regenerate DR-only 3state prior and require small parity against archived `xminus`/motion. 3state and 4state estimates use same R0 raw observations, same gate/quality, and 4state includes b gyro with explicitly chosen initial prior (0±0.1 deg/s). Both predictions + each accepted posterior become next prior. Genuine LUT s(x,y,psi), exact slant range, offset, original same-time conditional Gaussian R. Report LoS/Full RMSE/NEES/coverage, solver failure counts, time correlations, and range gate rejection. Source orbit legacy-Euler truth vs SE2 known mismatch retained.
Prior/motion Q must match original P0 if reconstructable; if unable to invert controls/shape, **stop only P6** with provenance and no scientific claim. The 14 traces are noise-pair seed0; no L2/RF multipath corrected prior, no independent external scene. **No autonomous calibration or trust switching based on heldout truth**.
If P6 shows real Full RF degradation, report as scientific finding, do not lower gate or artificially remove cases.

## Budget
Audit+P3 eligibility → P4 at minimum one case/channel then 14 traces → P5 fixed-position diagnostic only → P6 14 case-channel traces. Preserve run+code+input SHA, outputs, failure status. When essential RF/LUT data unavailable or source parity fails, finish unaffected stages and record NOT_RUN for affected stages; do not fabricate result.
