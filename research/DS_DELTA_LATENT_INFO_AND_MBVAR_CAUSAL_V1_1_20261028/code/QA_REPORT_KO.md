# 전달 QA 보고서

- `ds_info_audit.py` 문법 컴파일 PASS.
- `test_ds_info_audit.py` **7/7 PASS**: native-time centered smoother, LORO training에서 held-route leak 없는지, signed 3×3 covariance SPD, full 5D conditional information monotonicity 20 stochastic SPD cases, zero-added-information parity, spectrum/first-tap extraction, synthetic end-to-end CLI.
- 고정된 E1 EKF (`dsreassess/engine.py`)와 Stage7 fake fixture를 가져와 `var_failure_traces()` 통합 합성 QA **1 PASS**: 원래 MB replay parity, 동일 prior K0/K1 비교, 207 accepted packets, 원래와 VAR 점수 출력. QA fixture는 배포 ZIP에 포함하지 않는다.
- 합성 3route 명시적 인공 상관: 학습 slope [0.2735, 0.2834, 0.2845], 전체 prior heading σ 1.21–1.24°에서 Δs 추가 σ 0.83–0.85°로 줄어드는 수치가 계산됨. **실제 RF 수치가 아님.** 합성 시각화/숫자를 실제 결과로 인용하지 말 것.
- 실제 Full RF `.npy`, SourceFFD 은닉/원본 bank가 로컬 컨테이너에 없어 실제 RF 데이터에 대한 작업은 **미실행**. `--mode real`은 사용자 동결 p2 / Git LFS 바이트가 있는 환경에서만 실행 가능.
- 별도로 GitHub의 `run_40652679303/PB_SCORES.csv`에 대해 Heading RMSE²=Bias²+Std²를 직접 재산출하여 R2_m45/B0의 MB_VAR 편향 확대(1.086→1.689°)와 R4_aB 편향 복구(-0.422→-0.223°) 확인.
- 코드 원본 checkout 읽기 전용, 새 output-root만 쓰기; 실패 시 `FAILED.json`와 비영 종료, 완료 상태는 `MEASUREMENT_INFORMATION_AUDIT_NOT_RECURSIVE_PROOF`.
