# AMENDMENT-010 — prospective D2/D3/D4/D6 candidate, DRAFT ONLY

**IMPLEMENTER PRE-FREEZE DRAFT.** This file is NOT the applied AMENDMENT-010.md lock, and is not an execution authorization.

Original FROZEN A008/A009/A010-P0 and past C3/C3V4 FAIL evidence remain unchanged. `contract_lock.effective_lock` remains track-replacement merging.

## D2/D3 mathematical and receipt checks

- Preserve field-qualified full covariance receipts and their byte-level SHA256; cross-field numerical equivalence requires `delta_max <= 1e-10` AND `delta_F <= 1e-10` with symmetric SPD matrices.
- Separately gate RECEIPT_INTEGRITY (hash/array bytes), GENERATOR_LAW (independent K_pose, OU K_time and full Sigma), CROSS_FIELD_COV_EQUIVALENCE, FULL_C10_REPRO (ten entries, SPD and |delta log10(condition normalized by sqrt diag)| <= 1e-3).
- GEN_REGEN_Z byte equality is a reported diagnostic only; numerical replay is not generator correctness or posterior calibration.

## D4 dual verdict

- Explicit hard-gate allowlist is `code/a10_validation.py:G5_NUMERIC_GATE_IDS`; no suffix-based implicit filtering.
- Keep STATE_STABILITY_FIXED_LEGACY on all rows, including historic FAIL results. MODE_IDENTIFIABILITY is a separate scientific scope/status, never an automatic science PASS.
- All truth-free alternative starts are evaluated after comparable F2 polishing; the oracle truth start cannot select the operating mode. H/CAL analysis must retain all valid ambiguous rows.
- Near-cost alternative scientific effect/paired sensitivity, and independent multi-runner SOLVER_REPRO, remain required before science release.

## D6 full split replacement candidate

Old entire S_field is copied exactly from the effective lock obtained with existing frozen amendments, with DEV3 as the sole new track. No old HOLDOUT track restored. Never open DEV3 from this file.

```json
{
  "status": "DRAFT",
  "contract_id": "MBVAR-INFO-001",
  "amendment": "AMENDMENT-010",
  "proposer": "PROPOSER_DECISION_20261102",
  "source_impl": "9e0686602b612cd9f948e8a2f9f8e9098facd434",
  "handoff": "3e3bec436a23ef4eed27387234e085e7f4a46b2b",
  "baseline_amendments": [
    "AMENDMENT-001",
    "AMENDMENT-002",
    "AMENDMENT-003",
    "AMENDMENT-004",
    "AMENDMENT-005",
    "AMENDMENT-006",
    "AMENDMENT-007",
    "AMENDMENT-008",
    "AMENDMENT-009",
    "AMENDMENT-010-P0"
  ],
  "splits": {
    "S_field": {
      "SMOKE": [
        900,
        901
      ],
      "DEV": [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9
      ],
      "POST_HOC": [
        1000,
        1001,
        1002,
        1003,
        1004,
        1005,
        1006,
        1007,
        1008,
        1009,
        1010,
        1011,
        1012,
        1013,
        1014,
        1015,
        1016,
        1017,
        1018,
        1019,
        1020,
        1021,
        1022,
        1023,
        1024,
        1025,
        1026,
        1027,
        1028,
        1029,
        1030,
        1031,
        1032,
        1033,
        1034,
        1035,
        1036,
        1037,
        1038,
        1039,
        1040,
        1041,
        1042,
        1043,
        1044,
        1045,
        1046,
        1047,
        1048,
        1049,
        1050,
        1051,
        1052,
        1053,
        1054,
        1055,
        1056,
        1057,
        1058,
        1059
      ],
      "HOLDOUT2": [
        5000,
        5001,
        5002,
        5003,
        5004,
        5005,
        5006,
        5007,
        5008,
        5009,
        5010,
        5011,
        5012,
        5013,
        5014,
        5015,
        5016,
        5017,
        5018,
        5019,
        5020,
        5021,
        5022,
        5023,
        5024,
        5025,
        5026,
        5027,
        5028,
        5029,
        5030,
        5031,
        5032,
        5033,
        5034,
        5035,
        5036,
        5037,
        5038,
        5039,
        5040,
        5041,
        5042,
        5043,
        5044,
        5045,
        5046,
        5047,
        5048,
        5049,
        5050,
        5051,
        5052,
        5053,
        5054,
        5055,
        5056,
        5057,
        5058,
        5059
      ],
      "HOLDOUT2_RESERVE": [
        5060,
        5061,
        5062,
        5063,
        5064,
        5065,
        5066,
        5067,
        5068,
        5069,
        5070,
        5071,
        5072,
        5073,
        5074,
        5075,
        5076,
        5077,
        5078,
        5079,
        5080,
        5081,
        5082,
        5083,
        5084,
        5085,
        5086,
        5087,
        5088,
        5089,
        5090,
        5091,
        5092,
        5093,
        5094,
        5095,
        5096,
        5097,
        5098,
        5099,
        5100,
        5101,
        5102,
        5103,
        5104,
        5105,
        5106,
        5107,
        5108,
        5109,
        5110,
        5111,
        5112,
        5113,
        5114,
        5115,
        5116,
        5117,
        5118,
        5119
      ],
      "DEV2": [
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19
      ],
      "DEV3": [
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29
      ]
    }
  },
  "run_plan": {
    "S1V5": {
      "split": "DEV3",
      "fields": [
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29
      ]
    },
    "C3V5": {
      "split": "DEV3",
      "fields": [
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29
      ]
    }
  },
  "science_freeze": false,
  "can_execute": false,
  "code_sha256": "TO_BE_FILLED_AFTER_CODE_FINAL_AND_INDEPENDENT_AUDIT"
}
```

## Approval status

`SCIENCE_DRAFT`, `IMPLEMENTER_SELF_REVIEW_ONLY`, `AUDITOR_PENDING`, `DEV3_NO_GO`, `HOLDOUT2_NO_GO`, `RT_NO_GO`.