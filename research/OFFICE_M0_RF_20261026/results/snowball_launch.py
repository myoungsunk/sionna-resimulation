import json
from pathlib import Path
import subprocess
import sys

root = Path('/home/KMS/OFFICE_M0_RF_20261026_01a17631')
assert not (root / 'LAUNCH_LOCK.json').exists(), 'Already launched'
with (root / 'CONTROLLER.log').open('xb') as log:
    process = subprocess.Popen([sys.executable, str(root / 'snowball_controller.py')],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
print(json.dumps({'controller_pid': process.pid, 'root': str(root)}))
