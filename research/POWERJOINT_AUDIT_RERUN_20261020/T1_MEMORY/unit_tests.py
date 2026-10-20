"""Locked T1 tests of the recovered engine, not a replacement memory engine."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys
import traceback
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load_engine(root=ROOT):
    for rel in ('research/EKF4_RANGE_S_STAGED_20261014',
                'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'):
        sys.path.insert(0, str(root / rel))
    # Byte-for-byte recovered dependency at the engine's exact source revision.
    # This dedicated path avoids accidentally importing a later shared core.
    sys.path.insert(0, str(HERE/'vendor'))
    path = root / 'research/CHAIN_HYPOTHESIS_20261019/engine.py'
    spec = importlib.util.spec_from_file_location('t1_exact_engine', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


class TestObservation:
    """Smooth synthetic observation for numeric parity; no RF performance claim."""
    def batch(self, x, case, gradient=True):
        h = np.column_stack((x[:, 0] + .1*x[:, 1]**2,
                             np.sin(x[:, 2]) + .05*x[:, 1]))
        H = np.zeros((len(x), 2, 4))
        H[:, 0, 0] = 1
        H[:, 0, 1] = .2*x[:, 1]
        H[:, 1, 1] = .05
        H[:, 1, 2] = np.cos(x[:, 2])
        return h, H


def rho0_test(engine):
    rng = np.random.default_rng(20261020)
    n = 240
    dt = rng.choice([.1, .2, .25, .4], n)
    t = np.cumsum(dt)
    controls = dict(dt_s=dt, ds_odom=.015*np.ones(n),
                    dtheta_gyro=.002*np.sin(np.arange(n)/11))
    C = np.empty((n, 2, 2))
    for i in range(n):
        L = np.array([[.1+.01*np.sin(i), 0], [.02*np.cos(i), .08]])
        C[i] = L@L.T
    mu = .01*rng.normal(size=(n, 2))
    z = np.c_[np.linspace(0, 4, n), np.sin(np.arange(n)/100)]
    z += mu + .06*rng.normal(size=(n, 2))
    z[::17] += 2  # Exercise accepted and rejected gates.
    specs = [dict(name='POWER1', base='power'),
             dict(name='MEMORY_RHO0', base='power', latent=True, tau=0., fraction=.8)]
    r = engine.run(t, controls, np.zeros(3), z, mu, C, np.zeros(n),
                   {'id': 'UNIT_SYNTHETIC'}, TestObservation(), specs)
    dx = float(np.max(abs(r['state'][:, 0, :4]-r['state'][:, 1, :4])))
    dp = float(np.max(abs(r['cov'][:, 0, :4, :4]-r['cov'][:, 1, :4, :4])))
    flips = int(np.count_nonzero(r['accepted'][:, 0] != r['accepted'][:, 1]))
    both_gates = bool(r['accepted'][:, 0].any() and (~r['accepted'][:, 0]).any())
    return dict(test='rho0_actual_run', state_max=dx, cov_max=dp, gate_mismatch=flips,
                both_gate_outcomes=both_gates, pass_=max(dx, dp) <= 1e-10 and flips == 0 and both_gates)


def variance_test(engine):
    rng = np.random.default_rng(20261020)
    worst = 0.
    for i in range(500):
        A = rng.normal(size=(2, 2))
        C = A@A.T + np.eye(2)*.001
        fraction = [.05, .9, .8539096073922738][i % 3]
        spec = dict(base='power', latent=True, tau=.7, fraction=fraction)
        _, white, B, _ = engine.parameters_at(i, spec, np.zeros(2), C, C, 0.)
        worst = max(worst, float(np.linalg.norm(white+B@B.T-C)/np.linalg.norm(C)))
    return dict(test='stationary_variance', relative_max=worst, pass_=worst <= 1e-9)


def linear_test(engine):
    rng = np.random.default_rng(161019)
    N, T, rho, fraction = 500, 100, .98, .8
    truth = rng.normal(size=N)
    b = rng.normal(size=N)
    obs = []
    for k in range(T):
        if k:
            b = rho*b + np.sqrt(1-rho*rho)*rng.normal(size=N)
        obs.append(truth + np.sqrt(fraction)*b + np.sqrt(1-fraction)*rng.normal(size=N))
    rows = []
    for name, a in [('independent', 0.), ('memory_correct', rho)]:
        # Embed the original two-state test in actual engine.single_update's
        # six-state layout. x coordinate is the scalar target, latent index4.
        H = np.zeros((1, 6)); H[0, 0] = 1.; H[0, 4] = np.sqrt(fraction)
        F = np.eye(6); F[4, 4] = a
        Q = np.zeros((6, 6)); Q[4, 4] = 1-a*a
        means = np.zeros((N, 6)); P = np.eye(6)
        for z in obs:
            means = means@F.T
            prior = F@P@F.T + Q
            for j in range(N):
                y, post, *_ = engine.single_update(means[j], prior, np.array([z[j]]),
                                                   H@means[j], H, np.array([[1-fraction]]))
                means[j] = y
            P = post
        error = means[:, 0]-truth
        nees = error**2/P[0, 0]
        rows.append(dict(test='linear_'+name, rmse=float(np.sqrt(np.mean(error**2))),
                         sigma=float(np.sqrt(P[0, 0])), nees=float(nees.mean()),
                         coverage95=float(np.mean(nees < 3.8414588)), n=N))
    expected = {'independent': (42.642544837154055, .248),
                'memory_correct': (1.0886208363935503, .934)}
    for row in rows:
        target = expected[row['test'].removeprefix('linear_')]
        row['pass_'] = abs(row['nees']-target[0]) <= 1e-9 and abs(row['coverage95']-target[1]) <= 1e-12
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        engine, path = load_engine(args.source_root)
        rows = [rho0_test(engine), variance_test(engine)] + linear_test(engine)
        pd.DataFrame(rows).to_csv(args.out/'UNIT_TESTS.csv', index=False)
        (args.out/'UNIT_MANIFEST.json').write_text(json.dumps(dict(
            engine_path=str(path), engine_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            protocol_sha256=hashlib.sha256((HERE/'PROTOCOL_LOCK.json').read_bytes()).hexdigest(),
            core_sha256=hashlib.sha256((HERE/'vendor/core.py').read_bytes()).hexdigest(),
            numpy_version=np.__version__, pandas_version=pd.__version__, python_version=sys.version,
            technical='TECHNICAL_PASS' if all(r['pass_'] for r in rows) else 'FAIL',
            scientific='NOT_ESTABLISHED', source_only_missing_impls=[2, 3]), indent=2))
        if not all(r['pass_'] for r in rows):
            raise RuntimeError('T1_UNIT_TEST_FAILED; preserve outputs; do not continue to replay')
    except Exception as error:
        (args.out/'ERRORS.json').write_text(json.dumps([dict(error=str(error),
            traceback=traceback.format_exc(), retry='not automatic')], indent=2))
        raise


if __name__ == '__main__':
    main()
