"""Whole-campaign coverage and integrity check (no RF calls).

    python scripts/g2_completion/verify_sionna_full.py --campaign-root <root> --inputs-dir 00_inputs_R3 \
        [--batches-file 02_batches/BATCHES.jsonl] [--runs-dir batches] [--out 06_validation/VERIFY.json] \
        [--raw-policy full|receipts-only]

Every judgement uses the key the *current* frozen inputs, runtime code and
full band produce (expected_run_key) and the current finish code
(production_key); results from any other configuration count as pending.

--raw-policy full (on the server, raw NPZ present): each raw NPZ is re-hashed.
--raw-policy receipts-only (collected copy, raw NPZ kept on the server by
policy): receipts and MANIFEST/COMPLETE are checked against each other and
the current key, and a server VERIFY.json produced with --raw-policy full
for the same key must be present; NPZ bytes are not re-hashed locally.

FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED only when all targets of the
campaign contract (165,009 targets, 101 scenes) are raw-complete and
finished under the current keys; never a G2 PASS or seal.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_runner import atomic_write_json  # noqa: E402
from rt_cp_uwb_py.g2_full_verify import verify_campaign  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', required=True)
    ap.add_argument('--batches-file', default='02_batches/BATCHES.jsonl')
    ap.add_argument('--runs-dir', default='batches')
    ap.add_argument('--out', default='06_validation/VERIFY.json')
    ap.add_argument('--raw-policy', choices=('full', 'receipts-only'), default='full')
    ap.add_argument('--server-verify', default=None, help='receipts-only: server VERIFY.json (raw-policy full)')
    ap.add_argument('--stage-manifest', default=None,
                    help='03_stage/STAGE.json that was deployed: judge with the shipped bytes (Windows collect)')
    a = ap.parse_args()
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    stage = json.loads(Path(a.stage_manifest).read_text(encoding='utf8')) if a.stage_manifest else None
    report = verify_campaign(ROOT, root, a.inputs_dir, a.batches_file, a.runs_dir, a.raw_policy, a.server_verify,
                             stage=stage)
    out = root/a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out, report)
    print(json.dumps(dict({k: report[k] for k in ('status', 'expected', 'raw_complete', 'finished', 'pending')},
                          stale=len(report['stale_or_other_key']), problems=report['problems'])))
    sys.exit(0 if report['status'] == 'FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED' else 3)


if __name__ == '__main__':
    main()
