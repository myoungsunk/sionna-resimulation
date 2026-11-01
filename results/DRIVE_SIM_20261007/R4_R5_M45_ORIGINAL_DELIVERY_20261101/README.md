# Historical R4/R5 Mount 45 degree originals recovered on 2026-11-01

Recovered existing 2026-10-07 Snowball files from:

```text
/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2
```

Download [R4_R5_M45_ORIGINAL_20261007.zip](R4_R5_M45_ORIGINAL_20261007.zip) (88,656,933 bytes). All original bytes and source-relative paths are preserved inside the ZIP.

| Original H file | Shape | Historical SHA-256 |
|---|---|---|
| H_R4_aA_m45.npy | 922 x 257 x 2 x 2 | 5eabb1e44677bdf82630cdf9eea43cad729af2459b9b790d246310d62b725724 |
| H_R4_aB_m45.npy | 922 x 257 x 2 x 2 | 3f76d713edccf90ed1d20c8e0f65064add3ca5c5340b56d11c1f391ca81c791d |
| H_R5_aA_m45.npy | 1883 x 257 x 2 x 2 | 1e2c2f36c8d4945e3868c418875b6f08e459c669bcdad981318daf4521ecfbc2 |
| H_R5_aB_m45.npy | 1883 x 257 x 2 x 2 | 8f0d87f213a04d6861d6de12f557ce5ce4ae2ba369b9c94e49496bc4f3e154e9 |

Each array is complex128, in the recorded `[pose_id, bin, rx(+45,-45), tx(+45,-45)]` order. Original manifests record `mount_deg=45.0`.

The ZIP includes exactly 10 original files: the four H arrays, their four unmodified `.manifest.json` files, and original `S1/routes/rf_poses_R4.json` / `rf_poses_R5.json` (for pose ordering). One newly generated `DELIVERY_MANIFEST.json` adds recovery hashes and provenance. Mount 0, R2 and mount-independent trace NPZ folders are outside this delivery's requested scope.

## Verification and provenance

- Base commit: `f98503f35469ddaa907b2aa2041c9a5e3a72eb21` of `myoungsunk/sionna-resimulation`.
- [SOURCE_LOCK.json](SOURCE_LOCK.json) pins each historical manifest hash to the committed `final_20261007T140446Z/TRANSFER_MANIFEST.json`. Historical manifest bytes match 4/4.
- H SHA-256/size matches each original manifest 4/4. Both pose lists match the hashes/sizes in those manifests.
- ZIP SHA-256: `5e6622da9f01d4de65c83de763e71c77f66a21003b03f4aaeb1aba8dd6cf34ef`.
- [TRANSFER_VERIFICATION.json](TRANSFER_VERIFICATION.json) records every file's source-relative path, hash, size and recovery timestamp.
- [LOCAL_VALIDATION.json](LOCAL_VALIDATION.json) records the second verification after SCP: ZIP SHA/CRC/membership, all 10 file hashes, historical hash chain, shapes, complex128 type, finite values and mount setting.

Commands executed in sequence (both exited 0):

```text
# Snowball, foreground Python 3.6; source files read only
python3 /home/KMS/R4_R5_M45_ORIGINAL_DELIVERY_20261101_01a18744/package_originals.py
# After SCP, local Python with NumPy
python verify_delivery.py
```

The [packaging script](package_originals.py) and [verification script](verify_delivery.py) are included. The new remote delivery folder is retained as `/home/KMS/R4_R5_M45_ORIGINAL_DELIVERY_20261101_01a18744` for transfer recovery. No background helper was started.

No original source file was changed, moved or regenerated. This delivery does not execute MBVAR C3/C3V4/A010, open HOLDOUT2, perform new physical RT, or change any historical gate verdict. The checks establish byte identity and array structure, not scientific acceptance or new H reconstruction parity.
