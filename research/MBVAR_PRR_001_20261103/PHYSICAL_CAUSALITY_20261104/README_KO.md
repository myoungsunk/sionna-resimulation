# READ ME FIRST — MBVAR Physical Causality C0–C3

**기준:** PR #24 HEAD aac6fe8d4dba2bdaea3d531f3cf4fd196a773ce6 (2026-11-04)
**현재:** 기존 composite Full/LoS H로 C0-A 실험 완료; C0-B 개별 ray 데이터 및 C3 동일 위치 yaw 대조 부족. C1/C2는 기존 데이터로 가능하지만 새로운 인과 실험은 미실행.
**과학 판정:** 새 복구 모델 성공·전체 채택·실시간성 미승인. S1–S3/P0/N0B/R2_EXTENSION 기존 FAIL/NO_GO/HOLD 원본 보존.

## 읽는 순서

1. [DATA_READINESS_AUDIT_KO.md](DATA_READINESS_AUDIT_KO.md) — 원본 Git 자산 점검, 누락, 현재 C0-A 실행 결과.
2. [SIMULATION_DATA_REQUEST_KO.md](SIMULATION_DATA_REQUEST_KO.md) — Full ray path-level spectra/metadata 최소 생성 요청, SM0 canary→SM1 시간 구간→SM2 yaw-only 실험. **전체 RF 무조건 재생성 금지**.
3. [CAUSAL_VERIFICATION_PLAN_KO.md](CAUSAL_VERIFICATION_PLAN_KO.md) — C0-A/B, C1 거리·편파 동일 prior, C2 자연 재귀, C3 matched yaw 인과 대조의 설계와 주장 기준.
4. [INDEPENDENT_AUDIT_REQUEST_KO.md](INDEPENDENT_AUDIT_REQUEST_KO.md) — 단계별 별도 auditor와 수치·물리·과학 판정 항목, STOP.
5. [c0a_aggregate_preflight.py](c0a_aggregate_preflight.py) — 기존 frozen raw H/pose/FFT 체인에서 물리 eMP, FP tap, same-tap 및 detector-choice 대수 분해.
6. [C0A_EXECUTION_RECEIPT.json](C0A_EXECUTION_RECEIPT.json) — SHA, 전체 n=3136, 계산 실행 범위.
7. [.github/workflows/mbvar-c0a-physical-preflight-20261104.yml](../../../../.github/workflows/mbvar-c0a-physical-preflight-20261104.yml) — read-only Actions 재현.

## 실제 실행 결과

- [GitHub Actions #41783949902](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41783949902): SUCCESS, runner source SHA, full originals SHA12, 3136 aligned pose, C0-A physical first-path result. Artifact mbvar-physical-c0a-41783949902, retention=90d. **기존 raw data에서 실행했으며 새 Sionna RT simulation은 돌리지 않음.**
- R2=979, R4=742, R5=1415; extreme abs(eMP)>0.3: 25/39/30, 그중 tap shift: 12/27/27. 전체 항등식 residual 최대 2.22e-16.
- 기존 R4 native per-ray 분해는 pose194/234/500/525에 한정; R4 pose168/172/173, R5 pose982의 ray-resolved Full 계수는 이 패키지로 생성·검증하지 않음.
- C0-A는 집계 채널을 재계산했을 뿐 physical reflection path causal attribution이나 EKF C1/C2 전체 재귀를 검증하지 않음.

## 다음 승인 대상

시뮬레이션 실행자에게 SM0 최소 ray 데이터 요청을 전달한 뒤 별도 DATA_A0/C0B_CODE_AUDIT. C1/C2는 독립 code SHA/frozen contract 전 과학 실행 금지. 본 산출물은 **실험계획 및 데이터 준비·부분 실행**의 결과이며 새로운 알고리즘 채택 GO가 아니다.
