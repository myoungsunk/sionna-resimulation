# POL-XCORR-001 — Unresolved reflection 편파 오염 지표 (proposer 패키지, DRAFT)

Status: **DRAFT**. 실행 결과는 없다. 허용 범위는 `P0_PREFLIGHT`뿐이다.

| 파일 | 역할 |
|---|---|
| `contracts/EXPERIMENT_CONTRACT_POL-XCORR-001.md` | 실험 계약(template 준수): authority, estimand, H1–H6, data/split, P0_TO_RESOLVE, 금지 표현 |
| `SCIENCE_SPEC.md` | 관측 체인, 물리 유도(F1–F4), 지표 M0–M4, label, 단계, 경쟁 설명, 산출물 스키마 |
| `config/PLAN_PARAMETERS.json` | 수치 설정 후보(W, L, 분위수, tolerance, seed) — FROZEN 전까지 비구속 |
| `config/INPUT_LOCK.json` | 입력 30개 sha256 (manifest 대비 불일치 0) |
| `PRE_CONTRACT_DISCLOSURE.md` | 계약 전 proposer가 본 것과 보지 않은 것 |
| `PROPOSER_FREEZE_CHECKLIST.md` | F-01–F-15 상태 |
| `CLAIMS.md` | 이 실험의 claim ledger |
| `TASK_HANDOFF.md` | 구현자·감사자 입력 헤더와 P0 순서 |
| `package_provenance/PACKAGE_MANIFEST.json` | 패키지 파일 sha256, contract sha256 |
| `00_PLAN_KO.md` | v0 선행 메모(대체됨, 이력 보존) |

Root `AGENTS.md`의 governance router는 MBVAR 범위에만 적용되므로, 이 패키지는 governance를 참조로 채택했다(F-01 결정 대기).
