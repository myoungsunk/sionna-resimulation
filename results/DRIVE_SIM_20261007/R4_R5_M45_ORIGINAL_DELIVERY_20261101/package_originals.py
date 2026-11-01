"""Package existing R4/R5 m45 bytes only. Python 3.6+; no simulation."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    folder = Path(__file__).resolve().parent
    lock_bytes = (folder / 'SOURCE_LOCK.json').read_bytes()
    lock = json.loads(lock_bytes)
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(lock['source_root'])
    s2 = Path(lock['s2_relpath'])
    files = {}
    shapes = {}
    for item in lock['items']:
        rel = s2 / item['manifest_name']
        raw = (root / rel).read_bytes()
        if sha(raw) != item['expected_original_manifest_sha256']:
            raise ValueError('Historical manifest SHA mismatch: ' + str(rel))
        manifest = json.loads(raw)
        if manifest['config']['mount_deg'] != 45.0:
            raise ValueError('Unexpected mount')
        files[rel.as_posix()] = raw
        output = manifest['outputs'][0]
        hrel = s2 / Path(output['path']).name
        hraw = (root / hrel).read_bytes()
        if sha(hraw) != output['sha256'] or len(hraw) != output['bytes']:
            raise ValueError('Historical H SHA/size mismatch: ' + str(hrel))
        files[hrel.as_posix()] = hraw
        shapes[hrel.as_posix()] = [manifest['config']['report']['n_pose'],257,2,2]
        for inp in manifest['inputs']:
            data = (root / inp['path']).read_bytes()
            if sha(data) != inp['sha256'] or len(data) != inp['bytes']:
                raise ValueError('Historical pose SHA/size mismatch')
            files[inp['path']] = data
    if len(files) != 10:
        raise ValueError('Expected 4 H + 4 manifest + 2 pose files')
    report = dict(status='PASS_HISTORICAL_BYTE_HASHES',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  source_root=str(root),source_lock_sha256=sha(lock_bytes),
                  n_original_files=len(files),n_H=4,n_manifests=4,n_pose_lists=2,
                  items=[dict(path=p,sha256=sha(b),bytes=len(b)) for p,b in sorted(files.items())],
                  expected_shapes=shapes,scope='Byte-preserving delivery only; no RT regeneration or scientific revalidation.')
    out = folder / 'R4_R5_M45_ORIGINAL_20261007.zip'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as z:
        for p,b in sorted(files.items()):
            z.writestr(p,b)
        z.writestr('DELIVERY_MANIFEST.json',json.dumps(report,indent=2)+'\n')
    zip_bytes = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        if z.testzip() is not None or len(z.namelist()) != 11:
            raise ValueError('ZIP integrity or membership failure')
        for entry in report['items']:
            if sha(z.read(entry['path'])) != entry['sha256']:
                raise ValueError('Archived byte mismatch')
    with out.open('xb') as f:
        f.write(zip_bytes)
    report.update(zip_name=out.name,zip_sha256=sha(zip_bytes),zip_bytes=len(zip_bytes))
    with (folder / 'TRANSFER_VERIFICATION.json').open('x') as f:
        f.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('items','expected_shapes')},indent=2))


if __name__ == '__main__':
    main()
