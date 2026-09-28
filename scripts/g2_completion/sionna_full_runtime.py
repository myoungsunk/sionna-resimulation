"""Full-campaign native Sionna producer (one batch per invocation).

Unmodified Sionna RT PathSolver/FieldCalculator. The FFD adapter (BankPort,
Ports), the static scene builder (make_scene) and the LOS fixture are
imported unchanged from sionna_native_runtime.py (Windows bytes, SHA
9dc7dfa5...). Differences from the 41-row runner, all outside propagation:

- targets come from <inputs>/TARGETS.jsonl + POSES/PANELS (S0), not CONFIG.rows;
- the condition panel is bound through g2_full_panels (metal 1 mm or the
  dielectric occluder with sigma(f) re-evaluated on every scene.frequency set);
- FFD banks are resolved through the path map and SHA-checked;
- outputs are written per target atomically and resumed via g2_full_runner;
- a hard RF-call budget (--max-rf-calls) is enforced before every PathSolver call.

    python scripts/g2_completion/sionna_full_runtime.py --campaign-root <root> --inputs-dir 00_inputs_R3 \
        --batch-id B000000 [--batches-file 02_batches/BATCHES.jsonl] [--bins all|0,128,256] \
        [--max-rf-calls N] [--threads 4] [--environment repo_checkout|snowball] [--runs-dir batches]
    python scripts/g2_completion/sionna_full_runtime.py --campaign-root <root> --inputs-dir 00_inputs_R3 \
        --los-fixture-only      # LOS FFD fixture only: bins 0/128/256 x 3 arms = exactly 9 calls
"""
import argparse
import hashlib
import importlib.metadata
import inspect
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import sionna_native_runtime as native  # noqa: E402  (sets the llvm_ad_mono_polarized variant)
import drjit as dr  # noqa: E402
import mitsuba as mi  # noqa: E402
import sionna.rt as rt  # noqa: E402

from rt_cp_uwb_py.g2_full_panels import make_panel_material, material_readback  # noqa: E402
from rt_cp_uwb_py.g2_full_paths import file_sha, load_paths, resolve_banks  # noqa: E402
from rt_cp_uwb_py.g2_full_runner import (RUNTIME_CODE, CallBudget, atomic_write_json,  # noqa: E402
                                         expected_run_key, run_batch)

PATH_MAP = ROOT/'config/sionna_full_paths.example.json'
CODE = RUNTIME_CODE
PATH_KEYS = ('vertices', 'interactions', 'objects', 'primitives', 'valid', 'theta_t', 'phi_t', 'theta_r', 'phi_r')


def load_targets(inputs, wanted):
    wanted, found = set(wanted), {}
    with (inputs/'TARGETS.jsonl').open(encoding='utf8') as f:
        for line in f:
            t = json.loads(line)
            if t['target_id'] in wanted:
                found[t['target_id']] = t
    if set(found) != wanted:
        raise ValueError('TARGETS_MISSING:%d' % len(wanted - set(found)))
    return found


