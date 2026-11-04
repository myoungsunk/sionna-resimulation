# CAUSAL-VERIFY-001 — Dual-LP UWB 물리오염 → EKF 상태·공분산 과신의 인과 검증 계약 (PROPOSER DRAFT)

**범위:** C0(A,B) RF 물리적 오차 발생 / C1 같은 prior 거리·편파 개입 / C2 자연 재귀 전파 / C3 같은 위치의 yaw-only RF 대조.
**현재:** C0-A 재계산 PASS (자체 source/pose/hash QA), C0-B/C3 missing new ray-resolved data, C1/C2 미실행. 독립 사전감사·동결 및 GO 전에는 새로운 과학적 성능/인과 실행을 실시하지 않는다.
**기준 코드/데이터:** user proposal PR #24 aac6fe8d4dba2bdaea3d531f3cf4fd196a773ce6; 기존 S1–S3/P0/N0B/R2_EXTENSION 결과 수정 금지.

## 0. 질문을 서로 다른 원인 층으로 분리

**Q0:** Full multipath가 RX 두 포트의 직접파/반사파 복소 합을 어떻게 변화시키며, 어떤 경우 FP 검출 tap과 포트 편파비가 급변하는가?
**Q1:** 같은 Full−LoS 편파오차라도 거리·편파 관측과 H/K/R의 결합으로 왜 Heading 갱신 영향이 다른가?
**Q2:** 왜 R4의 오염 이력이 잘못된 상태/작은 P로 남고, R5 및 R2에서는 다른 posterior가 형성되는가?
**Q3:** 물리적 위치·yaw·이동시간 중 무엇이 RF 에러 발생을 바꾸고, 이전 상태오차·측정 게이트·오차 상쇄 중 무엇이 EKF 오차 유지에 작용하는가?
**Q4:** 기존 S2/S3 복구 손익과 Q0–Q3의 기전 사이 연결이 설명되는가? *복구 정책 설계/새 성능 주장은 이 계약의 목표가 아님*.

용어 고정:
- eMP_s = s_Full(x_GT)-s_LoS(x_GT), eMP_r = r_Full(x_GT)-r_LoS(x_GT): 원시 물리 채널 차이.
- epsilon_s = s_Full(x_GT)-h_s(x_GT)-mu_s(q_RF); delta_h_s = h_s(x_GT)-h_s(x_prior); nu_s = epsilon_s + delta_h_s. 같은 mean/channel convention을 쓴 경우의 등식.
- H_psi = derivative at **filter prior**, 단위 s/rad. g_GT per degree는 s/degree로 별도 명시. K_psi,s는 연동된 4상태 Kalman gain, H_psi만으로 결정되지 않음.
- P: 재귀적 posterior covariance, NEES와 Heading95/XY95는 GT를 갖춘 evaluator에만 사용.
- 원래 MB_VAR는 EXDS 기반 range mean과 편파 기본 mean, Rss_VAR=Rss_base+sigma_b(rho)^2를 사용. 원래 BASE NIS mask를 공통으로 사용. 정책 비교에서 이를 몰래 수정하지 않음.

## 1. 고정 원본·학습누출 방지

- R2/R4/R5 Anchor B Mount0 Tnone, 257-bin Full/LoS composite H, 같은 robot pose_id, 5Hz, 0.2m/s 이동+제자리 회전.
- 물리 입력/FFT, bank, material, max_depth=3, frequency, RX port와 TX selection은 GitHub source SHA 및 A0_R1 source lock에서 검증.
- 각 route-specific held-route mean model의 lineage를 별도 기록. R2는 S1 Delta-s threshold 산정에 사용되고 R2_EXTENSION이 이미 공개 평가됐으므로 신규 독립 holdout 아님.
- 수치 score의 primary t>=30s와 t=0부터 재귀 시작을 구분. 실제 시드0–29는 같은 원본 RF의 센서 잡음 실현으로 동일 환경을 공유한다.
- 기존 R4 pose168,172,173,525 및 R5 401,465,982는 **사후 선택된 설명용 hotspot**. 이를 확인용 비노출 데이터로 가정하거나 새 경로 일반화 주장을 하지 않음.

