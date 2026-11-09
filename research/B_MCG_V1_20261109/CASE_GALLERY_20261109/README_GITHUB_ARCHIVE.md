# B-MCG 506-case gallery — GitHub reproducibility entrypoint

This repository contains **all 506 case entries**, the 6,272-row two-calibration trajectory/IMU/heading/RF table, the three per-route RF/CIR feature CSVs, and the four Python analysis scripts. The full research data/code ZIP is preserved losslessly as eight base64 ASCII Git blobs, with SHA256 checked on reconstruction. The original 13,488,962-byte self-contained interactive HTML is preserved losslessly as 20 Git blobs; both archives are intended as **version-controlled, byte-exact**, not newly generated experiments.

## Reconstruct

```bash
cd research/B_MCG_V1_20261109/CASE_GALLERY_20261109
python assemble_science_data.py --extract
python assemble_interactive_html.py
```

Expected science ZIP SHA256: `75098d5ca6803c90f762e283b381701b7a068ee47d9eea0322543bb5095203e4`.
Expected HTML SHA256: `e707f55e879a8054c9df1a57fa50554eb1edbfad306039958554589bd6904c0f`.

Reconstructed files include `FULL_ENRICHED_6272.csv`, `PRIMARY_R2_RF_CIR_FEATURES.csv`, `PRIMARY_R4_RF_CIR_FEATURES.csv`, `PRIMARY_R5_RF_CIR_FEATURES.csv`, `CASE_CATALOG.csv`, four analysis scripts and audit metadata. The interactive HTML is a **self-contained offline gallery** with 506 index entries and 6,272 rows stored in the page's JavaScript. Static PNG panels can be re-rendered after extraction using `python export_panels.py --max 115` (NumPy, pandas, Matplotlib, NanumGothic). Output image pixels may vary across rendering environments; original PNG snapshots remain in the ChatGPT handoff ZIP.

Scientific status: **analysis of archived B-MCG outputs, not new RF runs**. Same RF observation can have different state-update effect because prior heading, prior XY, covariance, calibration mean and Kalman gain all vary. The captured R5/k435 comparison isolates their observed association but does not claim heading-only causal attribution.