class Producer:
    def __init__(self, paths, inputs, config, banks, bins, threads):
        dr.set_thread_count(threads)
        self.geometry = paths['geometry']
        self.inputs = inputs
        self.config = config
        self.poses = json.loads((inputs/'POSES.json').read_text(encoding='utf8'))
        self.panels = json.loads((inputs/'PANELS.json').read_text(encoding='utf8'))
        self.manifest = {s['scene_id']: s for s in
                         json.loads((self.geometry/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))['scenes']}
        self.banks = []
        for port in config['ports']:
            with np.load(banks[port]['path']) as z:
                self.banks.append({k: z[k] for k in z.files})
        self.freq = self.banks[0]['freqs_hz']
        np.testing.assert_array_equal(self.freq, 6250400000. + 1950000.*np.arange(257))
        self.bins = list(range(len(self.freq))) if bins == 'all' else [int(b) for b in bins.split(',')]
        self.txp = [native.BankPort(np.deg2rad(b['theta_deg']), np.deg2rad(b['phi_deg'])) for b in self.banks]
        self.rxp = [native.BankPort(np.deg2rad(b['theta_deg']), np.deg2rad(b['phi_deg']), True) for b in self.banks]
        self.solver = rt.PathSolver()

    def runtime_record(self):
        calc = type(self.solver._field_calculator)
        return dict(versions={n: importlib.metadata.version(n) for n in ('sionna-rt', 'mitsuba', 'drjit')},
                    variant=mi.variant(), code_sha256={c: file_sha(ROOT/c) for c in CODE},
                    pathsolver_file=inspect.getfile(rt.PathSolver),
                    pathsolver_sha256=file_sha(inspect.getfile(rt.PathSolver)),
                    calculator_sha256=file_sha(inspect.getfile(calc)), custom_propagation=False,
                    configuration=self.config['solver'], bins=self.bins, threads=dr.thread_count())

    def scene_for(self, t):
        pose = self.poses[t['pose_id']]
        row = dict(scene_id=t['scene_id'], tx=t['tx'], rx=t['rx'],
                   tx_rotation=pose['tx_rotation'], rx_rotation=pose['rx_rotation'])
        scene, bindings = native.make_scene(self.geometry, row, self.manifest, self.txp, self.rxp)
        panel_material = None
        if t['panel_id']:
            p = self.panels[t['panel_id']]
            panel_material = make_panel_material(rt, p['spec'])
            scene.edit(add=[rt.SceneObject(fname=str(self.inputs/p['ply']), name='dynamic_panel',
                                           radio_material=panel_material)])
            bindings.append(dict(object='dynamic_panel', panel_id=t['panel_id'], kind=p['spec']['kind'],
                                 thickness_m=p['spec']['thickness_m'], ply_sha256=file_sha(self.inputs/p['ply'])))
            panel_material = scene.objects['dynamic_panel'].radio_material
        return scene, bindings, panel_material

    def compute(self, t, budget):
        start = time.monotonic()
        scene, bindings, panel_material = self.scene_for(t)
        saved, channels, counts, readback = {}, [], [], []
        for fi in self.bins:
            f = float(self.freq[fi])
            scene.frequency = f  # triggers the occluder sigma(f) callback
            if panel_material is not None:
                readback.append(dict(material_readback(panel_material), bin=fi, frequency_hz=f))
            for i, b in enumerate(self.banks):
                self.txp[i].update(b['e_theta'][fi], b['e_phi'][fi])
                self.rxp[i].update(b['e_theta'][fi], b['e_phi'][fi])
            arm_channels, arm_counts = [], []
            for ai, arm in enumerate(native.ARMS):
                ix = slice(2*ai, 2*ai+2)
                scene.tx_array = rt.AntennaArray(native.Ports(self.txp[ix]), mi.Point3f(0, 0, 0))
                scene.rx_array = rt.AntennaArray(native.Ports(self.rxp[ix]), mi.Point3f(0, 0, 0))
                budget.take()
                paths = self.solver(scene, **self.config['solver'])
                a = np.asarray(paths.a[0]) + 1j*np.asarray(paths.a[1]); tau = np.asarray(paths.tau)
                n = a.shape[-1]; coef = a.reshape(2, 2, n); delay = tau.reshape(-1)
                if len(delay) != n:
                    raise ValueError('PATH_SHAPE_MISMATCH')
                h = coef.astype(np.complex128)*np.exp(-2j*np.pi*f*delay.astype(np.float64))[None, None, :]
                if not np.isfinite(h).all():
                    raise FloatingPointError('NON_FINITE_H')
                arm_channels.append(h.sum(axis=-1)); arm_counts.append(n)
                saved[f'{arm}_a_{fi:03d}'] = coef; saved[f'{arm}_tau_{fi:03d}'] = delay
                for key in PATH_KEYS:
                    saved[f'{arm}_{key}_{fi:03d}'] = np.asarray(getattr(paths, key))
            channels.append(arm_channels); counts.append(arm_counts)
        saved.update(H_arms=np.array(channels), arms=np.array(native.ARMS), frequencies_hz=self.freq[self.bins],
                     bins=np.array(self.bins), tx_m=np.array(t['tx']), rx_m=np.array(t['rx']),
                     ports=np.array(self.config['ports']), target_id=np.array(t['target_id']))
        meta = dict(target_id=t['target_id'], family=t['family'], scene_id=t['scene_id'], tx=t['tx'], rx=t['rx'],
                    pose_id=t['pose_id'], panel_id=t['panel_id'], frame_ref=t['frame_ref'], bins=self.bins,
                    path_counts=counts, bindings=bindings, panel_material_readback=readback,
                    object_indices={str(o.object_id): name for name, o in scene.objects.items()},
                    elapsed_s=time.monotonic()-start,
                    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)  # Linux: KiB, process peak
        return saved, meta


