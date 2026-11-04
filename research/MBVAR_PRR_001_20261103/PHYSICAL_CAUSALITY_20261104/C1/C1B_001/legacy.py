"""Initialize the original source-only FFD observer and original motion code."""
import importlib.util
import sys
from pathlib import Path
import numpy as np


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def load(cache, banks):
    root = Path(cache)/'legacy'
    sys.path[:0] = [str(root/'research/FFD_P0P3_20261016'),
                   str(root/'research/EKF4_RANGE_S_STAGED_20261014'),
                   str(root/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
    from source_model import SourceFFD
    from qclean_uwb.drivesim import pattern_apply
    arrays = []
    for name in ('LP_plus45_bank.npz', 'LP_minus45_bank.npz'):
        with np.load(banks[name]['path'], allow_pickle=False) as data:
            arrays.append(pattern_apply.Bank(dict(data)))
    model = SourceFFD(banks=arrays)
    core = module('legacy_motion_core', root/'research/EKF4_RANGE_S_STAGED_20261014/core.py')
    online = module('legacy_online', Path(cache)/'provenance/online.py')
    return core, online, model
