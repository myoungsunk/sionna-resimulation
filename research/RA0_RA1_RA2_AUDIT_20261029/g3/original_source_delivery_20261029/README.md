# G3 original trace recovery and delivery — 2026-10-29

Recovered the requested 23 NPZ files and their 23 original receipts from Snowball as `KMS`. No RT regeneration, H reconstruction, solver change, or G3 physical adjudication was performed.

- Archive: [G3_ORIGINAL_23_TRACE_PAIRS.zip](G3_ORIGINAL_23_TRACE_PAIRS.zip), 3,908,829 bytes.
- SHA-256: `4f625c84172fecd7539273eb8d19c841fd2eb204b61d9062a3b901cca6dc4a62`.
- Contents: exactly 46 requested source files under `results/S2/traces_*/`, plus one generated checksum manifest. No H or CONTROL payload was added.
- Group counts: R2_aB 1; R4_aA 3; R4_aB 3; R5_aA 9; R5_aB 7. Historical strict unmatched counts sum to 25 rays.
- All 23 receipt SHA-256 values match the frozen [source lock](../G3_23_ORIGINAL_SOURCE_LOCK.json).
- [File paths, sizes, and recovered byte hashes](G3_REQUESTED_SOURCE_MANIFEST.json).
- [Validation result](VALIDATION.json); reproduce with `python verify_delivery.py` (NumPy required).
- Existing [request and acceptance conditions](../REQUEST_25_ORIGINAL_RAW_RAYS.md) and [packaging script](../package_g3_23.py) are preserved.

## Provenance and execution

Repository base: `myoungsunk/sionna-resimulation`, branch `audit/ra4-factorial-g3-precision-20261029`, commit `e437593f9316e4852d9b63e920f1566b5a78f0c8`.

Source S2 directory:

```text
/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2
```

New remote delivery directory (retained for this transfer):

```text
/home/KMS/G3_SOURCE_DELIVERY_20261029_01a18744
```

The existing `package_g3_23.py` and source lock were copied into that new delivery directory. Snowball's host Python is 3.6: the initial invocation stopped with `SyntaxError: future feature annotations is not defined`, before packaging. A foreground stdin wrapper removed only that unused future-import line in memory and executed the otherwise unchanged script with the original S2 directory as its first argument and the copied lock as its second argument. Packaging then exited 0. Original source files and the committed packaging script were untouched.

The ZIP was copied with SCP. Local `verify_delivery.py` exited 0: ZIP SHA and CRC, exact membership, all 46 byte hashes/sizes, all 23 historical receipt hashes, NPZ required fields, shapes, finite tau/Jones values, coordinates, status, and historical unmatched counts passed. Array order and contents were preserved.

## Claim boundary

The original published manifest did not record NPZ hashes. These are files recovered from the preserved original execution directory with matching historical receipts; H reconstruction parity remains required for stronger provenance/physics acceptance. Delivery validation does not resolve the 25 rays' physical causes or promote G3 to PASS. Historical blocked findings remain unchanged as dated records.