## 2. C0-A — composite FP 오차의 측정 수준 재현 (ALREADY EXECUTED)

이미 있는 Full/LoS H에서 원본 observation.py의 Hann, 4N IFFT, 30% leading-edge detector로 같은 pose의 FP index, r, s를 계산한다.

sF(fpF)-sL(fpL) = [sF(fpL)-sL(fpL)] + [sF(fpF)-sF(fpL)].

- 전항은 *같은 LoS tap에서 Full/LoS composite의 차이*; 후항은 *Full 내부의 tap 선택 차이*. 두 항은 대수적 항등식일 뿐 independent physical causal contribution으로 읽으면 안 됨.
- 이미 완료: [GitHub Actions #41783949902](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41783949902), total n=3136, original input SHA 12, 원본 eMP와 FP tap 분해. README의 결과표와 DATA_READINESS_AUDIT 참조.
- 미완: 별도 독립 구현의 observation-chain parity audit. 처음 C0-B의 독립 감사 선행 조건으로 등록.

## 3. C0-B — ray-level 물리 반사 귀속 (BLOCKED ON DATA)

입력: [SIMULATION_DATA_REQUEST_KO.md](SIMULATION_DATA_REQUEST_KO.md)의 SM0 ray-resolved 15 fixed pose 대상. canary 재생성 H가 original composite archived H와 사전 허용오차 내 일치하면 SM1 인과 집중 창에 진입한다.

실험:
1. 같은 pose, 동일 RX/TX port/freq/scene에서 direct-only, Full, full-minus-one-surface 등 complex ray subtraction. 경로가 변할 때 FP를 **고정**한 버전과 detector를 **재실행**한 버전 모두 계산.
2. 경로별 복소 벡터 합을 먼저 검증. power는 |sum H_path|^2이므로 path power의 산술합이 Full의 총 power가 아님. 포트별 coherent cross term, per-path delay, phase and polarization projection를 보존.
3. R4 168/172/173의 변화, R4 234 small-eMP negative control, R5 982,465 extreme controls, R2 525 extreme without detector tap shift를 한 그림/원장에 같이 포함.
4. 같은 변인을 한 개만 변경한 ray/path/FFT detector counterfactual의 변화를 구분. 특히 **tap 위치만 고정**하는 것은 RF 물리변경이 아니라 estimator-side observation preprocessing ablation.
5. 실제 물리 원인 주장: 반사경로 특정은 material/geometry/offline ray oracle에만 허용; 실시간 검출기로 바로 채택 금지.

C0-B STOP: raw ray path/delay/group data 없음, sum-path mismatch, native H archive parity FAIL, source bank/material mismatch, FP 이상 비유한 값.

## 4. C1 — 동일 prior에서 거리·편파 직접 기여 분리 (기존 데이터로 구현 가능, 코드승인 전 미실행)

모든 개입은 **오프라인 oracle**. 동일 pose의 archived z_F=(rF,sF)와 z_L=(rL,sL)를 사용한 4-arm.

| Arm | range r | polarization s |
|---|---|---|
| F/F | Full | Full |
| L/F | Native-LoS | Full |
| F/L | Full | Native-LoS |
| L/L | Native-LoS | Native-LoS |

### C1a: 엄격한 동일-prior / 동일 mask / 동일 K

- 하나의 원래 F/F 이전 x^-,P^-,h,H,muMB_full,Rss_VAR_full,BASE joint gate를 모두 고정. z 두 성분만 교체. 동일 gate로 갱신하면 x_F/L - x_F/F = K[:,s]*(sL-sF), x_L/F - x_F/F = K[:,r]*(rL-rF). yaw wrap 예외 명시. 교차항 확인 및 동일 관측 두 번 사용 금지.
- 같은 K/P/R를 고정하므로 Joseph P가 arm 사이에서 같다는 것은 **정의상** 정상. 이를 물리 모델의 covariance 개선 결과라고 보고 금지.
- Full mean/R를 hybrid 두 arm에서도 유지해 관측 변경 이외의 오차원인을 통제. 별도 'native channel-consistent LoS mean/R' 비교는 모델 변경이므로 C1의 순수 효과와 합산 불가.
- GT는 후처리 오차 측정에만 사용. OOF learned mu, anisotropic Q, noise seed, bias B0/L2, exact pose mapping 모두 고정.

### C1b: 같은 prior, gate 재판정 / gain 재계산

- F-mask 대조와 각 혼합 z를 넣어 BASE joint NIS gate를 재판정한 대조 O를 별도 기록. 한 채널만 거절했을 경우 range-only update를 원래 R correlation 및 Joseph 식에 맞게 구현하고 중복 갱신 금지.
- innovation v=z-h-mu, NIS pre-gate, K_r,K_s, dx/dpsi, posterior P(4×4), conditional acceptance를 모두 로깅.

C1 PASS: 무개입 F/F 기존 MB_VAR F64 재현 (mask 완전 일치, x/P 허용오차 사전 동결), self-derived identity, oracle GT leakage 없음, independent reference K/Joseph parity.

## 5. C2 — 시간적 발생·유지·증폭의 자연 재귀 개입 (기존 RF 데이터 + C1 PASS)

C0-B ray 귀속이 없더라도 **물리 s/r oracle intervention을 통한 필터 기전 분석은 가능**하지만, 이 경우 해당 물리 반사면 귀속을 인용하지 않는다.

사전 진단 집합:
- R4-B 초기 [0,15]s, R4-B [33.0,35.2]s, R4-B [99,105.4]s, R4-B near [59,61]s;
- R5-B [79,81]s, [92,94]s, [195,198]s, near [132,135]s;
- R2-B: C0A에서 사전 등록한 극심 no-tap-shift pose525와 정상/shift controls.
모두 hotspot을 **보고 골랐다는 사실을 유지**. 사후 성능/재설계를 독립 확인이라고 부르지 않는다.

- 각 arm은 t=0, 동일 x0/P0/gyro/odometry/5Hz RF timebase에서 독립 자연 재귀. 개입창 외부 모든 관측은 원본과 동일. C1의 4-way hybrid에 해당하는 window-only counterfactual 및 F vs O gate 분리.
- **C2a (동일 mask)**: 기준 BASE 수용 mask fixed. 오염의 순수 측정 기여와 mask 변경 효과 분리.
- **C2b (자체 gate)**: 개입에 따라 prior가 달라진 상태에서 BASE gate 또는 명시적 joint gate 재실행. 게이트 선택의 인과 효과는 C2a 대비로만.
- 매 시점: physical eMP_r/s, corrected epsilon, state-induced delta h, innovation, H_GT/H_prior (unit), K, Δx, Q, R, Jacobian, P, NEES3/4, Heading68/95·XY95, first accepted bad packet, state error trajectories, gate status, detector tap shift, future paired differences, time-window RF residual autocorrelation 및 time/distance blocks.
- '특정 편파오차 때문에 이후 XY/Heading 오차가 증가했다'는 주장은 원래 주행 대비 개입의 **동일 seed·동일 controls 차이**로만. 관련 비선형 상호작용은 additivity 주장 불가.
- 비교창 0–2/2–5/5–10/10–20초 및 t≥30 전체를 나눠 표기. P만 커져 coverage↑인 결과를 상태 회복으로 부르지 않음.

C2 STOP: frozen F/F parity FAIL, pose_id mismatches, 과거 mean/R 재학습, LoS oracle가 온라인 상태에 노출, 결측 event 후행 삭제, unknown RF tensor 변경.

## 6. C3 — 동일 위치 Heading counterfactual (SM2 시뮬레이션 뒤)

SM2에서 같은 x/y와 material, anchor, mount, bank, RNG/solver를 고정하고 yaw만 ±35.7°,0°,180° 등으로 바꾼 Full/LoS 채널에서 same-tap, ray-field, s, sensitivity를 비교한다. 다른 실측 경로의 서로 다른 좌표를 직접 비교하면 yaw의 인과효과가 아니다.

- Heading change만 할 때 ray phase/port-projection/FP tap/|eMP|·range 오차의 변화, |H_psi| (per rad vs per deg), hypothetical fixed-prior update를 구분.
- C3 결과는 새 simulated RF의 effect이고 R2/R4/R5 원래 자연주행에서의 인과효과 및 일반화 성능을 바로 보증하지 않음.

## 7. 주장-검증 대응

| Claim | 필수 실험 | 거짓 양성 차단 |
|---|---|---|
| C0-P: FP 검출 변화는 극심 편파오차와 동반 | C0-A all pose | 동반=물리적 causal fraction 아님 |
| C0-R: 어떤 반사면이 선택 pose의 포트 전력을 바꾼다 | C0-B rays/leave-one-surface, original-H parity | power additive와 wall 위치 추정 혼동 금지 |
| C1-E: r/s 오차가 같은 prior의 Heading/XY 갱신을 다르게 바꾼다 | C1a fixed K/gate, C1b changed gate | 다른 mean/R 또는 초기 P 변경 금지 |
| C2-H: 특정 hotspot의 RF 오염이 이후 과신에 인과 기여한다 | C2 F/O gate paired full trajectory, P/NEES checks | 단일 시점 상관 또는 재현성 PASS만으로 주장 금지 |
| C3-G: 같은 XY의 yaw가 RF 간섭/편파차를 바꾼다 | SM2 4-yaw per position | 자연 R4/R5 차이를 전부 yaw에 귀속 금지 |
| C4-G: 과거 오염·복구 이득이 경로별로 다르다 | N0B frozen benefit + C0–C3 outcome alignment | 정확도 라벨 ≠ treatment benefit; R2 이미 공개 평가 |

## 8. 감사·승인과 단계 중단

- **DATA_A0**: 외부 입력 SHA/LFS payload 실물 검사, 257bin source layout, 3 route sample join, bank/scene/path generator contract, 모든 원본 trace immutability. C0-A artifact 행수/계산식 자체 QA 확인. 별도 Python 구현으로 FFT/detector 일부 시점 독립 재계산.
- **C0_CODE_AUDIT**: native RT per-path reconstruction, path-key fidelity, direct/reflected separation, same-tap vs detector rerun, accepted error tolerance. 별도 runner 및 자체 checker 기록.
- **C0_RESULT_AUDIT**: raw H/path/reconstructed H, per-tap, per-surface leave-one-out, extremal/negative controls, NO hidden manual shift. C0-B 성공 판정과 범위를 독립 확정.
- **C1/C2_CODE_AUDIT**: actual core/FFD source SHA, x0/Q/bias, same K/P/μ/R, BASE mask & self gate, numerical units, original W0 parity, gate change experiment, no future/GT leakage. 별도 검산 코드 생산.
- **C1/C2_RESULT_AUDIT**: per-step paired state/P/NEES, off-diagonal R, seed-cluster uncertainty, all failed conditions, negative controls, B0/L2 identical RF limitations, claim-to-evidence matrix.
- **C3_AUDIT**: matched spatial coordinates, unchanged scene/solver, correct source bank, new synthetic-only flag, physics/RT parity, all yaw factorial.

각 stage: PROPOSER 조건/threshold freeze → 독립 PREAUDITOR SPEC_APPROVED → IMPLEMENTER 격리 코드 → pinned code SHA/독립 code audit → GO_DEV → development/run → 독립 RESULT AUDITOR → 별도 GO_LOCKED. 감사 에이전트 이름만 바꾸거나 production helper 그대로 재사용한 검사로 독립 PASS 금지. 본 문서는 **개발·과학 실행 승인 토큰이 아니다**.

## 9. 현재 결과와 후속 분기

- C0-A: 3,136 pose composite-H 재계산과 항등식/해시 일치; artifact 저장. 별도 독립 scientific approval pending.
- C0-B/C3: [시뮬레이션 데이터 요청서](SIMULATION_DATA_REQUEST_KO.md)에 적힌 새 per-ray 및 yaw contrast 없으므로 BLOCKED.
- C1/C2: 기존 Git 입력으로 수행 가능한 별도 연구 단계이나 현재 runner/코드/contract GO 없음. **이번 요청은 충분성 판정 → 없는 데이터 요청서·계획서 준비**로 처리.
- 최신 R2_EXTENSION 감사의 독립성·route-specific training한계 공개; 기존 모든 NO-GO/HOLD는 변경하지 않음.
