# Delta latent information and MB variance audit V1.1

Executed on 2026-10-28 using the original seven Full RF simulation cases, B0 only, and three held-route folds. These are simulation RF inputs, not hardware measurements.

Maintenance fix removes an unused dictionary with pandas Series keys from real-data aggregation. The aggregation and original case-count gate are covered by an added regression test. Models, thresholds, masks, and input data are unchanged.

Validation: 8/8 unit tests; seven original E1 replay parity checks; actual-data command exit 0; 14 output hashes verified. See validation/EXECUTION_RECEIPT.json and results/INFORMATION_AUDIT_STATUS.json. Original failure logs are retained under validation/original_failure. All pre-existing local code and results were preserved.

Scientific status: MEASUREMENT_INFORMATION_AUDIT_NOT_RECURSIVE_PROOF. Frozen-prior information gains do not establish recursive performance improvement from an added delta observation. MB_VAR recursive comparison is a separate diagnostic. GT-centered labels are offline only.

The code/README_KO.md, QA_REPORT_KO.md, and REAL_RUN_STATUS.json are supplied package documentation and retain their original pre-execution descriptions. The current execution evidence is in validation/ and results/. Local absolute paths in receipts describe the actual run environment; use code/RUN_REAL.ps1 with your own paths for reproduction. No experiment was rerun for this upload.
