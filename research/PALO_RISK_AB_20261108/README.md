# PALO loss-risk study: stages A and B

- [실행 결과와 추가/제거 비교](REVIEW_AB_KO.md)
- [다음 턴 C/D 인계](NEXT_CD_KO.md)
- [동결 조건](results/CONTRACT.json)
- [수치 요약](results/SUMMARY.json)
- [추출/학습 코드](run_ab.py)
- [별도 산술 검산](verification/RECHECK.json)

A/B are executed fixed-prior diagnostics. C/D, new closed-loop policy performance, independent generalization and independent scientific audit are NOT completed. No operational code or source results were modified. Results retain negative and abstaining cases.

Runner: GitHub Actions 42445866720. Raw input is pinned to 16450dc14366ba4ed2cb4e151952493f0efc944f. Exact numerical dependencies are in `.github/workflows/palo-risk-ab-20261108.yml`.

Recompute into a new directory: `python run_ab.py --output NEW_OUTPUT`. Never reuse an existing output path. The `--publish` option is only for the configured GitHub Actions environment and publishes to the dedicated branch with a checked source-head lease.

For next-turn experiments use this branch, preserve results, and do not merge to main unless separately requested.
