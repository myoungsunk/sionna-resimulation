# RA2-OBS-LINEAGE-001 — 다음 단계의 테스트 가능한 구현 계약 (DRAFT)

**역할 handoff:** 새 작업의 PROPOSER가 동결한 뒤, 별도 IMPLEMENTER가 QA/패치를 수행하고, 별도 AUDITOR가 raw data로 재검산한다. 이 문서는 아직 frozen science preregistration이 아니며 RA0/RA1 과거 결과를 사전 등록된 것으로 바꾸지 않는다.  
**기준 소스:** `myoungsunk/sionna-resimulation`, full source `f100a983cc389fcdef073592a254add61e7115da`; historic RT read source `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`; governance `250d617ad89a4105fa1af546cc83ceed9de98f42`. 필수 LFS와 bank 원본 SHA는 `SOURCE_REFERENCES.json`·동결 input manifest에서 읽는다.  
**허용 범위:** 기존 원 H/SAMPLES/timeline/controls/observation trace의 전수 대응 및 검사기의 fail-closed 보강만. **금지:** original raw overwrite, new estimator tuning, 과거 결과 덮어쓰기, 비동의 대규모 물리 RT, science PASS 주장.

## 0. 구현 시작 전 파일·출력 계약

- 읽을 원문: root AGENTS, COMMON_CONTRACT, `ROLE_PROPOSER`, `ROLE_IMPLEMENTER`, `ROLE_AUDITOR`, RA0-RA1 MASTER, 원 source manifest, 새 `RA2-OBS-LINEAGE-001` frozen 파일, 원 observation/SourceFFD/sensor/BB 코드.
- 새 작업 폴더 `research/RA2_OBSERVATION_LINEAGE_<date>/` (정확한 경로와 SHA는 구현 브랜치의 contract로 다시 고정), 원본 파일·이전 결과 폴더는 READ_ONLY.
- 각 출처에 `source_git_sha`, `blob_sha`, `sha256` (binary), `shape/dtype/units`, `producer_command`, `asset/scene key`를 기록한다. SHA 빈 값은 `MISSING`이어야 한다.
- 출력: `SOURCE_LEDGER.json`, `OBS_JOIN_LEDGER.csv`, `OBS_NATIVE_RECALC.csv.gz`, `MISSING_DUPLICATE.csv`, `FIRST_PATH_BOUNDARIES.csv`, `MODEL_BRIDGE.csv`, `NEGATIVE_FIXTURES.json`, `MANIFEST.json`, `QA.json`, `AUDIT_REPORT.md`, `RA2_HANDOFF.md`, rejected/errors retained.

## 1. 식별단위/조인

raw H는 `(scene_id, anchor_id, mount_deg, pose_id, channel=FULL/LOS, fgrid_sha, pattern_bank_sha, solver_sha)`를 key로 하고 tensor `[Npose,257,2,2]` 저장. timeline key는 `(route, t_s, pose_id, phase)`. 각 original `SAMPLES`는 `timeline`의 운행/회전 pose ID와 추가 simulation probe ID를 모두 포함하므로 **raw H와 packet이 1:1일 필요는 없으나 각 packet은 정확히 하나의 기존 H pose를 참조**해야 한다. 중복된 raw pose ID는 오류이며 같은 pose의 서로 다른 seed packet 재사용은 합법적이다.

기대 case: `R2_aA_m0`, `R2_aB_m0`, `R2_aA_m45`, `R4_aA_m0`, `R4_aB_m0`, `R5_aA_m0`, `R5_aB_m0`. 원 timeline R2 979 / R4 742 / R5 1,415; original SAMPLES H R2 1,303 / R4 922 / R5 1,883. 관측 packet 수는 고정 run의 scoring trace에서 별도로 추출해 정확히 비교한다. raw bank 257 f-bin, ±45 LP RX branches, TX=0, `freqs_hz`의 완전 동일성 필수.

**acceptance:** `N_registered == N_joined`, 0 unknown pose ID, 0 duplicate raw key, packet `case/anchor/mount/t_s/pose_id` exact alignment, expected SAMPLES auxiliary pose 별도 ledger; 0-row 검사는 FAIL. 미확인 pose는 행 제거 없이 `BLOCKED_INPUT` 보고.

## 2. 관측 연산 사전 정의

정합할 수학/동작:

```
H[p,f,rx,tx]  (complex, TX selected 0)
CIR[p,tap,rx] = 257 * IFFT_1028( Hann_257[f] H[p,f,rx,0] )
peak_port = argmax_rx max_tap |CIR|
first_tap = min {tap : |CIR[peak_port,tap]| >= 0.30*peak_peak_port}
P1,P2 = |CIR[first_tap,rx0/1]|^2
s = (P1-P2)/(P1+P2) ; invalid P1+P2 -> missing, never silently clip
r = c0 * first_tap / (1028 * Δf)
```

