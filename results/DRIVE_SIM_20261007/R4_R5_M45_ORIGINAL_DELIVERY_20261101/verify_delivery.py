"""Validate recovered bytes and H structure without running RF or estimation."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
import numpy as np

folder = Path(__file__).resolve().parent
report = json.loads((folder / 'TRANSFER_VERIFICATION.json').read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
archive = folder / report['zip_name']
assert archive.stat().st_size == report['zip_bytes']
assert sha(archive.read_bytes()) == report['zip_sha256'], 'Transfer SHA mismatch'
assert sha((folder / 'SOURCE_LOCK.json').read_bytes()) == report['source_lock_sha256']
checks = []
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == 11
    assert set(z.namelist()) == {i['path'] for i in report['items']} | {'DELIVERY_MANIFEST.json'}
    original_report = json.loads(z.read('DELIVERY_MANIFEST.json'))
    assert original_report['items'] == report['items']
    for entry in report['items']:
        data = z.read(entry['path'])
        assert sha(data) == entry['sha256'] and len(data) == entry['bytes'], entry['path']
    lock = json.loads((folder / 'SOURCE_LOCK.json').read_text())
    for item in lock['items']:
        name = lock['s2_relpath'] + '/' + item['manifest_name']
        raw = z.read(name)
        assert sha(raw) == item['expected_original_manifest_sha256']
        m = json.loads(raw)
        output = m['outputs'][0]
        hpath = lock['s2_relpath'] + '/' + Path(output['path']).name
        hdata = z.read(hpath)
        assert sha(hdata) == output['sha256'] and len(hdata) == output['bytes']
        for inp in m['inputs']:
            b = z.read(inp['path'])
            assert sha(b) == inp['sha256'] and len(b) == inp['bytes']
        h = np.load(io.BytesIO(hdata),allow_pickle=False)
        assert list(h.shape) == report['expected_shapes'][hpath]
        assert h.dtype == np.complex128 and np.isfinite(h).all()
        assert m['config']['mount_deg'] == 45.0
        checks.append(dict(path=hpath,shape=list(h.shape),dtype=str(h.dtype),sha256=sha(hdata),finite=True))
result = dict(status='PASS_TRANSFER_HISTORICAL_HASHES_AND_ARRAY_STRUCTURE',n_H=4,n_original_files=10,
              zip_sha256=report['zip_sha256'],checks=checks,
              limitation='Byte and structural verification only; no new RT run or scientific acceptance.')
(folder / 'LOCAL_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
