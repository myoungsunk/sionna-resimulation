# Native-LoS input provenance

The canonical range-mean generator, research/PJ_DS_GATED_20261021/mu_recursive.py, builds held-route estimators with .fit (lines 45,53), predicts channel-specific EXDS range corrections (63–70), and appends packet series only for Full (95–98). Its workflow .github/workflows/powerjoint-ds-gated-murec.yml uploads CSV, compressed CSV, and logs. MR_MEAS and MR_SCORES contain aggregate LoS outcomes. MR_SERIES contains Full rows only. The historical R4-B log records that LoS B0 ran. It cannot reconstruct the per-packet vector.

Existing separate-rs Native-LoS traces contain mu, R, and the following nine arms: JOINT4, POWER1, POWER_DIAG, SEP_DIAG, SEP_GLOBAL, SEP_BIN, SEP_MU_PWR_COV, PWR_MU_SEP_COV, SEP_BIN_BOX_GATE. None is MU_R_EXDS. The OOF_PARAMETERS table carries these same base/candidate models. Using its POWER_DIAG range mean would change the MB_VAR treatment.

To reopen this gate under the present contract: supply frozen channel-specific MU_R_EXDS per-packet predictions for R4_aB_m0 and R5_aB_m0 with pose IDs and source hashes, or the exact original fitted estimators and feature/transform lineage for inference-only recovery. If no such artifact exists, an explicitly versioned change of the channel convention or training restriction would be needed before designing a different baseline.