`observe(noise_var=None)` (frozen H raw reference)와 sensor noise-injected branch는 독립된 observation ID로 기록. Raw chain에 거짓 source `mu`나 GT를 넣지 않는다. `H` 자체가 frozen noiseless simulation이면 seed 증가를 독립 RF realization이라고 하지 않는다. Verify TX/RX orientation, port-swap negative sign invariant, `yaw ↔ yaw+360` periodicity, `r`-unit meters and signed `s` in [-1,1].

**acceptance (existing raw packet replay):** `max |s_recomputed - z_s| <= 1e-12`; `max |r_recomputed - z_r| <= 1e-9 m`; no missing/duplicate keys; no unreported detector resampling. These are replay numerical tolerances, **not** cross-Sionna physical parity tolerances. If archive's raw extractor intentionally differs, stop and propose an exact amendment with paired evidence instead of loosening tolerance after viewing outcome.

## 3. 평균·분산·모델 브리지 추적

- `h_LOS(x; sourceFFD)` is `[distance + B_OLD, signed_s_sourceFFD]`; its r component is **not** identical to discrete tap range. Log both `r_native_tap`, `r_continuous_bridge`, `h(x_true)`, `h(x_prior)`.
- Archived `mu_B`, `mu_M`, `R0` must retain original case/time/packet-key; newly generated RF poses shall not receive old packet-keyed mu. Model predicted `mu_M` from Δs feature is a **different** test requiring original fitted model and train split source.
- `epsilon_truth = z - h(x_truth) - mu` only in evaluation; `innovation_prior = z - h(x_prior) - mu` online. Testing truth leakage is mandatory.
- Sign and units: ψ rad internal, degrees in report, XY m internal, RMSE cm explicitly, gyro bias rad/s.

## 4. Adversarial / negative fixtures (all must fail)

| Fixture | Expected error |
|---|---|
| replace one complex H or corrupt its SHA | `ERR_SOURCE_HASH` |
| omit 1 observed packet or 1 raw match | `ERR_MISSING_PACKET` |
| repeat one pose id with conflicting H | `ERR_DUPLICATE_KEY` |
| shuffle pose ID while keeping array row order | `ERR_POSE_ALIGNMENT` |
| swap RX1/RX2 without updating declared convention | `ERR_PORT_CONVENTION` |
| interpret yaw degrees as radians | `ERR_ANGLE_UNIT` |
| shift one timestamp / wrong route segment | `ERR_TIME_ALIGNMENT` |
| fabricate empty phase and return success | `ERR_ZERO_ROWS` |
| change continuous bridge without amended model ID | `ERR_MODEL_VERSION` |
| force zero/NaN power denominator to finite s | `ERR_OBS_DOMAIN` |

Every fixture must be run on an isolated *copy*, preserve test log, fail exit status; none may alter original H or accepted trace. Positive baseline case remains byte/hash identical.

## 5. Two roles and independent audit separation

IMPLEMENTER submits actual commands, source/environment SHA, counterexample, real-case results and negative fixture results. AUDITOR must separately choose an ordinary packet and adversarial packet per route; independently calculate H→CIR→tap→r,s and verify source identity; check missing/duplicate accounting, source hash lookup, masks and measurement/model distinction. A separate runner using implementer's same helper alone does NOT establish independent audit. If author and auditor share one session/agent, label SELF_REVIEW_ONLY and withhold independent endorsement.

**Technical PASS:** all 7 raw case inputs accounted for, all positive canary parity and all negative fixtures pass *by rejecting bad inputs*, manifests complete, original untouched. **Scientific approval:** explicitly outside RA2; no new Heading/XY effect estimation until a separate science contract and independent reviewer decision. A blocked case must be listed; don't silently drop it or promote remaining cases to universal success.

## 6. Launch order / stop

RA2-a `PROPOSER`: lock exact hashes/path/cardinality/tolerances and source references; pre-review signoff.  
RA2-b `IMPLEMENTER`: create ledger-only read-only harness; negative fixtures; full pose/packet join; small H→r,s independent canary; then seven-case report.  
RA2-c `AUDITOR`: independent packet recomputation, failure injection, data leakage and claim boundary report; exactly one of ACCEPT_WITH_BOUNDARIES/REVISION_REQUIRED/REDESIGN_REQUIRED/BLOCKED_EVIDENCE.  
RA2-d `PROPOSER`: assess whether corrected source chain invalidates BB/MB_VAR replays; if yes, issue a **new scoped rerun contract**. Bulk H rerun only after physics impact proof and separate budget/solver approval.  
**Immediate stop:** missing binary/LFS access, unverifiable bank, unseen H hash, 0-row path, partial join, unapproved selector/port shift, frozen contract mismatch, actual source/ground-truth leak.