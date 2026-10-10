# A23 분석 자료 인덱스

완료된 Q1 1,650회 결과와 분석에 필요한 실제 입력을 한 브랜치에서 받을 수 있도록 보존했다. 진행 중인 Q2/joint/L2 결과는 이 패키지에 포함하지 않았다.

| 용도 | 포함 위치 |
| --- | --- |
| 결과 읽기 | FINAL_REPORT_KO.md, retrieved/OUTPUT/A0_ARMS.csv, ARMS_controls.csv, ARMS_q1.csv, A0_UNIT_STATS.csv, ARM_UNIT_STATS_controls.csv, ARM_UNIT_STATS_q1.csv, A0_CHECK.json, RUN_MANIFEST_*.json, ARMS_REPORT.json |
| trace 정렬성 | retrieved/OUTPUT/TRACES/*.npz, 총 66개 전체 내용 |
| 잔차 분해 | INPUTS/H_R2_aA_m0.npy, hs_lut_2deg.npy, hs_lut_meta.json, freqs_hz.npy 및 실제 FFD bank 조각 전체 |
| 편향 상태 증강 대조군 설계 입력 | retrieved/OUTPUT/ARM_TARGETS.json, RESIDUAL_STATS.json, RESIDUAL_R2A_m0.npz |
| 원자료 대응·검산 | INPUTS/timeline_R2_Tnone.csv, rf_poses_R2.json, VERIFICATION.json, TRACE_PAIRING.json |

큰 FFD bank는 INPUTS/README_KO.md의 도구로 복원한다. 12개 조각을 모두 받으면 원래 NPZ 두 파일이 복원되며 원 production manifest의 SHA256과 동일하다. 자료를 게시한 것과 분석·새 실험을 완료한 것은 구분한다. F01/F02 및 scientific_PASS=false는 유지한다.
