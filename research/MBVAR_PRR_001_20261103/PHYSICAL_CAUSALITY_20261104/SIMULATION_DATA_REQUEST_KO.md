# SIMULATION-DATA-REQUEST-001 — Sionna ray별 RF 기여 및 공통 좌표·Heading 대조

**목적:** R4/R5에서 편파비가 급변하는 물리 원인과 R2 반례를 재현하여 C0-B/C3 인과 실험을 가능하게 한다.
**현재 상태:** DATA REQUEST, 추가 시뮬레이션 미실행. C0-A는 기존 composite H만으로 실행됨 (Actions #41783949902).
**최우선 원칙:** 기존 Full/Native-LoS 총합 H와 MB_VAR 입력 전체를 재생성하지 않는다. 이미 GitHub에 저장된 데이터를 기준 채널로 고정하고, 추가로 필요한 **개별 ray 성분**과 **동일 위치-Heading 대조**만 산출한다.

## 1. 원본 환경과 동결 입력

- 저장소: myoungsunk/sionna-resimulation; 기준 SHA aac6fe8d4dba2bdaea3d531f3cf4fd196a773ce6.
- 경로/앵커: R2_aB_m0, R4_aB_m0, R5_aB_m0; Anchor B=(10,0,2.65)m, robot z=0.45m, mount 0°.
- 재사용 원본: BLOCK_C의 각 Full_RF/H_R*_aB_m0.npy, H_LoS_R*_aB_m0.npy, SAMPLES.json, Tnone timeline, scene/PLY/material manifest.
- 안테나 FFD: LP_plus45_bank.npz SHA256 b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b; LP_minus45_bank.npz SHA256 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9. 두 bank는 기존 LFS object의 bytes/hash 검증; 재학습·재합성 금지.
- Sionna native ray solver: results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json의 solver 계약. max_depth=3, samples_per_src=100000, max_num_paths_per_src=1000000, synthetic_array=true, los=true, specular_reflection=true, refraction=true, diffraction=false, edge_diffraction=false, diffuse_reflection=false, seed=20260924.
- 257 bin, 6.2504 GHz 시작, 간격 1.95 MHz, frequency index와 RX(+45/−45), TX(+45/−45) 순서 고정. 원래 ray 디버거 research/R4B_RAY_ATTRIB_20261103/compute.py를 reference로 삼되 실행 SHA·설정·스칼라 GPU/LLVM 환경을 반드시 기록.
- Mitsuba·DrJit·Sionna 버전, Python/NumPy, CPU/GPU, solver variant, scene/material PLY SHA, bank SHA, 경로/pose ID를 실행 전에 lock하고 기록한다.

## 2. SM0 — 최소 Canaries: ray-resolved FULL spectra [필수]

최소 대상은 **확정된 원본 pose_id**를 직접 사용한다. FFD truth pose의 좌표를 샘플 manifest에서 읽고, 새로운 위치로 변형하지 않는다.

| 경로 | 우선 pose_id | 목적 |
|---|---|---|
| R4-B | 168,172,173 | 33.6–34.6초에 FP tap 이동·양의 편파오차와 Heading 과신 단서 |
| R4-B | 194,234 | 이전 native ray 검증 접근/오차 상쇄 대조 |
| R4-B | 500,525,729 | 후반 시점 반사 변화, 음의 측벽 반사 대표, 원본 최대 eMP pose |
| R5-B | 401,465 | 큰 편파오차가 거절되는 양성/음성 게이트 반례 |
| R5-B | 979,980,982,983 | 196.4초 편파오차와 tap 선택 변화의 전후 |
| R2-B | 525 | C0-A에서 abs(eMP)가 가장 큰 R2 대조 (추후 원인군 확대는 별도 선택) |

*선정된 pose는 사후 hotspot 진단용*이다. 본 1차 검증의 효과를 새로운 독립 표본/빈도 추정으로 주장하지 않는다. 식별 불가능한 pose는 임의로 대체하지 말고 BLOCKED로 남긴다.

### 필수 원시 산출물

각 pose_id에 대해 다음을 저장할 것 (변동 path 수는 offsets + ragged array 또는 1-pose NPZ로 저장 가능).

1. **Frequency-domain complex path fields**: per path_i/per 257 freq/per RX±45/선택 TX+45의 Re·Im 또는 복소 dtype, direct ray 포함; path sums가 archived Full H의 선택 TX column과 비교 가능해야 한다. 필요한 경우 TX−45 column도 별도 저장하고 그 사실 표시.
2. **Path metadata**: stable path/group ID, direct/reflected, path delay tau_s per frequency, arrival/departure angles, scene object/interaction chain (floor, ceiling, y± wall, x± end), interaction type, path count/missing flag. ray ordering이 달라지는 frequency 간 그룹 기준을 문서화하고 원본 source IDs 보존.
3. **Direct vs combined**: direct ray coefficient와 total Full H, archived LoS H, composite Full/LoS H, original RX branch spectra; 4×FFT shape·tap index·range·signed s, first-path detector peak·30% threshold, relevant two-port CIR samples at fpFull/fpLoS, selected tap±4 주변.
4. **Same-tap decomposition**: sF(fpL)-sL(fpL), sF(fpF)-sF(fpL), sum identity. 각 성분에 부호, denominator/power floor, tap move integer 및 거리 차이 포함.
5. **Ray attribution diagnostics**: same fixed tap에서 direct + selected reflection group의 leave-one-ray-out s and port powers, quadratic coherent interaction allocation (e.g. path-wise Shapley for port power). **개별 ray의 편파비 제거 차이들을 additive contribution인 것처럼 합산하지 않는다.**
6. **Runtime provenance**: model/code SHA, scene/config/bank SHA, seed and versions, frequency grid, per-pose file content SHA256, group count, direct index confirmation.

### 필수 QA 및 stop

- 반사성분 재합성: H_direct + sum H_reflected = H_Full_native, 전 bin·RX port에서 복소 residual reported. 단순 전력합으로 대신하지 않는다.
- 과거 archived Full/LoS H와 native 재생성 H의 상대 L2 오차 및 최대 절대 차이 reported. Sionna 버전·경로 변화로 일치하지 않으면 원인 규명 전 STOP.
- 초기 **제안 허용치**: relative L2 Full≤1e-3, LoS≤1e-5, 자체 native ray sum residual≤1e-8 (complex normalized). 이는 확정 기준이 아니라 독립 preauditor가 solver/조건에 맞춰 실행 전 승인할 값. 확인된 과거 R4 4pose는 Full 약 3e-5, LoS 약 1.5e-7.
- archived H와 수신 chain이 다르면 FP 결과를 임의 shift/scale해 맞추지 않는다. mismatch를 원시 결과로 남긴다.
- 첫 canary FAIL이면 데이터 생성 범위를 늘리지 않는다.

## 3. SM1 — 시간·공간 인과 집중 구간 [SM0 PASS 후]

다음은 최초 제안 후보이며, 대상 시점은 원본 Tnone의 pose_id로 결정한 뒤 freeze한다.

- R4 33.0–35.2s, R4 0–15s(초기 인과 가설), R4 59–61s(복구 직전 근접), R4 99–105.4s(후반 반사 대조).
- R5 79–81s, 92–94s, 195–198s, 132–135s(근접·작은 오염 대조).
- R2 앵커 B에는 C0-A 데이터에서 사전에 정한 큰 FP shift·큰 물리 편파오차/작은 편파오차 각 대조를 등록. C0-A 계산 이후 지정한 개발 진단점이라고 표시.
- 각 구간은 full/LoS, per-ray contributions, tap transitions를 **시간 순서로** 결합. pos/heading 및 0.2s 이동 변화, 변경된 반사면과 port power를 같은 pose ID로 정렬. spatial window(0.1/0.25/0.5/1.0m)와 fixed time window(0.2/1/5s)를 별도 분석한다.
- 사건 선별은 사후 hotspot 진단이다. 빈도를 추정하거나 전체 경로 효과로 일반화하지 않는다. SM1은 SM0 결과를 보고 물리적 원인 가설이 충족될 때 별도 승인을 받아 확대한다.

## 4. SM2 — 동일 위치·Heading만 바꾼 물리 반증 데이터 [필수 C3]

동일한 복도 scene·앵커·RX 높이·bank·material에서 고정 위치의 yaw만 바꾸어 신규 RF를 만든다. 기존 R4/R5 경로를 서로 다른 좌표에서 비교하는 것은 heading의 순수 효과가 아니다.

- 첫 세트 좌표: 기존 R4 pose 168, R5 pose 982 및 공통 위치 x=10m y=±0.35m, x=13.9m y=±0.35m (허용 위치/충돌 검사 선행).
- yaw: 같은 좌표에서 0°, 180°, +35.7°, −35.7° + 각 실제 궤적 yaw. 동일 좌표에서 한 인수씩 변경. 범위를 임의 확장하지 않는다.
- 기록: LOS/Full composite H, 같은 지점의 ray-resolved channels, fp/port powers/range/s, model h_s/Jacobian per rad vs per degree; yaw만 변화시킬 때 반사 성분과 관측 민감도가 어떻게 변하는지.
- 한 시점의 기존 GT/Heading과 교차해 실제 있었던 측정이라고 취급하면 안 된다. **물리적 counterfactual RF 데이터**로 별도 접두사와 source ID 사용.
- SM0/SM1의 ray 재현 PASS가 먼저이며, 필요하면 한 좌표 4 yaw canary부터.

## 5. 데이터 저장·전달 명세

- 새 데이터 경로 제안: research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/{SM0,SM1,SM2}/ ; large NPZ는 Git LFS 또는 영구 접근 가능한 GitHub 원본으로 게시. Actions artifact 단독은 만료되므로 완전 전달이 아니다.
- MANIFEST.json: repo/source SHA, simulation SHA, input list sorted, original/counterfactual flag, pose_id/time/xyz/yaw, original vs new masks, bank/material/solver env versions, shape/dtype/units, checksums, reconstruction residuals, PASS/HOLD.
- INDEX.csv: case/phase/pose_id/t, orientation, file path/sha256, number of rays, direct valid, fpFull/fpLoS, max abs error, max relative error.
- READ_ME_FIRST_KO.md: 생성/제출 순서와 재현 명령, 미확보 실패 항목, 최초 발견 결함.
- path coefficient NPZ: per-ray complex fields + path IDs + delays + object sequence; direct/negative controls 포함. CSV 숫자 요약만으로 제출 완료 인정 금지.
- 모든 경로·채널의 결측/무효/추정 path를 삭제하지 않는다. pose_id sequence가 922/1883 원본 샘플과 Tnone 742/1415 평가 sample에서 다르므로 원래 index 일치 검사 필수.

## 6. 독립 감사 요청

**IMPLEMENTER:** 요청 데이터를 생성하되 기존 H/GT/MB_VAR를 수정하지 않는다. **INDEPENDENT AUDITOR:** 다른 runner·독립 코드로 bank/scene SHA, 복소 H 재합, FP/편파비 연산, path별 counterfactual, 원본 archive parity를 검산한다. 구현자 결과 JSON을 그대로 승인하면 안 된다.

상태:
- RUN_SM0 = REQUESTED_NOT_AUTHORIZED
- RUN_SM1/SM2 = HOLD
- C0B_CAUSAL_CLAIM = BLOCKED UNTIL independent audit passes.

수치 threshold·pose 목록·새 RF 데이터 구분은 실행 전에 동결하고, 과거 RF와 비정상적으로 일치하지 않더라도 threshold를 사후에 느슨하게 바꾸지 않는다.
