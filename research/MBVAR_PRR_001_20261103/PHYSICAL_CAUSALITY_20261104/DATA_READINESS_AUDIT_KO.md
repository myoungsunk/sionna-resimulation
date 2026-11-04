# DATA-READINESS-001 — Dual-LP 물리→EKF 인과 검증 데이터 점검

**기준:** 2026-11-04, PR #24 HEAD aac6fe8d4dba2bdaea3d531f3cf4fd196a773ce6.
**데이터 판정:** C0-A 원시 채널 검증 가능 및 실행 완료. C0-B 반사별 귀속과 C3 동일 위치-방향 교차대조의 필수 데이터는 미확보.
**원칙:** Git 파일명/manifest, 실행된 수치검사, 독립 과학적 감사의 범위를 분리한다.

## 1. 확인한 원본 데이터

| 자산 | 경로 | 확인 결과 |
|---|---|---|
| Full/LoS 복소 채널 | results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/FULL_RF/H_R{2,4,5}_aB_m0.npy, 같은 BLOCK_C의 H_LoS_R{2,4,5}_aB_m0.npy | 있음. 원본 [pose, 257freq, 2 RX, 2 TX] 복소 배열 |
| GT 및 pose alignment | BLOCK_C/{R2,R4,R5}_aB_m0/SAMPLES.json, INPUTS/timeline_R{2,4,5}_Tnone.csv | 있음. Tnone 기준 각각 979, 742, 1415시점 |
| FP 검출·편파 계산 | src/qclean_uwb/drivesim/observation.py | 있음. Hann→1028 tap IFFT→peak의 30% leading edge→s=(P+−P−)/(P++P−) |
| FFD ±45도 안테나 bank | 저장소 루트 LP_plus45_bank.npz 및 LP_minus45_bank.npz, research/FFD_P0P3_20261016/SOURCE_BANK_RECEIPT.json | Git LFS 저장 및 해시 검증 기록 확인. 이 조사에서 495MB 바이너리를 다시 materialize하지 않음 |
| 복도 scene·material | BLOCK_C/{R4,R5}_aB_m0/scene, MANIFEST.json | 있음. 원래 6면 PLY와 재료/기하 provenance |
| MB_VAR 원시 운동·관측·평가 | research/MBVAR_PRR_001_20261103/{A0_R1,A0_R3_REFIT,S1,S2,S3} | SHA/입력 manifest·실행 코드 있음. 이 조사에서 모든 LFS NPZ를 새로 읽어 실행하지 않음 |
| R2 확장 실행·감사 | POST_S3_PROPOSER_20261104/R2_EXTENSION/RESULT_KO.md 및 audit/RESULT_FINDINGS_R2.md | 완료·독립감사 ACCEPT 기록 확인. 독립 RF 환경 holdout 아님 |
| 반사경로별 분석 | research/R4B_RAY_ATTRIB_20261103/compute.py, Actions #41578225906 | R4 4개 pose 194/234/500/525의 JSON 결과만 있음. Full 전체 pose의 개별 path 복소 H는 미확인 |
| R4 168/172/173 및 R5 401/465/982 경로별 H | 해당 경로의 Full H는 합성 결과, 각 path 복소 성분 별도 파일 아님 | 미확보 |
| 동일 (x,y)에서 yaw만 변경한 대조 RF | 원본 R4/R5 궤적만 있음 | 미확보, 신규 최소 대조 시뮬레이션 요청 |

아카이브 원본 H는 R2 21,431,872 bytes × Full/LoS, R4 15,165,184 bytes × Full/LoS, R5 30,971,712 bytes × Full/LoS이다. SAMPLES 원본 pose 개수는 각각 1303/922/1883이며 Tnone 평가 개수와 다르다. pose_id mapping을 함부로 인덱스 연속성으로 추론해서는 안 된다.

## 2. 실행한 C0-A 기존 채널 재계산

[읽기 전용 C0-A 코드](c0a_aggregate_preflight.py)와 [Actions #41783949902](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41783949902), artifact mbvar-physical-c0a-41783949902: 12개 원본 SHA, 3개 route·3136시점, noise-free 257-bin composite channel의 FP/tap/s 재계산 PASS.

| 경로 | N | RF eMP RMS | abs(eMP)>0.3 | 그중 FP index 변동 |
|---|---:|---:|---:|---:|
| R2-B | 979 | 0.10822072 | 25 | 12 |
| R4-B | 742 | 0.13380699 | 39 | 27 |
| R5-B | 1415 | 0.09362439 | 30 | 27 |

정확한 항등식: sF(fpF)-sL(fpL)=[sF(fpL)-sL(fpL)]+[sF(fpF)-sF(fpL)], 최대 산술 오차 2.22e-16.
- R4 pose168, t33.6: eMP +0.3422; tap shift +2; same-tap +0.1104, tap-selection +0.2317.
- R4 pose172, t34.4: +0.3288; shift +1; same +0.1929, selection +0.1360.
- R4 pose173, t34.6: +0.3117; shift +2; same +0.1029, selection +0.2088.
- R5 pose982, t196.4: +0.5875; shift +2; same +0.1095, selection +0.4780.
- R5 pose465, t93.0: −1.2980; shift +16; same +0.1841, selection −1.4821.

원본 artifact SHA256: C0A_AGGREGATE_TAP_DECOMPOSITION.csv = c134fcc16f78220abc00485cafd09e9596d3b091817112a88e19de7177d85966; C0A_MANIFEST.json = cc65692fdbc17ca0f6c1359bce24b97b8aa05c63095fa40ae1a90c9c7e65d4b3.

**해석 경계:** 저장된 noise-free composite H에 대한 대수적 분해다. 두 항의 물리적 인과율, 반사별 기여, 센서 열잡음 조건의 ON/OFF 측위 성능을 증명하지 않는다. Actions 실행은 source-check에 해당하고 별도 독립 물리 알고리즘 검산이 수행된 것은 아니므로 독립 과학감사 PASS가 아니다. Actions artifact는 retention 90일이며 영구 Git 자료로 치환하면 안 된다.

## 3. 데이터 누락으로 차단된 주장

- Full 합성 H만으로 direct + 각 벽·바닥·천장 반사의 **복소 ray별 진폭/위상/지연/interaction chain**을 유일하게 분해할 수 없다.
- R4의 4개 ray JSON은 R4 33.6초, R5 196.4초를 포함하지 않는다. 원본 path solver 코드는 있으므로 추가 **결과 생성·게시** 요청이 적절하며 RF 채널 전체의 무조건적 재생성은 불필요.
- R4/R5가 다른 (x,y,yaw)를 지나므로 같은 pose의 yaw만 바꿔 RF를 비교할 자료가 현재 없다.
- C1/C2의 기본 입력은 존재하지만 전체 신규 인과 재귀 실험은 별도 계약/코드감사 후 수행. 역사적 S1–S3 결과가 새 개입 검증을 대신하지 않는다.

**최종:** C0A_COMPLETE_SELF_QA / C0B_MISSING_RAY_RESOLVED_DATA / C1_C2_EXISTING_INPUTS_AVAILABLE_NOT_RUN / C3_MISSING_MATCHED_YAW_DATA / NO_FULL_CAUSAL_GO.
