# AGENTS_ROOT_APPEND_PROPOSAL — POL-XCORR-001 (미적용, 사용자 승인 대기: R-09)

아래 블록을 root `AGENTS.md` **끝에 append**한다. 기존 MBVAR router와 다른 규칙은 수정하지 않는다. 적용 commit SHA가 POL-XCORR의 governance SHA가 되며, 계약을 v0.3으로 re-pin한다.

```markdown
## POL-XCORR polarization-contamination experiments — scoped role routing (APPEND-ONLY)

Only when a task touches `research/POL_XCORR_UNRESOLVED_20261029/**` or contract `POL-XCORR-001`:

1. Read `docs/research-governance/COMMON_CONTRACT.md`, then `research/POL_XCORR_UNRESOLVED_20261029/governance/GOVERNANCE_APPLICABILITY.md`, which states which MBVAR-specific rules APPLY, ADAPT or are N/A for this contract.
2. Read the latest experiment contract under `research/POL_XCORR_UNRESOLVED_20261029/contracts/` and its SCIENCE_SPEC, then exactly one role file (`ROLE_PROPOSER.md`, `ROLE_IMPLEMENTER.md`, `ROLE_AUDITOR.md`). A task must declare role, `contract_id=POL-XCORR-001`, full governance SHA, base SHA, and the draft or frozen contract sha256.
3. This routing does not override or relax any root `AGENTS.md` data-protection, scientific-claim, archive, or validation rule, nor the MBVAR routing above.
4. A DRAFT contract permits only `P0_PREFLIGHT` (source/math/geometry audit and label-free measurement). No metric–label relationship may be computed before FROZEN proposer+auditor sign-off.
5. Never overwrite prior contract versions, inputs, results or audit records; post-freeze changes require an amendment ID.

If the governance path is unavailable, report `BLOCKED_GOVERNANCE_NOT_INSTALLED`.
```
