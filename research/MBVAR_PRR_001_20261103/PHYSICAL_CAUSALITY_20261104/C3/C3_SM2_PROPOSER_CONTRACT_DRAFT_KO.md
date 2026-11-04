# C3-SM2-YAW-001 — 동일 XY에서 yaw만 변경하는 RF 인과 대조

**상태: PROPOSER DRAFT / NOT FROZEN / NOT APPROVED / NOT RUN**

## 목적과 이전 단계

기준 SHA e8669d2c8c54402d44c0310da0ae57edd6fe1965. C0-A/C0-B/C1a/C1b/C2는 독립 감사 ACCEPT 기록이 있으며 재실행하지 않는다. C3는 원래 계획서의 SM2만 다룬다. C3용 코드, 신규 RF, 새 실행 GO, C3 결과는 아직 없다.

가설 C3-G: 동일 위치/높이/scene/앵커/물성/FFD bank/solver에서 RX yaw만 바꾸면 Full과 LoS의 포트별 복소 전파장, first-path 선택, 편파비, Full−LoS 편파오차가 달라지는가? 다른 R4/R5 경로의 서로 다른 위치·다른 prior를 단순 비교한 결과를 yaw의 순수 인과효과라고 하지 않는다.

C2 결과가 C3 설계의 동기: R4 hot33 own gate 편파 교체(FL)로 Heading RMSE 중앙값 B0 -0.29499도·L2 -0.26089도이지만 XY RMSE는 약 +1.26cm 악화. R2 hot525 FL은 Heading RMSE 중앙값 +0.42155/+0.43489도 악화. R5 hot79 own gate 양채널 교체(LL)는 B0 Heading 약 +0.10602도, XY +1.117cm 악화. 따라서 단순히 더 깨끗한 RF라서 항상 재귀 성능이 개선된다는 모델을 가정하면 안 된다.

## 데이터 모집단: 원본에 고정된 6개 XY, 4개 공통 yaw

| 좌표 ID | 고정 RX 위치 m | 이전 근거 |
|---|---|---|
| R4_168 | (5.251464, +0.325895, 0.45) | SM0 R4 pose168, 원 yaw -31.700092도 |
| R5_982 | (1.521387, -0.338994, 0.45) | SM0 R5 pose982, 원 yaw +2.990632도 |
| P10Yp | (10.0, +0.35, 0.45) | 사전 제안 공통 공간 대조 |
| P10Yn | (10.0, -0.35, 0.45) | 사전 제안 공통 공간 대조 |
| P139Yp | (13.9, +0.35, 0.45) | 사전 제안 공통 공간 대조 |
| P139Yn | (13.9, -0.35, 0.45) | 사전 제안 공통 공간 대조 |

각 좌표에서 물리적 body yaw = {0도, 180도, +35.7도, -35.7도} 네 가지. **6좌표 × 4 yaw = 24개 새 RF 조건**. R4_168과 R5_982의 기존 실제 yaw에 해당하는 SM0 저장 입력 2건은 별도의 **원본 보정 대조**이며 24개 새 데이터에 섞어 세지 않는다. 타당한 원본 actual yaw 재실행은 별도 승인 범위에서만 허용. 이미 제공된 선별 좌표이므로 새 환경을 대표하는 무작위 표본이 아니다.

- CANARY: R4_168의 네 공통 yaw만 먼저. 실패 시 잔여 20조건 미실행.
- 원본 R4_168/R5_982 pose ID·원 yaw/위치와 새 SM2 pose는 별도 namespace. 기존 R4/R5 샘플 ID를 재사용해 원래 주행 자료라고 표시하지 않는다.
- collision·scene bounds·수신기 위치·자세 변환 정의(부호, deg/rad, body→antenna, mount=0)에서 한 건이라도 모순이면 GO 발급 전 중단.
- 고정 위치의 yaw-sweep는 물리적 정지 실험이며 기존 gyro·odom·시간이력의 반사실이 아니다.

## 변경 금지 항목

기존 SM0 amended 원시 경로 생성 원본/기준: Python3.11.17, NumPy1.26.4, SciPy1.14.1, sionna-rt2.0.1, mitsuba3.8.0, drjit1.3.1, LLVM/WSL2 pinned variant. RT solver max_depth3, seed20260924, samples_per_src100000, specular/refraction True, diffraction/diffuse False. TX=(10,0,2.65), RX z=.45, mount0, +45TX와 ±45RX 두 포트, 257개 주파수 bin, 원래 scene PLY·materials·banks 및 TX/RX conventions 유지.

한 비교쌍에서 yaw 외에 RF 입력값·파일·난수/solver 조건을 바꾸지 않는다. "yaw 변화만"의 뜻은 **직접파 입사각에 대한 안테나 응답도 함께 변한다**는 것이다. 그러므로 Full s 변화만으로 multipath 변화를 추정하지 말고 eMP(yaw)=sFull(yaw)-sLoS(yaw)와 복소 직접파/반사파를 분리한다.

## 필수 산출물

