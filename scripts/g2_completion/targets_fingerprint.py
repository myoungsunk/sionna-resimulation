"""Localise TARGETS.jsonl differences across environments (no RF, read-only).

    # fingerprint: whole-file SHA + one digest per field over all rows (small JSON, easy to diff)
    python scripts/g2_completion/targets_fingerprint.py TARGETS.jsonl --out FP.json
    # also split POSES/PANELS pointers: pass the inputs dir to fingerprint pose matrices by value
    python scripts/g2_completion/targets_fingerprint.py <inputs_dir>/TARGETS.jsonl --poses <inputs_dir>/POSES.json
    # row/field comparison of two files: counts, first differing rows, float differences in ulp
    python scripts/g2_completion/targets_fingerprint.py A/TARGETS.jsonl --compare B/TARGETS.jsonl

Nested fields are flattened (identity.case_id, frame_ref.frame, ...). A field
whose digest differs while identity/count digests agree points at the value
producing the byte difference; --compare then separates pure floating-point
representation differences (a few ulp) from substantive changes.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def flatten(row, prefix=''):
    out = {}
    for k, v in row.items():
        key = f'{prefix}{k}'
        if isinstance(v, dict):
            out.update(flatten(v, key + '.'))
        else:
            out[key] = v
    return out


def fingerprint(path, poses=None):
    whole = hashlib.sha256()
    fields, rows = {}, 0
    pose_table = json.loads(Path(poses).read_text(encoding='utf8')) if poses else None
    with Path(path).open('rb') as f:
        for raw in f:
            whole.update(raw)
            row = flatten(json.loads(raw))
            if pose_table is not None:
                row['pose.value'] = pose_table[row['pose_id']]
            rows += 1
            for k, v in row.items():
                fields.setdefault(k, hashlib.sha256()).update((canonical(v) + '\n').encode())
    return dict(file=str(path), rows=rows, sha256=whole.hexdigest(),
                field_sha256={k: h.hexdigest() for k, h in sorted(fields.items())})


def ulp_distance(a, b):
    if a == b:
        return 0
    if not (math.isfinite(a) and math.isfinite(b)):
        return math.inf
    return abs(a - b) / math.ulp(max(abs(a), abs(b)))


def diff_values(a, b, path, out):
    if isinstance(a, float) or isinstance(b, float):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            u = ulp_distance(float(a), float(b))
            if u:
                out.append((path, 'float', abs(float(a) - float(b)), u))
            return
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            diff_values(x, y, f'{path}[{i}]', out)
        return
    if a != b:
        out.append((path, 'value', None, None))


def compare(path_a, path_b, limit=20):
    stats, examples, rows = {}, [], 0
    with Path(path_a).open(encoding='utf8') as fa, Path(path_b).open(encoding='utf8') as fb:
        for la, lb in zip(fa, fb):
            rows += 1
            if la == lb:
                continue
            ra, rb = flatten(json.loads(la)), flatten(json.loads(lb))
            diffs = []
            for k in sorted(set(ra) | set(rb)):
                if k not in ra or k not in rb:
                    diffs.append((k, 'missing', None, None)); continue
                diff_values(ra[k], rb[k], k, diffs)
            for field, kind, absd, ulp in diffs:
                base = field.split('[')[0]
                s = stats.setdefault(base, dict(rows=0, kind=set(), max_abs=0., max_ulp=0.))
                s['rows'] += 1; s['kind'].add(kind)
                if absd is not None:
                    s['max_abs'] = max(s['max_abs'], absd); s['max_ulp'] = max(s['max_ulp'], ulp)
            if diffs and len(examples) < limit:
                examples.append(dict(row=rows, target_id=ra.get('target_id'), diffs=[
                    dict(field=f, kind=k, abs=a, ulp=u) for f, k, a, u in diffs[:10]]))
        extra = sum(1 for _ in fa) + sum(1 for _ in fb)
    return dict(rows_compared=rows, rows_only_in_one=extra,
                fields={k: dict(v, kind=sorted(v['kind'])) for k, v in sorted(stats.items())}, examples=examples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('targets', type=Path)
    ap.add_argument('--poses', type=Path)
    ap.add_argument('--compare', type=Path)
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    result = compare(a.targets, a.compare) if a.compare else fingerprint(a.targets, a.poses)
    text = json.dumps(result, indent=1, default=str)
    if a.out:
        a.out.write_text(text + '\n', encoding='utf8')
    print(text if a.compare else json.dumps(dict(rows=result['rows'], sha256=result['sha256'],
                                                 fields=len(result['field_sha256']))))
    sys.exit(0)


if __name__ == '__main__':
    main()
