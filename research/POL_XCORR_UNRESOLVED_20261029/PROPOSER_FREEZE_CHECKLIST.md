# POL-XCORR-001 — contract freeze checklist

근거 없는 체크는 무효. 독립 reviewer 기록이 있어야 각 행이 `DONE`.

| Gate | Required proof | 현재 상태 | 근거 |
|---|---|---|---|
| F-01 | root AGENTS 보존; 이 실험의 governance 적용 방식 결정(router append 또는 by-reference 유지) | PENDING (R-09, 사용자) | root AGENTS 미수정 |
| F-02 | full governance SHA, base SHA, contract sha256 | DRAFT_DONE | contract §Authority, `package_provenance/PACKAGE_MANIFEST.json` |
| F-03 | 입력 hash와 observer 체인 고정 | DRAFT_DONE (auditor 재계산 필요) | `config/INPUT_LOCK.json` (불일치 0), SCIENCE_SPEC §1 |
| F-04 | observer parity: s_fp 재계산 = HP_PACKETS | PENDING (P0, R-02) | — |
| F-05 | LoS 채널 rank-1 수치 floor, 이득 불변성 | PENDING (P0, R-03/F3) | — |
| F-06 | path trace 재정렬·jones 대응 검증 | PENDING (P0, R-01) | PRE_CONTRACT_DISCLOSURE #3 |
| F-07 | pose_id·phase 결합, segment 정의 | PENDING (P0, R-05) | — |
| F-08 | S0 유도식(F2) 독립 대수 검증 | PENDING (auditor) | SCIENCE_SPEC §2 |
| F-09 | tolerance가 결과 전 고정 | DRAFT_DONE | PLAN_PARAMETERS `tolerances_fixed_before_run` |
| F-10 | split·seed·bootstrap 단위 고정, scene n=1 및 holdout BLOCKED 명시 | DRAFT_DONE | contract §Data, PLAN_PARAMETERS `statistics` |
| F-11 | 검정력: route당 유효 1 m block 수와 최소 감지 ΔAUC | PENDING (P0 산출 후 기록) | SCIENCE_SPEC §7 |
| F-12 | per-realization oracle 우월 주장 금지, 금지 표현 목록 | DRAFT_DONE | contract §Implementation |
| F-13 | 신규 scene/RT 예산과 사용자 승인 | NOT_REQUESTED (P0–P3는 RT 불필요) | R-11 |
| F-14 | 독립 pre-run auditor 수용 | PENDING (R-10) | — |
| F-15 | CI negative fixture(잘못된 hash, LoS에 Δ 주입 시 ε>0 검출, train/test route 중첩) | PENDING (구현자) | — |

**현재 허용:** `P0_PREFLIGHT`(F-04–F-07, F-11 해결 목적). F-01, F-08, F-14, F-15가 PENDING인 동안 FROZEN 서명 불가.
