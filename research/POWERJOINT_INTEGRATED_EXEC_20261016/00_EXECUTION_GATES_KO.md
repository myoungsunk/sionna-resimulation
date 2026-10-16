# POWER_JOINT 통합 계획 P0–P4 실행 게이트 (2026-10-16)

## 고정 입력과 재현 기준
- 사용자 제공 통합 계획 `POWERJOINT_INTEGRATED_FINAL_PLAN_PACKAGE_20261016(1).zip`, E1–E6 / PRE-1~3, 184개 사전등록 arm은 **계획표**이며 184개 실험 완료를 의미하지 않음.
- SourceFFD 원본 기준: `4b82e9801a1e065593fdd67a0f3ebd721ba29848`. Legacy 2° LUT, 10m source/ffd, POWER/J4/R0 frozen 기준선을 **절대 덮어쓰지 않음**.
- LP+45 FFD bank SHA256: `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b`. LP−45 bank: `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9`.
- 신규 통합 SourceFFT·CIR 및 범위 결과는 사용자 대화에 전달된 **독립 ZIP/Markdown/CSV**에 저장. 이 GitHub 문서는 연구 게이트 요약이며 **ZIP의 전체 수치/코드를 GitHub에 게시했다고 주장하지 않음**.

| Gate | 현재 판정 | 증거/잔여 입력 |
|---|---|---|
| PRE-1A | TECHNICAL_PASS | bank/source SHA and candidate model versions registered |
| P0 | SUPPORTED_BUT_LIMITED | Native LoS 9519: s RMSE 6.592e-7; FP tap 0 mismatch; H complex max rel 3.254e-4 but not bit parity. Range remains d+B_OLD; Δtap .149552 m, residual RMSE .045945 m; normalized quantized likelihood absent |
| PRE-2 | BLOCKED_SOURCE_PARITY | Historic V01b five Method-B M45 Full H vs Native FAIL. Subsequent 2026-10-12 trace audit attributes mismatch to native missing valid higher-order specular paths. Do not mix 7 native and 5 legacy as identical |
| PRE-3 | TECHNICAL_PASS | R4 742 and R5 1415 timestamps; B0/L0/L1/L2 regenerated 8 new GT-derived Sensor-v2 controls. Not original measurement log |
| P1 | TECHNICAL_PASS_REFIT_ONLY | source-corrected 19038 packets and N4B 24 Source fits frozen; scene generality/likelihood calibration absent |
| PRE-1B | CONDITIONAL_LOCK | source observer and route folds locked for *mechanism comparison*, final model not frozen until Range likelihood and q endogeneity solved |
| P2 E1/E5 | SUPPORTED_BUT_LIMITED | existing 256 recursive/1368 sameprior, 48 new hybrid frozen-prior controls; Gyro bias Kν exact; not deployable hybrid |
| P2 E4 | SUPPORTED_BUT_LIMITED | R2 25 straight legs, 347 common scored frames; M0/M45 SourcePOWER B0 heading 1.833/1.040 deg. R4 zigzag M45 held until PRE-2 |
| P3 E2/E3 | SUPPORTED_BUT_LIMITED | G4 POWER covariance/mean swap, Gate flip analysis; seven heldout route/mount correlated-NLL comparisons with sign reversals; M45 R4/R5 blocked |
| P4 | SUPPORTED_BUT_LIMITED | R4/R5 train R2 heldout G5 CIR full/clean classifier, 32 recursive R2 paths, +/−3/6dB neg controls, independent re-score. LoS protected in same corridor; no generalization; M45 B0 narrow XY NEES 16.61→16.99 |
| P5/P6/P7 | NOT_TESTED | outside current request; requires independent scenes, site repeats, dual-anchor C_AB |

## 심층 조사해야 하는 두 가지 단계
### P0
1. 복소 H 원본 파일·port/conjugation/gauge; θ=0/seam/tap crossing FD and ray completeness.
2. 연속 EKF 기준 `d+B_OLD`과 discrete first-tap k의 normalized `p(k|x)`; threshold noise/soft bin probability. Discontinuous floor quantizer를 EKF differentiable h로 위장하지 말 것.
3. SourceFFD direct와 경량 range-aware LUT를 원본/Native LoS와 독립 검증.
### P3
1. `μ_r/μ_s` × diagonal/joint `C_rs` × fixed/natural Gate × G4 POWER mean-cov swaps, fixed-prior packet and natural recursive separately.
2. G4 inversion earliest Gate flip and subsequent trajectory drift with pre-Gate NIS/whitened J4⇔SR4 SPD.
3. E3 GT evaluation only approach/depart radial c=(v·ell)/|v|; R4/R5 M45 only after PRE2 physical contract.
4. q extracted from same (r,s) packet; no normalized p(z|x,q) without deriving p(z,q|x). If unavailable, use *empirical robust update*, not calibrated Bayesian posterior.
5. Temporal site bias/colored residual requires independent repeat RF data in P5.

## 연구 윤리와 Claim
- **Allowed**: within-corridor physical LoS s parity, Dual-LP biases through Kalman state cross-covariance, mechanism dependence on route/mount/gate; proof-of-concept CIR quality safeguarding clean LoS on heldout R2.
- **Forbidden**: universal joint Crs gain; Native/Method-B M45 equivalence; full Bayesian consistency; XY narrow-axis calibration; unseen multipath/hardware performance.

Source: `research/V01B_RESULT_20261012/REPORT_KO.md`, `research/V01B_TRACE_REQUEST_20261012/RESULT_KO.md`, and original branch SHA above. No original data altered, no final scientific PASS asserted.