각 (coordinate, yaw)에서 RAW:
- 257×2 channel Full/Direct(LoS) H와 legacy complex64 phase-compatible group H, 병행 독립 F64 ray closure;
- 주파수 bin별 원시 ray complex coefficients·tau·valid·object/interaction/vertices/angle, 원래 source ID, group label/count/missing mask; 경로/semantic chain은 다른 yaw와 one-to-one index로 연결하지 않는다.
- 포트별 CIR/전력과 fp tap, window±4 taps, s_F/s_L, 같은 LoS tap 분해항, detector-choice 분해항, range F−LoS;
- 같은 yaw에서 model h_s, H_psi=s/rad 및 s/deg 정확 단위/해석과 독립 수치 확인(필요한 경우 고정 source-model).
- 신버전 input/code/runtime lock과 SHA manifest, complete INDEX.csv, zero-missing/failure ledger; GT는 고정 좌표/자세의 synthetic truth만 사용.
- baseline original actual-yaw 2개 기록과의 source binding. 새 4개 yaw에 대해 원본 archive가 없으므로 기존 archived Full/LoS에 대한 일치 검사를 **억지로 수행하지 않는다**. 대신 pinned ray closure/direct geometry, yaw-repeat deterministic QA, per-bin source invariance를 적용한다.

## 분석 설계 (새 RF 값이 생긴 뒤)

(1) 같은 좌표의 pairwise yaw 차이: delta_sFull, delta_sLoS, delta_eMP, delta range, fp shift, port power, H_psi.
(2) direct-only vs direct+reflected 비교. 동일 전파 ray group을 삭제하는 off-line counterfactual은 실제 벽 제거 시뮬레이션과 구분. one-to-one ray across yaw가 아닌 same semantic chain 합만 비교.
(3) first-path가 바뀌는 경우 fixed-tap/selector 분리; 이전 15 pose와 같은 식 사용.
(4) 좌표 block별로 결과 표시; 24개 yaw 조건을 독립 seed 또는 자연경로의 대표 모집단으로 취급하지 않는다.
(5) Original R4/R5 상태와 EKF를 혼합하지 않는다. C3의 물리 RF 확인 이후 Heading 갱신까지 연결하려면 명시적 고정-prior 원인 시험과 신규 C3-EKF 계약이 필요하다.

## 각 단계의 독립 감사 및 fail-closed 판정

**G0 — SCIENCE SPEC:** 이 문서를 물리 단위/좌표/yaw/order, source provenance/threshold, controls/failure definitions까지 동결. 독립 PREAUDITOR PASS가 없으면 STOP. 기준 경로의 기존 결과를 다시 계산하지 않음.

**G1 — CODE:** 원래 SM0 amended producer를 source로 한 SM2 yaw-only wrapper의 신설·SHA 동결. 독립 checker는 yaw 외 parameter 변화, source/FFD hash drift, float32 phase archive compatibility vs F64 ray closure, axes, receiver rotation, per-bin paths, duplicate/missing ID, restored archive-only checking 분리 등을 음성 검증. 코드 변경 후 사전 승인 GO를 자동 재사용하지 않음.

**G2 — CANARY 1 POSITION/4 YAWS:** R4_168 × {0,180,+35.7,-35.7} 총 4조건에만 GO. 새 출력 폴더. provenance와 raw 4×257 bins·ray closure·ports·fp/s 비교를 독립 DATA AUDITOR가 검산. 하나라도 실패 시 STOP 및 원자료 보존; 잔여 20조건 실행 금지.

**G3 — EXTEND 20 CONDITIONS:** G2 독립 DATA PASS 이후에만 새 승인. 기존 producer/scene/solver/FFD/threshold/GT 참조 변경 불가, 개별 capture SHA와 누락 기록 및 원본 actual yaw 보정 대조 보존.

**G4 — C3 PHYSICS:** 같은 XY 4-yaw 간 eMP 분해, tap/port path response, H_psi 및 실험 전 지정한 같은-tap 대비표. 독립 result auditor가 모든 좌표/방향을 확인. PASS는 선택 위치에서 yaw가 simulated RF를 변화시키는 기전 근거이지 R4/R5 자연주행 Heading 과신의 모든 원인 규명은 아니다.

**G5 — REPORT / PUBLICATION:** science claim-to-evidence, 별도 independent numerical/claim audit, artifact SHA/LFS OID·size/accessible original verification, Git push acceptance. 독립 감사 없이 model adoption, C4/new policy, 실시간성 주장 금지.

**STOP:** yaw 이외의 scene/anchor/position/bank 변화, receiver body→antenna orientation 오해, original/novel yaw source 혼합, prior C0-B archive comparator를 새 yaw에 잘못 적용, LoS 진폭/다중경로 설명 혼동, F64/legacy group use-case 혼용, 실패 후 20개 조건 일괄 실행, 증거 없는 independence/generalization 주장.

## 전제
이 문서는 **코드 작성/시뮬레이션 실행/GO 발급 자체가 아니다**. 기존 e8669d2c의 C0–C2 결과와 원래 S1–S3 NO-GO/HOLD를 보존한다.
