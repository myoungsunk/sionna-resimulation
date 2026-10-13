"""I0 public-only RF-off replay. No generator or scoring imports."""
from pathlib import Path
import sys
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
sys.path.insert(0, str(SRC))
from qclean_uwb.drivesim.filter_v2 import run_filter_v2
from qclean_uwb.drivesim.filters import FilterConfig

FIELDS = {'t_s', 'dt_s', 'ds_odom', 'dtheta_gyro', 'dtheta_odom', 'x0'}

def load_public(path):
    with np.load(path, allow_pickle=False) as data:
        if set(data.files) != FIELDS:
            raise ValueError('public schema mismatch; truth and undeclared fields forbidden')
        result = {key: data[key].copy() for key in FIELDS}
    validate(result)
    return result

def validate(data):
    if set(data) != FIELDS:
        raise ValueError('public schema mismatch')
    t = np.asarray(data['t_s'])
    if t.ndim != 1 or len(t) < 2 or not np.isfinite(t).all():
        raise ValueError('invalid timestamp vector')
    for key in FIELDS - {'x0'}:
        x = np.asarray(data[key])
        if x.shape != t.shape or not np.isfinite(x).all():
            raise ValueError('missing/nonfinite or misaligned measurement: ' + key)
    if data['dt_s'][0] != 0 or np.any(np.diff(t) <= 0):
        raise ValueError('timestamps must increase; first interval is zero')
    if not np.allclose(data['dt_s'][1:], np.diff(t), rtol=0, atol=1e-12):
        raise ValueError('timestamp/interval mismatch')
    if np.asarray(data['x0']).shape != (6,) or not np.isfinite(data['x0']).all():
        raise ValueError('invalid public initial pose/calibration mean')

def replay(public_path, config_path):
    data = load_public(public_path)
    cfg = FilterConfig(**json.loads(Path(config_path).read_text()))
    if cfg.use_range or cfg.use_s or cfg.known_wheelbase_error != 0:
        raise ValueError('I0 implements RF-off, non-oracle replay only')
    return run_filter_v2(cfg, None, data, {}, {}, data['x0'])

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('public'); parser.add_argument('config'); parser.add_argument('output')
    args = parser.parse_args()
    result = replay(args.public, args.config)
    target = Path(args.output)
    if target.exists():
        raise FileExistsError(target)
    np.savez_compressed(target, est=result['est'], cov=result['cov_full'])
