"""Post hoc B0 mechanism replay. The archived R4 path and O30 stay fixed."""
import argparse
from pathlib import Path
import json
import sys
import numpy as np

from run_tb3_g1_pilot import read, sha
import run_tb3_model003_s3 as frozen
from tb3_model003_filter import range_model
from tb3_model003_s1_observation import channel_to_cir, range_candidates

FOLDS = Path('/folds/30')
FROZEN = Path('/frozen')


def simulate(original, args, z):
    case, path, arm, level, data, inp, _, dr, model, obs, banks, rule, offset, settings, k_variance = args
    n = len(inp['rows'])
    assert arm == 'R4' and level == 'B0' and rule == 'O30'
    record = np.empty((n, z.shape[1], 12))
    call = 0
    correction = np.zeros(z.shape[1]); bias_integration = correction.copy()
    last_b = correction.copy()
    original_rf = frozen.update_rf

    def inspect(mean, cov, value, xy, dz, offset, noise, **options):
        nonlocal call
        n_run = value.shape[0]
        assert n_run == 2*z.shape[1]
        h, jac = range_model(mean, xy, dz, offset)
        ph = np.einsum('rij,rj->ri', cov, jac)
        innovation_cov = np.einsum('ri,ri->r', jac, ph) + noise[:,0,0]
        new_mean, new_cov, event = original_rf(mean, cov, value, xy, dz, offset, noise, **options)
        bias_integration[:] -= last_b * inp['dt'][call]
        direct = frozen.wrap_rad(new_mean[:,2] - mean[:,2])[::2]
        correction[:] += direct
        last_b[:] = new_mean[::2,3]
        record[call] = np.stack([a[::2] for a in (value[:,0]-h, event['accepted'], event['nis'], ph[:,2]/innovation_cov,
                                                ph[:,3]/innovation_cov, new_mean[:,3], np.sqrt(new_cov[:,2,2]),
                                                np.sqrt(new_cov[:,3,3]), frozen.wrap_rad(new_mean[:,2]-inp['truth'][call,2]))]
                                + [correction, bias_integration, direct], axis=1)
        call += 1
        return new_mean, new_cov, event

    frozen.update_rf = inspect
    try:
        score, details = original(*args[:6], z, *args[7:])
    finally:
        frozen.update_rf = original_rf
    assert call == n
    return score, details, record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('case', choices=frozen.CASES)
    parser.add_argument('path', choices=frozen.PATHS)
    flags = parser.parse_args()
    key = f'{flags.case}_{flags.path}_B0'
    source = FOLDS/f'{key}_R4.json'
    gate = read(Path('/published/LOAO_RESULTS.json'))
    expected = gate['receipt_sha256'][f'30/{source.name}']
    assert sha(source) == expected
    base = FOLDS/f'{key}_DR.json'
    assert sha(base) == gate['receipt_sha256'][f'30/{base.name}']
    official = read(source)
    options = dict(case=flags.case,path=flags.path,arm='R4',level='B0',snr=30,dr=base,results_root=Path('/results'),
                   model_source=Path('/model'),banks_dir=Path('/banks'),out=Path('/analysis')/f'{key}_replay.json')
    for opt,file in [('timeline','TIMELINE_PACKETS.csv'),('s2','CHARACTERIZATION_003.json'),
                     ('selection','RANGING_RULE_SELECTION.json'),('parity','PARITY.json')]:
        options[opt] = FROZEN/file
        options[opt+'_sha256'] = gate['source'][{'selection':'s1','s2':'s2','timeline':'timeline','parity':'parity'}[opt]+'_sha256']
    original = frozen.fit_path

    def run(*args):
        case, path, arm, level, data, inp, z, dr, model, obs, banks, rule, offset, settings, k_variance = args
        score, details, observed = simulate(original, args, z)
        assert score == official['receipt_rows'], (case,path,'checkpoint replay differs')
        ids = np.array([int(row['rf_pose_id']) for row in inp['rows']])
        streams = [row['phase'] for row in inp['rows']]
        modes = [row['motion'] for row in inp['rows']]
        sequences = [int(row['sequence']) for row in inp['rows']]
        dz = data['rx_z']-data['anchor'][2]
        true_range = np.sqrt(np.sum((inp['truth'][:,:2]-data['anchor'][:2])**2,axis=1)+dz**2)
        true_expectation = true_range+offset
        # Swap only archived multipath in this diagnostic. Same O30, seed, SNR, offset, filter and gate.
        df = float(banks[0].freqs_hz[1] - banks[0].freqs_hz[0])
        z_los = frozen.paired_observations({'full':data['los']}, inp['rows'], obs, df, (rule,), snr_db=30)[rule]
        _, _, los = simulate(original, args, z_los)
        # Ideal zero-residual control is injected after O30 entirely outside the frozen estimator.
        z_truth = z.copy()
        z_truth[...,0] = np.where(np.isfinite(z[...,0]), true_expectation[:,None], np.nan)
        _, _, ideal = simulate(original, args, z_truth)
        clean = []
        for h in (data['full'], data['los']):
            taps = []
            for lo in range(0, len(ids), 64):
                cir = channel_to_cir(h[ids[lo:lo+64]], obs)
                taps.extend(range_candidates(cir,df,rules=(rule,))[rule]['range_m'])
            clean.append(np.array(taps))
        cp = inp['cp']
        paired = np.stack([dr[int(i)][::2] for i in cp])
        error = frozen.wrap_rad(observed[cp,:,8] - paired - observed[cp,:,9] - observed[cp,:,10])
        assert np.max(np.abs(error)) < 4e-11, 'heading error decomposition differs'
        out = Path('/analysis')/f'{key}.npz'
        np.savez_compressed(out, cp=cp, streams=streams, modes=modes, ids=ids, sequences=sequences,
                            elapsed=inp['geometry']['elapsed_s'], true_range=true_range, pose_range=data['d'][ids],
                            clean_full=clean[0],clean_los=clean[1], observations=z[...,0],obs_los=z_los[...,0],
                            observed=observed, los=los, ideal=ideal, dr=paired, offset=offset,
                            range_sigma=np.sqrt(settings['thermal'][0]+settings['constant'][0]),
                            replay_max_difference=0., decomposition_max_rad=np.max(np.abs(error)))
        return score, details

    frozen.fit_path = run
    frozen.run_fold(argparse.Namespace(**options))
    print(f'{key} exact checkpoint reproduction: {len(official["receipt_rows"])} rows')


if __name__ == '__main__':
    main()
