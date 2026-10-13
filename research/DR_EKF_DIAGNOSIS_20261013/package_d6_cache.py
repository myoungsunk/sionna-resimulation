"""Package / restore the D6 confirmation caches (seeds 8100-8399) for plain-git storage.

Git LFS uploads are refused for this repository, so the caches are stored as ordinary git blobs (LFS disabled for
cache/ by cache/.gitattributes). GitHub rejects files > 100 MiB, so such files are split into byte-exact 64 MiB parts
<cell>.npz.partNN; the original <cell>.npz stays local and is git-ignored. CACHE_D6_MANIFEST.json records the SHA256
and size of every original file and of every part, plus the arrays it contains.

usage:
  package_d6_cache.py pack [--arms ...]   split oversized files, (re)write the manifest and the ignore list
  package_d6_cache.py restore             rebuild <cell>.npz from parts where missing, then verify every SHA256
  package_d6_cache.py verify              verify originals (if present) and parts against the manifest
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'cache'
SEEDTAG = 's8100-8399'
LIMIT = 100 * 1024 * 1024 - 1          # GitHub hard limit is 100 MiB
PART = 64 * 1024 * 1024
MANIFEST = CACHE / 'CACHE_D6_MANIFEST.json'
IGNORE = CACHE / '.gitignore'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def d6_dirs(arms=None):
    out = sorted(p for p in CACHE.glob(f'*_{SEEDTAG}') if p.is_dir())
    return [p for p in out if arms is None or p.name[:-len(SEEDTAG) - 1] in arms]


def pack(arms=None):
    doc = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else dict(
        note='D6 confirmation caches (seeds 8100-8399), plain git; parts are byte-exact slices of the original file',
        part_bytes=PART, files={})
    for d in d6_dirs(arms):
        for f in sorted(d.glob('*.npz')):
            rel = str(f.relative_to(CACHE))
            size = f.stat().st_size
            digest = sha256(f)
            with np.load(f, allow_pickle=False) as z:
                arrays = {k: [list(z[k].shape), str(z[k].dtype)] for k in z.files}
            parts = []
            if size > LIMIT:
                for old in d.glob(f.name + '.part*'):
                    old.unlink()
                with open(f, 'rb') as fh:
                    i = 0
                    while True:
                        chunk = fh.read(PART)
                        if not chunk:
                            break
                        p = d / f'{f.name}.part{i:02d}'
                        p.write_bytes(chunk)
                        parts.append(dict(path=str(p.relative_to(CACHE)), bytes=len(chunk),
                                          sha256=hashlib.sha256(chunk).hexdigest()))
                        i += 1
            doc['files'][rel] = dict(bytes=size, sha256=digest, stored_as='parts' if parts else 'whole',
                                     parts=parts, arrays=arrays)
    MANIFEST.write_text(json.dumps(doc, indent=1, sort_keys=True))
    ignored = sorted(k for k, v in doc['files'].items() if v['stored_as'] == 'parts')
    IGNORE.write_text('# originals > 100 MiB are stored as .partNN slices (see CACHE_D6_MANIFEST.json)\n' +
                      ''.join(f'/{k}\n' for k in ignored) + '*.tmp\n')
    return doc


def verify(restore=False):
    doc = json.loads(MANIFEST.read_text())
    bad = []
    for rel, v in doc['files'].items():
        f = CACHE / rel
        for p in v['parts']:
            pp = CACHE / p['path']
            if not pp.exists() or sha256(pp) != p['sha256']:
                bad.append(f'part {p["path"]}')
        if restore and v['parts'] and not f.exists():
            with open(f, 'wb') as out:
                for p in v['parts']:
                    out.write((CACHE / p['path']).read_bytes())
        if f.exists() and sha256(f) != v['sha256']:
            bad.append(f'file {rel}')
        if not f.exists() and not v['parts']:
            bad.append(f'missing {rel}')
    print('verified', len(doc['files']), 'files;', 'problems:', bad or 'none')
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['pack', 'restore', 'verify'])
    ap.add_argument('--arms', nargs='*', default=None)
    a = ap.parse_args()
    if a.mode == 'pack':
        doc = pack(a.arms)
        print('manifest files', len(doc['files']), 'split', sum(v['stored_as'] == 'parts' for v in doc['files'].values()))
    else:
        raise SystemExit(0 if verify(restore=a.mode == 'restore') else 1)


if __name__ == '__main__':
    main()
