# MBVAR-INFO-001 — A010 external-auditor waiver / governance change proposal

**Type:** `PROPOSED_GOVERNANCE_VARIANT`, **effective:** `FALSE`. **Date:** 2026-11-04.

## Existing governing requirement
`docs/research-governance/COMMON_CONTRACT.md §I/VI`, `ROLE_AUDITOR.md`, original `AMENDMENT-010.md` require independent math/code review by a different actor/session with a separate provenance. PR #20 recorded `ACCEPT_WITH_BOUNDARIES` on A18 technical work; a read-only report is **not** an independent GitHub `APPROVE` review of all A010 science. Connected GitHub user `myoungsunk` is the implementation/PR author; the account cannot create independent reviewer identity by using a different role label.

## Alternative if user expressly chooses to omit external GitHub approval

- **New prospective rule** (requires an explicit statement from the actual user approving this specific waiver and a durable GitHub appendix before execution): `USER_AUTHORIZED_NONINDEPENDENT_A010_FREEZE`.
- The **technical audit** remains `ACCEPT_WITH_BOUNDARIES` for precisely tested A18 code. No untested physical/RT/A010 field hypotheses are deemed supported.
- A self-review or same-account review is **`SELF_REVIEW_ONLY`**, not independent and must never set `independent_auditor_signed=true` or claim an independent auditor signature exists.
- With a waiver, any DEV3 experiment is labeled `USER_AUTHORIZED_EXPLORATORY` for release/governance purposes unless the publication-level independence and held-out validation are subsequently restored through a new audited contract. Original DEV3 field IDs remain reserved and not opened before the waiver takes effect.
- The user must choose the precise approval *scope* explicitly: external GitHub review omission for **A010 DEV3 internal exploratory work only**, NOT automatic HOLDOUT2, RT, independent-science-release, claims, or spending approval. This does not rewrite old approvals, historical FAIL, or user data.
- A durable effective-authorization record must contain `waiver_approved_by_user=true`, `approval_message_date`, `approval_scope`, `reviewer_status=USER_APPROVED_NONINDEPENDENT`, exact `base/source/contract/governance SHA`, and a rollback condition. No fabricated GitHub actor signature.

## Default decision right now

**The current user message directs “audit complete, freeze, prepare RT,” and reproduces an option to document waiver. It does not unequivocally state that an independent review requirement is waived.** Therefore this document does **not** silently activate the waiver. Maintain the existing independent reviewer gate until an explicit waiver is unambiguously recorded; no source `AMENDMENT-010.md` FROZEN transition from this proposal.

```json
{
  "proposed_procedure": "USER_AUTHORIZED_NONINDEPENDENT_A010_FREEZE",
  "approval_source": "USER_MESSAGE_2026-11-04_STATING_FREEZE_REQUEST_BUT_NOT_EXPLICIT_WAIVER",
  "user_waiver_approval": "NOT_ESTABLISHED",
  "active": false,
  "independent_auditor_signed": false,
  "external_github_approve_review": false,
  "a010_science_frozen": false,
  "dev3": "NO-GO",
  "holdout2": "NO-GO",
  "rt": "NO-GO"
}
```

**Alternative preferred path:** retain an independent named GitHub auditor with `APPROVE` on exact reviewed SHA and no waiver. Either way RT is a separate signed pre-P3 + user-approved numeric budget.
