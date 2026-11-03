# DLP-P4-COV-001 — IMPLEMENTER D1 수행 지침 (감사 GO 전 실행 금지)

**Contract:** FROZEN_SCIENCE_CONTRACT_D1_KO.md. **Frozen SHA를 먼저 검증하고 AUDITOR의 GO_D1를 확보한 뒤에만 시작한다.**
**P4 base SHA:** e365b2f79eb86a3fd53d0d350f8e2d9364f285fe. 절대 연구 원본 변경 금지.

## 필수 실행 전 확인
1. INPUT_SOURCE_LOCK.json의 archive sha를 다운로드 실제 bytes와 비교. Original P4 12 trace ZIP / GT float64 archived legacy source / P1 6자리 proxy 검증. Original 84 case score로 독립 계산 패리티.
2. D1_NUMERIC_LOCK.json의 fixed chi-square thresholds, windows, strict phase/QA와 SHA 일치.
3. AUDITOR 사전 GO의 서명 주체, Git commit/contract/config/input lock SHA 재확인. 없거나 REVISION_REQUIRED이면 D1 STOP.

## D1 실행
- 원본 NPZ shape [n,7,4], Ppost [n,7,4,4]와 exact t/pose; 모든 route/mode/bias/arm.
- score window t>=30, float64 exact GT, yaw wrap, heading marginal vs conditional Schur, XY marginal; Cholesky solver, no regularization.
- per-epoch XY NEES, heading NEES, pose NEES, Schur conditional, eigenvalues/eigenvectors, major/minor error projection, 95% flags, original status.
- summary 84 case, paired AB/ABC & Full/LoS, fixed 10/20/40s independent window views, R4 onset 25-consecutive.
- 원본 Pose/Heading 지표 1e−9 이내, 원본 count/acceptance exact, Schur decomposition predeclared tolerance. 모든 실패와 반례 보존.
- overwrite/noise-fitting/new filter replay/RT/R adjustment/counterfactual gate is disallowed. Metadata scene_n=1.

## 필수 출력 / 제출
D1_MANIFEST, D1_QA, read-only source SHA verification, epoch CSV, 84 case summary, time windows, paired results, R4 onset, failures, D1 state-cov report. SHA of analysis code+output, command/environment, independent preauditor source URI and reviewer ID. Scientific hypotheses SUPPORTED/PARTIAL judgments are not made at D1.

**다음 전이:** D1 QA 완료 → 별도 사후 AUDITOR → D2 계약 동결/재승인.
