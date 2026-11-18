"""Compare unchanged Office producer with original 2026-10-08 H samples."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

root = Path('/work')
checks = []
for station, tag in [('S01', 'office_x0.5_y0.75'), ('S10', 'office_x0.5_y5.25')]:
    folder = root / 'pilot' / station
    actual = np.load(folder / ('pilot_' + station + '_H.npy'), allow_pickle=False)
    original = np.load(Path('/reference') / tag / (tag + '_H.npy'), allow_pickle=False)
    expected = original[[0, 9, 18]][:, [0, 128, 256]]
    receipt = json.loads((folder / ('pilot_' + station + '_receipt.json')).read_text())
    old_receipt = json.loads((Path('/reference') / tag / (tag + '_receipt.json')).read_text())
    fields = ['setup_config_sha256', 'anchor_m', 'materials', 'solver', 'versions',
              'runner_sha256', 'adapter_sha256', 'bank_sha256']
    config_equal = all(receipt[field] == old_receipt[field] for field in fields)
    checks.append(dict(station=station, complex_coefficients=int(actual.size),
                       array_exact_equal=bool(np.array_equal(actual, expected)),
                       byte_sha_equal=hashlib.sha256(actual.tobytes()).hexdigest() == hashlib.sha256(expected.tobytes()).hexdigest(),
                       max_abs_difference=float(np.max(np.abs(actual - expected))),
                       config_equal=config_equal, solver_calls=int(receipt['pathsolver_calls']),
                       elapsed_s=receipt['elapsed_s'], seconds_per_call=receipt['seconds_per_call']))
passed = all(row['array_exact_equal'] and row['byte_sha_equal'] and row['config_equal'] for row in checks)
result = dict(status='PASS' if passed else 'FAIL', checked_utc=datetime.now(timezone.utc).isoformat(),
              comparison='2 positions x 3 yaws (0,90,180) x 3 bins (0,128,256)',
              original_root='/home/KMS/OFFICE_SNOWBALL_20261008_819fa93/full35_stride1', checks=checks)
(root / 'PILOT_VALIDATION.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
raise SystemExit(0 if passed else 2)