FIXTURE_BINS = '0,128,256'
FIXTURE_CALLS = 9   # 3 bins x 3 arms (S2 approval): never scaled by --bins


def run_los_fixture(root, config, paths, inputs, banks, threads):
    """Standalone FFD/native LOS adapter fixture: exactly 9 PathSolver calls, reused if already passed."""
    producer = Producer(paths, inputs, config, banks, FIXTURE_BINS, threads)
    code = {c: file_sha(ROOT/c) for c in CODE}
    tag = hashlib.sha256(json.dumps(code, sort_keys=True).encode()).hexdigest()[:16]
    out = root/'02_fixtures'/f'LOS_FIXTURE.{tag}.json'
    if out.is_file():
        prior = json.loads(out.read_text(encoding='utf8'))
        if prior.get('code_sha256') == code and prior.get('passed'):
            return dict(prior, reused=True, rf_calls_this_run=0)
        raise SystemExit(f'LOS_FIXTURE_EXISTS_NOT_PASSED: {out} is preserved; inspect before any retry')
    budget = CallBudget(FIXTURE_CALLS)
    budget.take(FIXTURE_CALLS)   # fixture makes one PathSolver call per (bin, arm)
    results = native.los_fixture(producer.banks, producer.txp, producer.rxp, producer.bins)
    if len(results) != FIXTURE_CALLS:
        raise SystemExit('LOS_FIXTURE_CALL_COUNT')
    record = dict(fixture='sionna_native_runtime.los_fixture (unchanged)', bins=producer.bins, rf_calls=FIXTURE_CALLS,
                  passed=all(r['passed'] for r in results), results=results, code_sha256=code,
                  runtime=producer.runtime_record())
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out, record)
    return dict(record, reused=False, rf_calls_this_run=FIXTURE_CALLS, file=str(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--environment', default='repo_checkout')
    ap.add_argument('--inputs-dir', required=True)
    ap.add_argument('--batch-id')
    ap.add_argument('--batches-file', default='02_batches/BATCHES.jsonl')
    ap.add_argument('--runs-dir', default='batches')
    ap.add_argument('--bins', default='all')
    ap.add_argument('--max-rf-calls', type=int, default=None)
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--los-fixture-only', action='store_true',
                    help='run only the LOS FFD fixture at bins 0/128/256 (exactly 9 calls); no batch')
    a = ap.parse_args()
    config_map, paths = load_paths(PATH_MAP, a.environment, ROOT)
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    inputs = root/a.inputs_dir
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    banks = resolve_banks(config_map, paths)
    if {p: b['sha256'] for p, b in banks.items()} != {p: config['bank_sha256'][f'{p}_bank.npz'] for p in banks}:
        raise SystemExit('BANK_SHA_NOT_CONFIG')
    if file_sha(inputs/'TARGETS.jsonl') != config['targets_sha256']:
        raise SystemExit('TARGETS_SHA_NOT_CONFIG')
    if a.los_fixture_only:
        r = run_los_fixture(root, config, paths, inputs, banks, a.threads)
        print(json.dumps({k: r[k] for k in ('passed', 'reused', 'rf_calls_this_run', 'bins')}))
        sys.exit(0 if r['passed'] else 5)
    if not a.batch_id:
        raise SystemExit('BATCH_ID_REQUIRED')
    batch = next((json.loads(l) for l in (root/a.batches_file).read_text(encoding='utf8').splitlines()
                  if json.loads(l)['batch_id'] == a.batch_id), None)
    if batch is None:
        raise SystemExit('UNKNOWN_BATCH')
    producer = Producer(paths, inputs, config, banks, a.bins, a.threads)
    key = expected_run_key(ROOT, inputs, producer.bins)
    budget = CallBudget(a.max_rf_calls)
    batch_dir = root/a.runs_dir/a.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    targets = load_targets(inputs, batch['target_ids'])
    status = run_batch(batch, targets, batch_dir, key, producer.compute, budget, 3*len(producer.bins))
    status.update(budget_used=budget.used, budget_limit=budget.limit)
    if not status.get('reuse_only'):
        atomic_write_json(batch_dir/status['attempt']/'RUNTIME.json', producer.runtime_record())
    atomic_write_json(batch_dir/status['status_file'], status)
    print(json.dumps(status, indent=1))
    sys.exit(0 if status['complete'] else 2)


if __name__ == '__main__':
    main()
