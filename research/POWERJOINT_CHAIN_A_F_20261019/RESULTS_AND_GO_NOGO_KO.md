# POWER_JOINT Full RF Heading A–F 실험 — 2026-10-19 실제 실행 결과

**과학 판정:** SUPPORTED_BUT_LIMITED. **새 모델 승인:** NO-GO. **물리적 RF 장면 수:** 동일 복도 한 장면. **M45:** R2 A M0/M45만.

## 데이터 및 실행
- GitHub 원본 Full/LoS 복소 H 7쌍과 LP±45 bank 사용; 기존 두 bank SHA 일치. SourceFFD로 19,038 Full+LoS 관측 레이블 재생성 및 R2/R4/R5 route-heldout POWER/G4 OOF 재학습.
- 실제 새로운 6-state EKF: R2 A M0, R2 A M45, R4 A M0, R5 A M0 각각 B0·L2 × 9 arms = **8 recursive conditions/72 arm-score rows**, 새 Sionna 환경 생성 없음.
- C단계 1차 보정 구현의 covariance 중복 결함은 폐기하고 전체 V2 재실행. V2 rho=0 beta 상태는 POWER1 상태 최대차 4.12e−14, Gate 반전 0 (8조건). 최종 정본은 CD_V2, CDE_V2.
- 저장 상태 독립 점수계산 Heading RMSE/nominal95 전체 **72개 arm 일치**. 원본 FFD 데이터와 동일 scene 내 통계이고 독립장면 반복 아님.
- stage D 공통 POWER prior packet mean/cov/gate 총 **42,180 packet-arm**; stage E error-origin/gate diagnosis; stage F 사전 정의한 x strip 별 45개 full recursive counterfactual.

## C: 시간 기억 bias 추가의 실제 재귀 B0
| Case | Joint4 RMSE / heading95 | POWER1 | 2D beta-memory |
|---|---|---|---|
| R2 M0 | 7.930°, 16.9% | 1.799°, 68.6% | 2.857°, 83.1% |
| R2 M45 | 1.006°, 51.4% | 0.983°, 63.6% | 1.401°, 70.8% |
| R4 A M0 | 0.847°, 44.3% | 0.659°, 46.8% | 1.617°, 51.0% |
| R5 A M0 | 4.827°, 9.3% | 4.556°, 39.7% | 6.183°, 62.1% |

**단순 동적 beta 상태는 정확도와 포함률을 동시에 개선하지 못함**; MEMORY 존재 자체를 반박하는 것은 아님.

## D: 사후 오염 레이블 != 관측 업데이트 효용
P4 레이블 `abs(full-los-range)>=0.15m OR abs(full-los-s)>=0.10`와 같은 prior의 JOINT vs POWER heading-squared-error 부호를 오프라인 비교:
- R2 M0 B0 오염 label 음성 n598에서 POWER 유리 47.0%, 양성 n231에서 POWER 유리 63.2%.
- R2 M45 B0 음성 n442에서 POWER 유리 39.1%, 양성 n387에서 유리 41.1%.
즉 **오염의 크기만 분류하는 작업과 행동을 바꾸어 실제 Heading을 개선하는 작업은 같은 학습 문제가 아님**. Oracle utility는 실시간 추정 입력으로 사용 금지.

R2 M0 B0 POWER: 829 평가 패킷 중 811 수용, 392개는 그 한 번의 accepted update에서 즉시 Heading squared loss 증가. R2 M45 POWER: 410 harmful accepted, 25 beneficial rejected. NIS는 GT 효용 Gate가 아님. 개별 유해 update가 장기 유해하다는 결론 아님.

## F: local x-strip intervention의 강한 반증/지원
x in [1,4),[4,10),[10,16) m first contiguous interval after 30s, region selection is oracle geometry for diagnostics only. In region, skip RF / remove mean / inflate R×4 / memory beta then resume same original POWER1 Full RF until end.

| case | strip | after-end POWER RMSE | skip RF only there, then original RF | result |
|---|---|---:|---:|---|
| R5 A M0 B0 | x[10,16)m, 44.2–74s | **4.842°** | **1.636°** | RF updates at this site strongly involved in later heading failure |
| R2 A M45 B0 | x[10,16)m, 52.4–82.2s | **0.998°** | **3.182°** | same spatial skip is harmful in this different case |
| R2 A M0 B0 | x[4,10)m, 30–52.2s | **1.853°** | **2.964°** | blanket RF exclusion not valid |

R5A x[10,16)m: mean correction removal after RMSE6.634° (worse), R×4 gives 3.807°, memory beta5.575° (worse). Thus site-specific RF acceptance/weighting is implicated but **specific reflecting wall/path physical root cause is not yet determined**. Cases without subsequent frames have after metric NaN—not proof.

## Conclusion and next steps
1. Current Power1/G4 conditional mean/cov and correlated R can miss physical-directional systematic signed bias.
2. Time-correlated residual exists (R2 heldout M45 r lag1 .785, s .934), but spatial/yaw confound; naive beta memory did not solve Heading.
3. Site-level F intervention proves chain interruption possible **in some cases**, but other cases reverse sign.
4. Need isolate x[10,16) R5 A Full/LoS per-packet r/s, FP tap, `K_psi,r nu_r` and `K_psi,s nu_s`, pre-gate NIS and trajectory first divergence versus R2 M45; compare alternate mean-only/range-only/s-only under common prior; if path-level traces are obtainable identify actual physical reflector. Design physically measurable online gate only then, preserving beneficial M45 RF.
5. Independent office/new routes not yet generated; no environment generalization or formally normalized Bayesian claim.

**Full numerical outputs:** conversation file `POWERJOINT_A_F_CHAIN_CAUSAL_RESULTS_20261019.zip` (about 23.5MB, SHA256 `6c3150b65078ff62dfcebf5aa8aa95741389a085100b3c8a1f1851a2c967cec3`). Not committed to GitHub; summary+GO/NOGO here. Input acquisition GH Actions run 39256621315: source snapshot artifact 12187054720 uploaded successfully, workflow report itself failed from missing runner numpy. Source file available and local science executed to conclusion.
