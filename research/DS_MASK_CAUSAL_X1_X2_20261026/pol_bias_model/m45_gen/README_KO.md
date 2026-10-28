# 마운트 45 packet 입력 생성 (5개 경로) — 원래 특징·OOF 코드로 재생성

입력: 복원된 마운트 45 Full RF H 5개(`research/DS_INPUT_PROVENANCE_20261028/mount45_recovery/FULL_RF`, 커밋 `b17b0f5`, SHA-256 일치 확인),
저장된 특징·OOF 표(`DS_INPUT_PROVENANCE_20261028/prepared`, 커밋 `6000803`), 기존 7개 경로의 Full RF H.
새 Sionna 시뮬레이션은 없다.

## 생성 절차 (원래 코드 그대로 import)
| 단계 | 원래 코드 | 산출 |
|---|---|---|
| 특징·라벨 | `PHYSICS_RS_STAGED_20261015/code/features.py` `extract()`; 라벨은 참 자세의 SourceFFD 예측 대비 (`power_oof_experiment.build_dataset`) | z = [range_m, s_fp], 특징, e_r, e_s |
| μ_B, R | `R5_N4B_20261015/n4b_rf_errors.fit_model('POWER_BIN_JOINT')`, `site_weights` → POWER_DIAG (`power_oof_experiment.fit_models`) | μ_B = (mu_r, mu_s), R = diag(Vr, Vs) |
| μ_M | `series_dump.taps` + `mu_recursive.hgb(EXIST+DS, 'e_r')` (HGB, random_state 0) | μ_M = (EXDS 예측, mu_s) |
| 수용 mask | gate가 있는 BASE 필터 (`exp_pb.gated_mask`, GATE_JOINT 9.2103) | A_B, gyro bias 단계마다 |

학습 집합은 **원래 fold 그대로**다: 기존 7개 경로의 Full 행, 대상 경로 제외(POWER는 대상 XY와 1e-4 m 이내 중복도 제외).
마운트 45 새 경로는 예측만 하고 학습에 넣지 않는다. 학습 행 수가 원래 fold와 같다(R2 fold 5608/5610, R4 7672/7675, R5 5753).
R2 fold는 45° 학습 행이 0개이므로 R2_aB_m45의 μ는 마운트 외삽이다. R4/R5 fold는 R2_aA_m45를 포함한다.

## 재현 gate (기존 7개 조건, `gate.py`, `gen_packets.py`)
- 특징·라벨: 저장 표와 최대 차이 7e-15 (20개 열 모두).
- POWER_DIAG μ_B, Vr, Vs: 최대 1.4e-16.
- EXDS μ_M: scikit-learn 1.5.2 / 1.6.1 / 1.7.2에서 **0 차이**, 1.9.1에서는 최대 5–10 cm 차이 → **scikit-learn 1.7.2로 고정**.
- 조립한 packet z, μ_B, μ_M, R 대 저장된 E1 CONTROL trace: 최대 1.8e-15 (7개 경로 모두, `PACKETS_REPORT.json`).
- 수용 mask: gate BASE 필터가 저장된 14개 mask를 정확히 재현(앞선 확인).
- 마운트 45 trace의 시간·pose_id·truth는 같은 경로 마운트 0 trace와 같다(R2_aA_m45 대 R2_aA_m0 pose_id 동일 확인).

스크립트는 작업 공간에서 실행한 그대로이며, 입력 경로(src/research, reflect_model)는 실행 환경 기준이다.

`packets/PACKETS_<case>.npz`: t_s, pose_id, truth, z, mu_B, mu_M, R, mount_deg, anchor. 기존 7개는 parity 확인용, 새 5개가 실험 입력이다.
