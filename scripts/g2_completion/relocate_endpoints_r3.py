"""Plan and write the R3 endpoint relocation overlay (no RF calls, R2 untouched).

    python scripts/g2_completion/relocate_endpoints_r3.py --out results/SIONNA_G2_ENDPOINT_RELOCATION_20260927_R3

Builds the R2 targets, finds every TX/RX group below 1 cm clearance against
the native geometry (and condition panels), searches the R2 placement rule
(g2_full_relocation), then re-applies the overlay and requires zero remaining
endpoints below 1 cm. Refuses to overwrite an existing overlay folder.
"""
import argparse
import collections
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_inputs import CLEARANCE_M, build_targets, endpoint_clearance
from rt_cp_uwb_py.g2_full_paths import file_sha, load_paths
from rt_cp_uwb_py.g2_full_relocation import DIRECTIONS, MAX_SHIFT_MM, REVISION_ID, plan_relocations

PATH_MAP = ROOT/'config/sionna_full_paths.example.json'
R2_FILES = ['CHANGED_LINKS.json', 'MOVES.json', 'MANIFEST.json', 'common/LINKS.jsonl', 'common/FRAMES.jsonl'] + \
           [f'inputs_v6/{f}/INPUT.json' for f in ('L1', 'L1multi', 'L2static', 'L2multi')]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out if a.out.is_absolute() else ROOT/a.out
    if out.exists():
        raise SystemExit('OVERLAY_EXISTS: create a new revision folder instead')
    config, paths = load_paths(PATH_MAP, 'repo_checkout', ROOT)
    targets, _, panels, _ = build_targets(paths['relocated_inputs'], paths['geometry'], paths['static9_contract'])
    rooms = [t['room_size'] for t in targets]
    moves = plan_relocations(targets, panels, paths['geometry'], rooms)
    overlay = dict(
        revision_id=REVISION_ID, status='ENDPOINT_RELOCATION_OVERLAY',
        decision='2026-09-27 user decision: move all TX/RX below 1 cm (native geometry) with the R2 rule',
        base_revision='SIONNA_G2_RX_RELOCATED_20260924_01a0d320_R2',
        base_inputs_sha256={n: file_sha(paths['relocated_inputs']/n) for n in R2_FILES},
        geometry_manifest_sha256=file_sha(paths['geometry']/'SCENE_MESH_MANIFEST.json'),
        rule=dict(threshold_m=CLEARANCE_M, horizontal_only=True, directions=[d[0] for d in DIRECTIONS],
                  step='whole millimetre', choose='smallest shift; tie -> larger clearance, then direction order',
                  max_shift_mm=MAX_SHIFT_MM, room_margin_m=CLEARANCE_M, path='every mm outside material',
                  clearance='slabs: one-sided NEGATIVE_NORMAL prism; ideal sheets: distance; '
                            'condition panels: sheet distance minus half thickness',
                  linked_rows='every row referencing the same (scene, role, coordinate)'),
        claim_boundary='1 cm is the existing synthetic placement rule, not a physical near-field threshold; the '
                       'far-field FFD model is not validated for antennas within centimetres of metal',
        moves=moves)
    # Re-apply and verify: no endpoint below the threshold remains.
    after, _, panels2, census = build_targets(paths['relocated_inputs'], paths['geometry'],
                                             paths['static9_contract'], overlay)
    clearance = endpoint_clearance(after, panels2, paths['geometry'])
    inside = sum(1 for t in after for v in t['clearance_m'] if v is not None and v < 0)
    verification = dict(remaining_below_threshold=len(clearance['violations']), inside_material=inside,
                        issues=census['issues'], r3_relocated_rows=census['r3_relocated_rows'],
                        targets=census['targets'])
    if clearance['violations'] or inside or census['issues']:
        raise SystemExit('R3_VERIFICATION_FAILED: ' + json.dumps(verification))
    out.mkdir(parents=True)
    (out/'OVERLAY.json').write_text(json.dumps(overlay, indent=1) + '\n', encoding='utf8')
    changed = [dict(family=r['family'], case_id=r['case_id'], role=m['role'], scene_id=m['scene_id'],
                    before=m['before'], after=m['after'], shift_m=m['shift_m'])
               for m in moves for r in m['linked_rows']]
    (out/'CHANGED_ROWS.json').write_text(json.dumps(changed, indent=1) + '\n', encoding='utf8')
    (out/'VERIFICATION.json').write_text(json.dumps(verification, indent=1) + '\n', encoding='utf8')
    code = ['rt_cp_uwb_py/g2_full_relocation.py', 'rt_cp_uwb_py/g2_full_inputs.py',
            'scripts/g2_completion/relocate_endpoints_r3.py']
    (out/'MANIFEST.json').write_text(json.dumps(dict(
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv, rf_calls=0,
        code_sha256={c: file_sha(ROOT/c) for c in code},
        outputs_sha256={n: file_sha(out/n) for n in ('OVERLAY.json', 'CHANGED_ROWS.json', 'VERIFICATION.json')}),
        indent=1) + '\n', encoding='utf8')
    print(json.dumps(dict(moves=len(moves), rows=len(changed),
                          by_family=collections.Counter(c['family'] for c in changed), **verification), indent=1))
    for m in moves:
        print(m['scene_id'][:24], m['role'], m['direction'], f"{m['shift_m']*1000:.0f} mm",
              f"{m['clearance_before_m']*1000:.2f} -> {m['clearance_after_m']*1000:.2f} mm",
              m['nearest_before'], len(m['linked_rows']), 'rows')


if __name__ == '__main__':
    main()
