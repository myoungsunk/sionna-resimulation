# POWER_JOINT 통합 계획 — 2026-10-19 현존 유효 RF 실행 판정

**Source lineage:** `research/ffd-source-p0p3-20261016` @ `4b82e9801a1e065593fdd67a0f3ebd721ba29848`. **Incoming inventory:** `research/powerjoint-integrated-valid-rf-20261019` @ `809970bc4f3e74b57a1f51a8471be018713dd2c1`.

**전체 판정:** `SUPPORTED_BUT_LIMITED`. 과학 결과는 기존 한 복도에서의 동결 동일 데이터 검증이다. 독립 장면 일반화 및 formal Bayesian posterior consistency는 확인되지 않았다. **원본 코드를 덮어쓰거나 새 RF를 생성하지 않았으며**, 독립 수치 검산으로 동일 입력 재생성 및 일부 기전 분해를 확인했다.

## 유효 데이터와 보류

- **GO:** R2 aA mount 0°/45° Full+Native LoS, R2 aB mount0, R4/R5 aA/aB mount0 Full+LoS. SOURCE P1 OOF train splits와 RF packets SHA 확인. 
- **PRE-2 BLOCKED:** R2 aB mount45 및 R4/R5 aA/aB mount45 **legacy Method-B vs native Full H** V01B 소스동등성 불일치. 원자료가 존재해도 최종 Mount45 recursive claim에서 제외. 새 유효 Mount45는 **R2 aA**로 제한.
- **PRE-3:** R4 742 + R5 1415 time-ordered control frames, gyro B0/L0/L1/L2, A/B same clock, **GT-derived synthetic Sensor-v2**, measured log 아님.
- **P7 BLOCKED:** 새 corridor C01–C03 및 Office O01–O03의 route geometry CI PASS, 신규 Full/LoS 연속 H는 **NOT GENERATED**. Office static 35 sites × yaw sweep은 이동경로 자료가 아니다.

## 실행 범위

- P0 원천 FFD: 기존 Native LoS 9519점 s RMSE 6.592×10⁻⁷, FP tap difference 0; targeted independent complex-H 16 checks rel max 1.508×10⁻¹³. **원본 전체 complex H 비트 정합 미확보, Range 관측식 `d+B_OLD` 미수정, 확장 dense-pole ring 시험 시간 초과**.
- P1: Source-corrected 19038 labels / route-heldout OOF 학습 재사용 (R2/R4/R5 동일 복도, independent-scene 아님).
- P2/E1: R2 mount0/45 LoS/Full range×s hybrid recursive 4 arms; offline synthetic hybrid intervention.
- P3/E2/E3: 기존 R2 Source corrected 256 recursive arms + 1368 fixed-prior comparisons 동결·재검산. R2 mount45 E3 방향별 잔차상관 approach +0.2735 (n428), depart −0.2529 (n426), POWER model predicted 각각 +0.2464/+0.2485; **동일 RF 궤적의 기술통계**, 방향별 posthoc C_rs 수정은 금지.
- P6/E4: R4/R5 mount0 aA/aB × B0/L0/L1/L2 × Full/LoS **32 conditions, nine arms each**. Validated natural recursive EKF. Straight segments are posthoc **kinematic-only subgroup**.
- E5: 96 stored trajectories' `K_bg,r ν_r+K_bg,s ν_s` contribution exactly sums to final gyro bias; **알제브라 분해**이며 RF arm 제거 반사실 실행과 구별.
- E6: R2 mount0 A-only/B-only/A+B × 4 bias. B0 A Power XY 0.150 m, B 0.0743 m, AB 0.0609 m; cross-anchor covariance only sensitivity policy, not calibrated posterior.
- P4: 17 CIR features, train R4/R5 11216 packets / heldout R2 7818, AUROC 0.950; R2 mount0/45 × B0/L0/L1/L2 × Full/LoS **16 natural-recursive conditions ×6 arms**. Hard (0.5) R2 M0 B0 Native LoS Heading 0.502° vs POWER 2.108°, 그러나 Full hard 3.905° vs POWER1.799°. Full RF noninferiority >10% fails hard13/24 and soft16/24 metrics. **현재 후보 NO GO**.
- P5 M45 R2 A B0 Full 95–135s: SourcePOWER Heading0.337°, conditional XY narrow-axis NEES33.864, nominal95% coverage **0%**. covariance consistency NOT established.

## Selected Full RF, Mount0, B0/L2

| Valid case | DR4 B0 / L2 Heading | SOURCE POWER B0 / L2 Heading | SOURCE POWER B0 / L2 XY (m) |
|--|--:|--:|--:|
| R4 A | 0.466 / 19.540° | 0.659 / 0.657° | 0.105 / 0.104 |
| R4 B | 0.466 / 19.540° | 1.508 / 1.448° | 0.094 / 0.096 |
| R5 A | 0.521 / 35.018° | 4.556 / 4.790° | 0.477 / 0.489 |
| R5 B | 0.521 / 35.018° | 1.056 / 0.695° | 0.085 / 0.059 |

DR B0 can beat RF; L2 RF can correct DR gyro drift. **No universal performance superiority or calibrated covariance** claim.

## QA and artifact provenance

- Frozen ZIP/archive SHA and 120 source file SHA match; P4 32 baseline parity checks state/cov <1e−8, zero Gate flips.
- An independent numeric scorer independently recomputed pose/heading/XY/conditional narrow eigen-axis NEES over **32 P6 +16 P4 saved NPZ traces**, verified SPD & Schur covariance decomposition.
- E6 accidental duplicate summary lines were found and repaired from immutable NPZ, final **28 unique rows**. Numerical result count ≠ number of independent RF seeds.
- **Results archive:** `POWERJOINT_INTEGRATED_VALID_RF_EXECUTION_20261019.zip` created and SHA256 independently verified: `97efe63e7a717037828da0823e977917e8fd6468db3fbdce022fb1eea8dc59b1`, 182 files, 91,271,525 bytes. This archive is delivered as a conversation attachment/sandbox download, **not committed to GitHub**. Includes 48 new independent-scored run objects; raw FFD binaries are separately identified by SHA but not bundled again.
- GitHub report is a summary, not a replication of full 182-file 91MB numerical archive, nor scientific PASS for blocked conditions.

## Claim/next GO gates

**SUPPORTED_BUT_LIMITED:** SourceFFD (s) physical fidelity, s-only incremental heading information on R2, gyro-bias cross-cov transfer, dual-anchor same-room comparison, route-replay within one corridor. **FALSIFIED_FOR_CURRENT_CANDIDATES:** P4 full RF non-inferiority jointly with LoS safety, Mount45 overconfident conditional XY covariance. **NOT_TESTED:** independent Office mobile H, real sensor/hardware validation, generalization, normalized (p(q,r,s|x)) and calibrated Bayesian posterior.

**Important:** `R4/R5 M45` is not a valid data replacement even if filename or CRC matches. Keep V01B paired parity as a hard scientific gate.
