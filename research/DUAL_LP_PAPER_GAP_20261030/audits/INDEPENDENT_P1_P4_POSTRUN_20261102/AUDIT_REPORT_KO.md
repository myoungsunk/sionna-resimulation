# DLP-EKF-GAPS-001 — P1–P4 사후 독립 원본·수치 감사 (2026-11-02)

**Role:** AUDITOR (별도 ChatGPT 감사 세션에서 원본 GitHub Actions artifact를 직접 다운로드, 구현자 보조 함수를 호출하지 않고 새로운 Python 수식으로 재계산)  
**대상 원본:** `research/dual-lp-p4-full-native-c0plus-20261102` commit `e365b2f79eb86a3fd53d0d350f8e2d9364f285fe` 및 P1/P2/P3/P4 각각의 원래 Actions 아카이브  
**판정:** **`ACCEPT_WITH_BOUNDARIES`** — 보존된 RF·관측·EKF·통계 수치 검산은 PASS, 하나의 Corridor 장면 밖에서의 물리적/통계적 일반화나 독립 사람 심사는 검증되지 않음.

## 1. 단계별 감사 결론

| 구분 | 별도 수식으로 재검산한 원본 근거 | 판정 |
|---|---|---|
| P1 SourceFFD | 원본 19,038 residual rows, 14,502 archived observer parity rows, ddof=1 152 stratum의 mean/RMSE/cov. Max statistic diff 2.22e-16, LoS/Full pair 9,519, 누락 0 | **PASS_NUMERICAL** |
| P2 4-state Range-only vs joint | 원본 28 NPZ trace, 87,012 state-arm-time slots. `f/F/Q/H/innovation/K/S/NIS/χ²/Joseph` 독립 식 전수 재귀; 최대 posterior P 8.88e-16, NIS 2.84e-14, 실패 0 | **PASS_NUMERICAL** |
| P3 Native C canary | 39 real Native Sionna complex H·tau NPZ, 실제 SHA·257bin 재추출. signed s max diff 3.89e-16, direct tau max error 3.68e-15s | **PASS_ARCHIVED_RF** |
| P4 Sparse pilot | 원 실행 Actions 41405327966의 39 Native C pose-only, 84 case metrics, QA PASS. **NOT** the Full 3136 study | **PASS_WITH_PILOT_SCOPE** |
| P4 Full RF | 3136 actual original NPZ SHA/unique pose/time, incl 39 original P3 +3097 new, 51,465,535 stored tau values, 805,952 full frequency bins each with one unique geometric direct ray; tau max error 6.16e-15s; 3136×(Full/LoS) `H→FFT→tap→r,s` parity signed max 8.88e-16, C observation vs EKF raw input **exact 0** | **PASS_ARCHIVED_RF_TO_EKF** |
| P4 Full EKF | Original 12 NPZ, 87,808 state-arm-time slots. Independent 4state own-posterior f/F/Q, 1/2/3-DoF gate, Joseph, NIS, R matrix, no new RF; max post-x 1.78e-15, post-P 3.33e-16, K 9.73e-16, NIS 5.68e-14; 84 case→28 pooled+48 paired contrasts all exact. 1m state corruption negative test detected | **PASS_NUMERICAL** |

**Full native route counts:** R2 979=13+966, R4 742=13+729, R5 1415=13+1402. Complete old/new 39/3097 and all 3136 original C0 timestamps. The 80 original Native RT shard jobs in Actions 41408877765 were successful; later aggregate failed and was recovered without mutating source H.

## 2. 원 워크플로 실패를 보존한 판정
- [P1 original SUCCESS](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41300302082), independent-formula preaudit [41289874166](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41289874166).
- [P2 original failure](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41315429738) was **Git LFS NPZ publication**, NOT numeric compute failure; original Actions artifact downloaded and checked. [P2 immutable recovery SUCCESS](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41388940715).
- [P3 Native SUCCESS](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41395666117).
- [P4 Sparse Pilot SUCCESS](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41405327966).
- [P4 80-shard original workflow failure](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41408877765): all 80 RT shard jobs succeeded but aggregate Python heredoc variable error. Next recoveries [41434959439](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41434959439) (2.65 vs 2.6500000000000004 float strict match), [41435428514](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41435428514) (native 3 route data success, EKF dependency missing); [final 41435839892 SUCCESS](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41435839892), used SHA-matched original Native data.
- P4 Full original preserved trace ZIP SHA256: `5ecf2a326ec17c8ce4ccc7a42fe76227ecf6ad7ec027df9cdfcd2304dcb0acfe`; original route H/tau ZIPs: R2 `706811d5af4503fd310b598040419cc0ee63ec30ee8f1d26b764763575aa2e6f`; R4 `93f9e9bd71ed045fdf8f8ad42886caeac0dc57add126efd986ec43b0a9fb0776`; R5 `c65864473a685476708c77fea7031684577452acb50d0167e023dd0e229e2111`.

