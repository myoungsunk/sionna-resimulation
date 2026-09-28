"""Bounded S2 pilot report + capacity plan (no RF calls).

    python scripts/g2_completion/report_sionna_pilot.py --campaign-root <root> --inputs-dir 00_inputs_R3 \
        --batches B010040,B010041,B000337,B000381,B001868,B005973 --expected-rows 96 [--lanes 2 --threads 4]

Run where the raw NPZ are (server, inside the container). Writes
06_validation/S2_PILOT_REPORT.json and 03_pilot/CAPACITY_PLAN.json. The full
verify_sionna_full.py stays INCOMPLETE after a pilot by design.
Exit codes: 0 S2_PILOT_PASS, 3 otherwise.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_pilot import pilot_report  # noqa: E402
from rt_cp_uwb_py.g2_full_runner import atomic_write_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', required=True)
    ap.add_argument('--batches', required=True)
    ap.add_argument('--expected-rows', type=int, required=True)
    ap.add_argument('--batches-file', default='02_batches/BATCHES.jsonl')
    ap.add_argument('--runs-dir', default='batches')
    ap.add_argument('--lanes', type=int, default=2)
    ap.add_argument('--threads', type=int, default=4)
    a = ap.parse_args()
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    ids = a.batches.split(',')
    if not ids or any(not i for i in ids) or len(ids) != len(set(ids)):
        raise SystemExit('PILOT_BATCHES_INVALID')
    r = pilot_report(ROOT, root, a.inputs_dir, ids, a.expected_rows, a.batches_file, a.runs_dir, a.lanes, a.threads)
    (root/'06_validation').mkdir(exist_ok=True); (root/'03_pilot').mkdir(exist_ok=True)
    atomic_write_json(root/'06_validation'/'S2_PILOT_REPORT.json', r)
    atomic_write_json(root/'03_pilot'/'CAPACITY_PLAN.json', dict(r['capacity'], batches=ids,
                                                                  status=r['status'], expected_run_key=r['expected_run_key']))
    print(json.dumps(dict(status=r['status'], rows_verified=r['rows_verified'], problems=r['problems'][:20],
                          rf_calls_targets=r['rf_calls_targets'], rf_calls_fixture=r['rf_calls_fixture'])))
    sys.exit(0 if r['status'] == 'S2_PILOT_PASS' else 3)


if __name__ == '__main__':
    main()
