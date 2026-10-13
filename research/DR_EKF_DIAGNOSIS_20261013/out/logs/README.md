# 실행 로그 (stdout/stderr 그대로)
| 파일 | 실행 | 상태 |
|---|---|---|
| D0_TRACE_B0_s6000-6299.log | `diagnose_dr_trace.py --arms B0 --seeds 6000:6300 --check-r22 --dump R2:2:6000` | 완료 (R2-2 재현 PASS) |
| D4_ABLATION_s8000-8031.log | `ablate_dr_calibration.py --seeds 8000:8032 --procs 3` | 완료 |
| D5_NONLINEAR_s8000-8031.log | `compare_dr_nonlinear.py --seeds 8000:8032 --procs 4 --reuse` (중간 수정 전 코드로 실행; 요약 JSON은 이후 strict writer로 재생성) | 완료 |
| D5_PF_VALIDATION_V2-V4.log | `validate_dr_pf.py --parts V2 V3 V4 --procs 4` (V1은 별도 실행) | 완료 |
| D6_RUN_EKF_CKF_ARMS_s8100-8399.log | `confirm_dr_independent.py --only-arms B0 ORACLE_CAL NO_C A2_3_GAUSS_LEVEL A2_3D_GAUSS_DEFAULT CKF_A2_3` (구버전 실행 모드; 계산만, 판정 없음) | 완료 |
| D6_RUN_PF_A2_3_s8100-8399.PARTIAL.log | `confirm_dr_independent.py --run-arms PF_A2_3 --procs 4` | 진행 중 — 완료 시 최종 로그로 교체 |
