# 전 거리 POWER 평균 A/B 실행 계약

- 질문 ID: IPALO-POWER-ALL-AB-20261119.
- 역할: IMPLEMENTER / 자기 검사. 독립 감사 없음.
- 부모 커밋: `40ef8f700f795dbb44c041cb4c0f0df73a9742d2`.
- 사용자 지시: “단·중·장거리 모두 POWER로 하고 나머지 조건은 그대로 유지해서 기존 기준과 비교 실행”, 결과 GitHub 업로드.
- 기존 기준선 불일치 보고 뒤의 계속 실행 승인도 유지한다. 원래 `1e-8` 허용치와 실패 판정을 기록하며 통과로 바꾸지 않는다.
- 고정 지침: [COMMON_CONTRACT.md](../../gm_theta_m6/inputs/COMMON_CONTRACT.md), [ROLE_IMPLEMENTER.md](../../gm_theta_m6/inputs/ROLE_IMPLEMENTER.md). SHA256 각각 `a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb`, `2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da`.

## 개입과 통제

기준 F2SKRWV는 0–6 m Kriging / 6 m 이상 POWER를 유지한다. 시험 F2SKRWV_POWER_ALL은 모든 거리에서 같은 동결 `SWEEP_CAL_B.npz`의 route별 `mu_s[i]`를 사용한다. 이는 `baseline_packet.muMB`에 이미 들어 있으므로 후보 `mu_s_fn=None`으로 Kriging 덮어쓰기를 끈다. 거리 평균 `mu_r`, 입력 패킷, 거리·편파 분산, c1/c0 V 표, GM/KI/NIS/Q, scorer/threshold 등은 바꾸지 않는다. 동률 처리 안정화 후보는 적용하지 않는다.

같은 복원 입력 B0/L2_GYRO_ARW × seed30–49 × R2/R4/R5. 기존 40조건 grid만 실행한다. H2/H2S는 평가 참조이며 시험군과 동일한 F2 분산 모델로 대체하지 않는다.

## 실행 전후 검사와 판정

- 원래 replay/scorer를 재사용하고 기존 기본 strict 게이트는 유지한다. 명시적 사용자 승인 탐색 경로만 사용한다.
- 40개 결과, 2400개 동결 기준선 scalar, 480개 trace 완전성·고유성·유한성 및 입력 시각/pose_id를 확인한다.
- 이전 원거리 시험의 H2/H2S/F2SKRWV 360개 trace와 상태·공분산·수용 mask·시각·Reff·prior/Pprior가 bit-exact인지 검사한다. 이것은 과거 역사적 기준선 통과와 구별한다.
- 후보 innovation에서 원래 native model 예측과 GM prior를 빼 사용된 두 평균을 역산한다. 모든 120 route/seed/조건에서 동결 POWER `mu_r,mu_s`와 최대 절대 오차 `1e-12` 이내인지 검사한다. c1/c0는 후보 자신의 prior 거리로 같은 동결 표를 조회하는지 확인한다. 입력 R_ref/gyro_Q/dt와 NIS threshold 정의도 검사한다.
- XY/Heading RMSE, Pose95/Heading95/XY95, NEES, 거울해 및 N_I/N_A/N_J를 같은 정의로 집계한다. seed별 FAR가 아닌 POWER/기준 RMSE 비율의 중앙값과 고정 bootstrap seed 20261119, 10,000회 95% 구간을 사용한다.
- 수치 기준 충족은 기술적 집계로만 표시한다. 과거 기준선 미통과, seed30–49의 사후 탐색, 같은 RF/환경 반복이라는 한계를 남긴다. 독립 확인·일반화·과학적 채택을 주장하지 않는다.
- 입력/출력/코드 hash, 코드 커밋, 환경, 명령, 시각, 종료 상태를 보존한다. 입력 누락·비유한 값·조건 오류·완전성 오류 등은 중단한다. 원본/선행 결과는 덮어쓰지 않는다.
