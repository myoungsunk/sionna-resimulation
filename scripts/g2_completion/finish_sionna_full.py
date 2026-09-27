"""Post-process one COMPLETE batch into production channels (no RF calls).

    python scripts/g2_completion/finish_sionna_full.py --campaign-root <root> --inputs-dir 00_inputs_R3 \
        --batch-id B000000 [--batches-file 02_batches/BATCHES.jsonl] [--runs-dir batches]

Completion is judged against the key the *current* frozen inputs, runtime
code and full band would produce (expected_run_key), never the key stored in
COMPLETE: raw outputs from another configuration are refused
(RAW_KEY_NOT_CURRENT_OR_BATCH_INCOMPLETE). An existing production/ is skipped
only if FINISHED matches the current production key (raw key + operating
config + finish code) and every required CHANNEL/RESULT file is present with
its manifest SHA; any other existing production/ is preserved and the run
stops (PRODUCTION_STALE_OR_INCOMPLETE). Only full-band raw outputs are accepted.
Exit codes: 0 finished or already finished, 4 refused.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_finish import FinishRefused, finish_batch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', required=True)
    ap.add_argument('--batch-id', required=True)
    ap.add_argument('--batches-file', default='02_batches/BATCHES.jsonl')
    ap.add_argument('--runs-dir', default='batches')
    a = ap.parse_args()
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    batch = next((json.loads(l) for l in (root/a.batches_file).read_text(encoding='utf8').splitlines()
                  if json.loads(l)['batch_id'] == a.batch_id), None)
    if batch is None:
        raise SystemExit('UNKNOWN_BATCH')
    try:
        print(json.dumps(finish_batch(ROOT, root, a.inputs_dir, batch, a.runs_dir)))
    except FinishRefused as exc:
        print(f'FINISH_REFUSED: {exc}', file=sys.stderr)
        sys.exit(4)


if __name__ == '__main__':
    main()
