# Snowball B안 최종 결과

2026-10-07 19:14:59 KST에 S6와 analyze_experiments.py가 완료됐다. 컨테이너 exit 0. **18,000 runs, 실패 0**, 네 lateral×mount 조건 각각 4,500행이며 H1-H4 분석에 사용된 EKF runs는 10,800이다. 요청 산출물 누락 없음.

실행 원본 commit: 1b9cf190244f91d0097a82106a02ec1dd5f53220. 사용자 승인에 따라 이번 B eligibility에만 G3 허용치 2e-13 s를 적용했다. 저장된 trace와 원래 rf_b_apply.py로 네 H 저장소를 조립·검증했으며 원시 H/NPZ는 이 게시물에서 제외했다. S1·trace·bank·LUT 입력과 다른 gate 임계값은 보존했다.

## 판정과 한계

- Parity all_passed=true. 개발 수치와 정확히 같지는 않음.
- 원래 G3 strict 5e-14 s: y0 FAIL (6 unmatched), y0.35 PASS. 승인 relaxed 2e-13 s: 둘 다 PASS.
- L1 FAIL: max 0.023972114650869493, median 0.0005302414729959071.
- L2 FAIL: max 0.010448905754996851 > 0.005 (8 cases).
- **실행 완료는 production/scientific PASS가 아니다.** S6는 위 FAIL을 유지한 진단 결과다. 물리적 경로 유일성·동등성 및 실패 원인이 반올림뿐이라는 주장은 미확립이다. 시뮬레이션 센서 매개변수는 placeholder이며 `s`는 q_clean이 아니다.

## S6 설정과 주요 수치

`--snr-db 30 10 --mismatch-sigma 0.18 --pos-process-std 0.01 --seeds 50 --nproc 4`

원래 분석기가 산출한 EKF 전체 조건 중앙값:

| baseline | heading RMSE (deg) | position RMSE (m) |
|---|---:|---:|
| odom_imu | 7.78545 | 1.23063 |
| range_s_P0 | 2.38901 | 0.58653 |
| range_s_P1_T10 | 1.57987 | 0.29987 |

분석 CSV의 개선 판정: H1 vs odom_imu 19/24, H1 vs gyro_only 18/24 (악화 2/24), H2 24/24, H3 12/12. 이는 이번 진단 데이터의 분석 결과이며 채택·현장 검증을 뜻하지 않는다.

## 개발 결과와 별도 비교

LUT mismatch overall RMS: Snowball 0.18020465309084338, DEV 0.18020611764999286, 차이 -1.464559149483291e-06.

SNR calibration은 Snowball samples=184/draws=20, DEV samples=153/draws=10으로 설정이 달라 동일 조건 재현 비교가 아니다. 모든 공통 수치 차이는 B_RESTART_20261007_01a115bd/COMPARISON_SNOWBALL_DEV.json에 기록했다. DEV의 S6는 5-seed SMOKE_ANALYSIS_5seeds_NOT_EVIDENCE.md뿐이며 이번 50-seed S6의 동일 조건 기준 결과는 MISSING이다. 정확한 수치 재현을 주장하지 않는다.

## 파일

PARITY_REPORT와 두 G3 JSON은 S2/, 기존 LUT 판정은 S4/, 최종 S6 CSV·manifest·ANALYSIS와 SNR 보정·LUT mismatch·승인 변경은 B_RESTART_20261007_01a115bd/ 아래에 있다. FINAL_B_20261007T1017Z.zip에 1,836개 trace receipt JSON, 실행/status/log/provenance 및 DEV 기준 파일을 포함해 총 1,925개 파일을 보존했다. ZIP과 내부 개별 파일 SHA256 전송 검증 완료. raw H/NPZ·비밀정보·실험 ledger는 포함하지 않는다.

ZIP SHA256: `213123d54cbd1129bb6e31cf113c3df50e911a8c87ff70729e718e4a2ee37c90`.
