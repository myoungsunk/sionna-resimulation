# Snowball C00 phase convention and four-scene run

Base PR revision `c727703e2fc99d304fb97712220a7336b894d73e`. Executed source SHA-256 `79226718784565a5b7d414350ed2eeb884363ad547654d555065275df5ff9de4`. Scene lock SHA-256 `1c3eb577e3030edcf97a6f430054875d6a02d80a9912b179186a801bfdc47412`.

| Snowball run | Evidence | Decision |
|---|---|---|
| P3_PR33_20261104_185837 | previous_failure.tar.gz, previous_OUTPUT_SHA256.txt | C00 first repeat failed for all four poses, 1,028 native calls. Remaining keys were unexecuted. |
| P3_PR33_PHASE32_20261104_190821 | rerun.tar.gz, OUTPUT_SHA256.txt | C00 8/8 passed at the original relative L2 limit 1e-5. Paired scenes passed technical checks 24/24. All 8,224 native calls completed. |

The executed change restores the archive convention for the phase factor formed from frequency and the saved float32 path delay. The old run remains a recorded failure. The rerun used four workers within a shared logical CPU set of 0–31 and took 14 min 55 s. The 16 pairs of repeated complex H arrays were byte-identical. Results are nonindependent exploratory technical verification. EKF performance and temporal correlation were not assessed.

Each tarball contains original raw NPZ files, per-key manifests, logs and the original output hash list. Verify BUNDLE_SHA256.txt in this directory, then verify OUTPUT_SHA256.txt inside each separately unpacked bundle. The adjacent QA JSON and paired contrast CSV expose results without unpacking. The regression replays the four failed raw path records through the production C00 channel assembly and original parity check with an in-memory path reader; no native solver runs.
