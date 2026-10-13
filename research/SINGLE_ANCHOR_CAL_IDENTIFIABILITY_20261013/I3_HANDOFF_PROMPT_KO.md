# 다음 I3용 인계 프롬프트 — 사용자 실행 승인 필요

이 문서는 다음 단계용 인계이며 새 스레드 생성이나 I3 실행 명령을 발행하지 않았다.

작업 위치 `D:/SLAM_bot/artifacts/dr_ekf_followup_audit_20261013`, 연구 폴더 `research/SINGLE_ANCHOR_CAL_IDENTIFIABILITY_20261013/`, 브랜치 `codex/dr-ekf-causal-followup-v2-20261013`을 사용한다. 먼저 루트 `I2_PUBLISH_RECEIPT.json`과 실제 원격 커밋·작업 파일을 확인하라. 로컬 HEAD는 오래된 부분 clone이므로 broad checkout/reset/status로 frozen 자료를 변경하지 말라.

공통 연구 계약과 사용자 stop gate를 유지한다. D6/V3/V4/I0/I1/I2 원본은 수정하지 않는다. 사용자 승인된 I3만 수행하고 I4/I7/V5는 실행하지 않는다. 새 결과 전 설계·셀·검증 기준을 별도 동결한다.

`I2_REPORT_KO.md`, `out/I2_DESIGN.json`, `out/I2_VERIFICATION.json`, `out/i2_run_01/I2_REFERENCE_VALIDATION.json`, `I2_RUN_MANIFEST.json`을 먼저 읽어라. I2는 27 테스트, 144 primary PF, 8 high-N 반복, 4 batch case를 완료했으나 **모든 선별 참조는 REFERENCE_NOT_VALIDATED**다. Range 128회 모두 초기 Calibration 계보 <100, MCMC Rhat 2.22–6.61/최소 ESS 12.47–16.53 수준이다. PF 실패를 구조적 비식별성이나 센서 정보 부족으로 해석하지 말라.

I3 동일 입력 후보는 Gaussian R2/R4 d2 seed8000의 DR와 `RANGE_0.05_5`이다. 해당 episode 폴더의 `*_public.npz`와 `*_config.json`을 그대로 사용하고 SHA를 대조하라. 참 Calibration·true pose는 별도 `truth.npz`에 있고 추정기에 전달하지 않는다. I2 target은 static calibration conditional measured-input Gaussian + SE2이고, 물리적 생성 likelihood 전체와 같다고 주장하지 않는다. Batch는 terminal full-horizon이고 intermediate smoothing을 online filtering과 혼동하지 않는다.

먼저 posterior 참조 개선을 사전 설계하라. 표적 likelihood를 보존하는 수렴 개선과 독립 반복/입자 수/chain 진단이 필요하다. 인위적인 parameter jitter, covariance inflation, PSD repair, 결과 후 임계값 완화로 통과시키지 말라. 수렴 미달은 미검증으로 유지한다. 이후에만 같은 허용 관측·prior에서 frozen EKF/CKF/PF/batch를 비교하고 Calibration marginal/joint 영역, 실제 오차·포함률을 검토하라. seed 단위 paired 통계를 사용하라.

실용적 운용 요구는 사용자가 미정으로 답했다. 성능 곡선만 허용되며 충분/부족 판정은 보류한다. S0는 gauge·초기 위치 범위가 별도로 전달될 예정이므로 수치 계약 없이 실행하지 않는다. F0는 LUT 검증 실패로 NOT_RUN이다. RF 학습·실행 provenance 미해결 사항과 I1 최적화 2개 시작점 반복 한도, I1 구현 후 감사 미완료 기록을 보존한다.

끝에 구현·검증·실행·과학적 판정을 구분해 결과/한계/정확한 파일·해시·실행 환경·다음 단계 인계를 기록하고 종료하라. 후속 스레드 생성은 사용자 또는 별도 전달 담당의 지시를 기다린다.
