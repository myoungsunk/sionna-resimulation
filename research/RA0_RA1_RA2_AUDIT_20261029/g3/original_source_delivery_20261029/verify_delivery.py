"""Verify transferred bytes and NPZ structure; does not adjudicate G3 physics."""
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
import zipfile
import numpy as np

folder = Path(__file__).resolve().parent
archive = folder / 'G3_ORIGINAL_23_TRACE_PAIRS.zip'
lock = json.loads((folder.parent / 'G3_23_ORIGINAL_SOURCE_LOCK.json').read_text())
digest = lambda data: hashlib.sha256(data).hexdigest()
expected_zip_sha = '4f625c84172fecd7539273eb8d19c841fd2eb204b61d9062a3b901cca6dc4a62'
assert digest(archive.read_bytes()) == expected_zip_sha, 'ZIP transfer SHA mismatch'
rows = []
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None, 'ZIP CRC failure'
    manifest = json.loads(z.read('G3_REQUESTED_SOURCE_MANIFEST.json'))
    expected = {r['path'] for r in manifest['items']}
    assert len(expected) == 46
    assert len(z.namelist()) == 47
    assert set(z.namelist()) == expected | {'G3_REQUESTED_SOURCE_MANIFEST.json'}
    for entry in manifest['items']:
        data = z.read(entry['path'])
        assert digest(data) == entry['sha256'] and len(data) == entry['size'], entry['path']
    for item in lock['items']:
        name = item['original_relpath']
        receipt_name = name.replace('_trace.npz', '_trace_receipt.json')
        raw_receipt = z.read(receipt_name)
        assert digest(raw_receipt) == item['expected_original_receipt_sha256'], receipt_name
        receipt = json.loads(raw_receipt)
        with np.load(io.BytesIO(z.read(name)), allow_pickle=False) as a:
            required = {'tau','jones','ang','node_bins','node_freq_hz','present','x','y','status'}
            assert required <= set(a.files), name
            n = receipt['n_paths']
            nodes = receipt['n_nodes']
            assert a['tau'].shape == (n,)
            assert a['jones'].shape == (nodes,n,3,3)
            assert a['ang'].shape == (4,n)
            assert a['present'].shape == (nodes,n)
            assert a['node_bins'].shape == a['node_freq_hz'].shape == (nodes,)
            assert np.isfinite(a['tau']).all() and np.isfinite(a['jones']).all()
            assert str(a['status'].item()) == receipt['status'] == 'OK'
            assert float(a['x']) == receipt['x'] and float(a['y']) == receipt['y']
            assert int(a['unmatched']) == receipt['unmatched_paths'] == item['expected_n_strict_paths']
            rows.append(dict(path=name,n_paths=n,n_nodes=nodes,unmatched=receipt['unmatched_paths']))
    assert len(rows) == 23 and sum(r['unmatched'] for r in rows) == 25
    groups = dict(Counter(item['case'] for item in lock['items']))
    assert groups == {'R2_aB':1,'R4_aA':3,'R4_aB':3,'R5_aA':9,'R5_aB':7}
report = dict(status='PASS_TRANSFER_RECEIPTS_AND_NPZ_STRUCTURE',zip_sha256=expected_zip_sha,
              n_raw=23,n_receipts=23,receipt_sha_matches=23,groups=groups,
              historical_unmatched_ray_count=25,arrays=rows,
              limitation='Original NPZ hashes were not previously archived. H reconstruction parity and physical G3 adjudication remain pending.')
(folder / 'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(folder / 'G3_REQUESTED_SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='arrays'},indent=2))
