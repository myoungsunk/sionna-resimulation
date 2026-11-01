# P1 실행 잠금 제안 및 중단 영수증 — 2026-11-01

**IMPLEMENTER / DLP-EKF-GAPS-001.** 사용자가 P1 진행을 지시했으나 실험 계약은 DRAFT-0.1, `allowed_experiment_phase=NONE`, proposer+auditor FROZEN 서명 없음. 기존 채택 governance에 따라 수치/모델/RT/replay 실행은 **BLOCKED_CONTRACT_NOT_FROZEN**; 이는 사용자 지시 거부가 아니라 사전 승인된 재현성/역할분리 중단 조건 준수다.

## 이번에 진행한 작업
- SourceFFA/legacy 관측 및 4state motion source와 상수 값을 immutable 기준 sha에서 직접 재열람.
- `P1_PROPOSED_CONFIG_LOCK.json`에 기존 RR/RS/B_OLD, chi2 gates, bias, x/P 설정을 **unfrozen candidate**로 기록.
- 기존 Snowball 복구, P0 해시, P1–P4 정합표와 별도 신규 재계산 범위를 연결.
- SourceFFD `h_s`만 바꾸는 matched ablation vs 훈련 평균·공분산까지 변경하는 복합 실험은 분리 제안. `h_r=d+B_OLD`는 아직 detector 기반 likelihood가 아니라 기존 연속 surrogate.
- SourceFFD P0P3에 선행 훈련/재귀 결과가 보고돼 있으므로 기존 ZIP 및 전체 runner/trace를 먼저 복원하고 **기존 수행량을 신규 P1로 중복 실행하지 않도록** provenance crosswalk 요구.

## 실제 미실행 상태
- new RF / original H modification: NOT_RUN.
- H→CIR→r,s fresh numerical parity: NOT_RUN (new prior P0 provenance available).
- source FFD h/J and signed residual recalculation: NOT_RUN.
- train-only refit and any covariance evaluation: NOT_RUN.
- EKF full recursive and metric recalculation: NOT_RUN.
- independent audit / frozen sign-off: NOT_RUN.

## 제안자+독립 사전 감사자에게 필요한 결정
1. Canonical seven paired C0 primary, recovered 4 Full-only optional expansion, no implicit NativeLoS for them.
2. SourceFFD model and original FFD bank binary SHA, producer/extractor SHA, exact sensor/time and calibration evidence fixed.
3. Historical `B_OLD, Rr, Rs, Rsr=0, chi2` as candidate; change only with independent protocol amendment.
4. Exact P1 estimand, experimental arms, train-only routes and no-leakage keys, 4state f/F/Q/x0/P0/seed.
5. Separate deterministic model parity tolerance vs physics H and detector temporal quantization; never calibrate tolerances on observed performance.
6. Freeze a new contract revision and obtain independent pre-run auditor approval before scientific recalculation.

**Next gate:** proposer freezes science-affecting choices and pre-run independent reviewer signs. A user's explicit `P1 진행` constitutes execution intent but does not supply the missing science config or independent audit certification. Do not invent auditor signature.

No prior files modified, no FROZEN claim, no independent scientific verdict.
