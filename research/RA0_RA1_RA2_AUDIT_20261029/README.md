# RA0·RA1·RA2 감사 코드 및 증거 인계

이 경로는 기존 RF/BB/MB_VAR 데이터와 원본 실험 브랜치를 **수정하지 않고** 작성한 감사 전용 자료입니다.

## RA0·RA1
- [종합 보고서](ra0_ra1/RA0_RA1_MASTER_REPORT.md): 주장 의존성, 구현 정의, 유효·정정·폐기 근거, 위험순위, 최소 재실행 조건.
- 최초 보조 CSV/JSON 18개가 들어 있는 원본 ZIP은 사용자 대화 산출물 `RA0_RA1_AUDIT_PACKAGE_20261029.zip`에 보존. **해당 보조 18개 파일의 GitHub 원문 업로드가 완성된 것은 아님.** GitHub 버전에서 독립적으로 읽을 수 있는 RA0·RA1 주요 증거는 위 종합 보고서.

## RA2
- [초기 계약](ra2/RA2_CONTRACT_DRAFT.md) — 유효한 범위만 시작할 수 있는 DRAFT.
- [검산 코드](ra2/ra2_readonly_lineage.py) — 7개 case 원 SHA, SAMPLES/timeline/CONTROL, 별도 H→r,s 계산.
- [실행/감사 보고서](ra2/RA2_EXECUTION_AUDIT.md) — 7,251 packet-case row, 7/7 native parity.
- [G3 원인 감사](g3/G3_ROOT_CAUSE_AUDIT.md)와 [구조적 반례 스크립트](g3/g3_forensic_checks.py).
- [GitHub Actions](../../.github/workflows/ra2-observation-lineage-audit.yml): 실행 메타/receipt와 실패 기록은 기존 Actions run에 유지. 메커니즘·관측 검산 성공: https://github.com/myoungsunk/sionna-resimulation/actions/runs/40848193558

## 제안자 → 구현자 → 감사자 계약
- **PROPOSER:** source SHA, seven case keys, original LFS SHA, numerical tolerance and stop conditions are frozen in the contract/runner (수정은 새 git SHA에만).
- **IMPLEMENTER:** source download + sha verification, original H sample/timeline join, native r/s replay, negative fixtures; all under GitHub Actions, retains old FAIL runs.
- **AUDITOR:** separate logic and claim boundaries documented in RA2 audit and G3 audit. **This is SELF_REVIEW_ONLY: no separate independent auditor identity or session; no independent ACCEPT and no scientific release.**
- **Next gate:** actual source G3 per-ray `tau` access→26-row attribution→necessary focused RT canary and changed-H/packet impact only; separate RA3/RA4 estimator parity/ablation for sigma lookup/gate. No bulk RT or original result overwrite.

### 중요한 정의 제한
The seven-case H→packet equality is a **replay/source-integrity** check. It does not validate Sionna physical path correctness, generalization, or unseen scene efficacy. Current G3 class-tie code has a reproducible failing counterexample, but no per-ray classification has established that it explains all 26 actual mismatches.

### Read-only guarantee
Source under `results/`, original `research/DS_MASK_CAUSAL_X1_X2_20261026`, historic corrected G3, and frozen MBVAR-INFO contract were not edited by this audit branch. The branch starts at commit `f100a983cc389fcdef073592a254add61e7115da`.