## 3. 과학적 결론 및 반례 보존

P4 Full 한 Corridor의 pooled Heading RMSE(°), 2686 평가 timestep per condition:

| Channel/bias | DR4 | A range | A joint SourceFFD | AB range | ABC range |
|---|---:|---:|---:|---:|---:|
| Native LoS B0 | 0.498 | 3.437 | **0.419** | 2.380 | 0.990 |
| Native LoS L2 | 29.225 | 6.306 | **0.616** | 2.188 | 1.120 |
| Full B0 | **0.498** | 10.262 | 5.526 | 2.451 | 2.089 |
| Full L2 | 29.225 | 13.836 | 5.731 | 2.718 | **2.306** |

- **증명된 범위:** Full L2에서 ABC Range-only의 heading 2.306°/XY 0.1753m가 A range 13.836°/XY 1.9042m보다 작다. A 3136 vs ABC 9408 range packets, 3× resource. Equal-packet A/ABC 비교는 update cadence와 공간 coverage가 다르다.
- **반례:** Full B0에서 RF 없는 DR4 0.498°보다 ABC range 2.089°가 **악화**. All-cases improvement 금지.
- **사후 분산 과신:** Full ABC 95% pose coverage B0 **8.97%**, L2 **8.23%**. 단일 seed/time-correlated scenario에서의 descriptive empirical coverage이며 population calibration confidence interval 아님.
- P1 SourceFFD Native LoS direct-only 물리 일관성은 높으나 Full signed RMSE old LUT 0.169678 → SourceFFD 0.170113, **전체 multipath 개선이 아님**.

## 4. 감사 제한 및 필수 후속

1. **물리 solver**: 보존된 실제 PathSolver 출력 복소 H/tau를 재해싱·검산했지만 Sionna RT 경로 계수/반사 메커니즘을 별도 solver로 **재실행하지 않았다**. 6 pose×9 bin canary(기존 자동화)는 오프라인 Full direct/native LoS 일치 근거.
2. **환경 독립성**: R2/R4/R5는 동일 Corridor 장면의 세 경로. 3,136개의 timestamp는 simulated common clock일 뿐 실제 hardware multi-anchor sync 실증 아님.
3. **통계**: seed 0, 상관된 시간 표본이므로 scene-heldout, untrained heldout generalization, true NEES confidence intervals 미검증.
4. **오차 모델**: cross-anchor R을 대각으로 가정, time/space covariance를 교정하지 않음. 낮은 posterior coverage의 정확한 인과 분해 미검증.
5. **인적 독립성**: 이전 일부 pre-run 독립 계산기와 구현은 동일 ChatGPT 작성자. 이번 별도 세션에서 실제 원본을 새 코드로 독립 재계산했지만, **별도 인간 동료 GitHub APPROVE나 신원 확인된 인간 감사 서명은 없음**. 이를 해당 단계의 물리 검증 PASS로 가장하지 말 것.
6. **추가 연구 범위**: Office scene·3-D 상관·M2 characteristic-aware EKF·실측 동기화·추가 독립 시나리오는 별도 계약.

**Verdict:** `ACCEPT_WITH_BOUNDARIES`. 지난 P1–P4가 실행됐고 저장된 RF/관측/EKF/통계 산출물의 내부 재현성은 원본을 독립 수식으로 전수 검산해 확인했다. 논문 주장은 *동일 Corridor 환경에서의 원인 후보·결과 관찰*로만 제한할 것.

**별도 독립 코드 및 기계 영수증:** 본 대화에서 전달한 `DLP_EKF_P1_P4_INDEPENDENT_AUDIT_20261102.zip`에 Python 검사기 5개, 감사 영수증 5개, 이 판정 보고서가 포함되어 있다. 이 보고서가 최초 입력/원본을 변경하지 않는다.
