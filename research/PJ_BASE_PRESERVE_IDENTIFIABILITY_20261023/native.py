"""Read-only bridge to the pinned repository and staged original RF assets.

This module imports the historical pipeline only when NativeAssets is explicitly constructed.
No downloads, ray tracing, workflow dispatch, or import-time experiments.
"""
from __future__ import annotations
from pathlib import Path
import importlib
import json
import math
import importlib.metadata
import os
import subprocess
import sys
import numpy as np
import pandas as pd
import joblib
from .common import (REFERENCE_SHA, BASE_FEATURES, OFFSETS, Packet, Inputs, require, BlockedError,
                     file_hash, read_json, exact_rows, digest)
from .runtime_features import Corrector
from .numerics import psd, wrap


def spectrum_profile(spectrum, fixed_fp=None):
    """Original Hann / 4x IFFT / strongest-port 30%-edge observer, with explicit masks."""
    H = np.asarray(spectrum, np.complex128)
    require(H.ndim == 2 and H.shape[1] == 2 and np.isfinite(H).all(), 'Expected frequency x 2-port spectrum')
    nf = len(H); require(nf > 1, 'Insufficient frequency samples')
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[:, None], n=4*nf, axis=0) * nf
    amp = np.abs(cir); power = amp**2
    branch = int(amp.max(0).argmax()); strong = amp[:, branch]
    detected = int((strong >= .3 * strong.max()).argmax()) if strong.max() > 0 else -1
    fp = detected if fixed_fp is None else int(fixed_fp)
    indices = fp + np.array(OFFSETS); valid = (indices >= 0) & (indices < len(cir)) & (fp >= 0)
    sampled = power[np.clip(indices, 0, len(cir)-1)]
    den = sampled.sum(1); valid &= np.isfinite(den) & (den > 0)
    q = np.full(len(indices), np.nan); q[valid] = (sampled[valid,0] - sampled[valid,1]) / den[valid]
    return q, valid, fp, np.where(valid, den, 0.)


class NativeModel:
    mutable_runtime = False

    def __init__(self, source, V, core, case):
        self.source, self.V, self.core, self.case = source, V, core, dict(case)

    def observe(self, x):
        h, H = self.source.batch(np.asarray(x)[None], self.case, gradient=True)
        return h[0], H[0]

    def profile(self, x, fixed_fp=None):
        spectrum = self.source.spectrum(np.asarray(x)[None], self.case, gradient=False)[0][0]
        q, mask, fp, _ = spectrum_profile(spectrum, fixed_fp)
        return q, mask, fp

    def reference_increments(self,t,truth):
        RB=importlib.import_module('r2_bias_replay')
        return tuple(np.asarray(v) for v in RB.motion_increments(t,truth[:,:3],convention='legacy-euler'))

    def transition(self, x, u):
        return self.core.transition(np.asarray(x), float(u[0]), float(u[1]), float(u[2]))

    def predict(self, x, P, u):
        _, F, G = self.transition(x, u)
        y, C = self.V.predict_one(np.array(x, copy=True), np.array(P, copy=True), *map(float, u))
        Q = np.diag([2e-5*abs(float(u[0])), math.radians(.015)**2*float(u[2]), 0.])
        # Reject a changed historical process implementation rather than silently using the wrong Q.
        require(np.allclose(C, F @ P @ F.T + G @ Q @ G.T, rtol=1e-7, atol=1e-12), 'Native F/G/Q not equal to predictor')
        return y, C, F, G, Q


class NativeAssets:
    def __init__(self, config: dict):
        self.cfg = config
        required = ('reference_root', 'source_root', 'artifact_root', 'l4models_root', 'grid_root', 'asset_lock')
        absent = [x for x in required if not config.get(x)]
        if absent:
            raise BlockedError('Configure original assets: ' + ', '.join(absent))
        expected={'numpy':'2.3.3','scipy':'1.16.2','pandas':'2.3.2','scikit-learn':'1.7.2','joblib':'1.6.0'}
        mismatches={k:(importlib.metadata.version(k),v) for k,v in expected.items() if importlib.metadata.version(k)!=v}
        if sys.version_info[:2]!=(3,11) or mismatches:
            raise BlockedError(f'RF replay requires original Python 3.11 and pinned dependencies; found {sys.version_info[:2]}, {mismatches}')
        self.ref = Path(config['reference_root']).resolve()
        lock = read_json(Path(config['asset_lock']))
        require(lock.get('reference_sha') == REFERENCE_SHA, 'Asset lock reference mismatch')
        require(lock.get('files'), 'Empty asset lock is not evidence')
        self.lock = {str(Path(p).resolve()): h for p, h in lock['files'].items()}
        for label in ('source_root','artifact_root','l4models_root','grid_root'):
            directory=Path(config[label]).resolve()
            if not directory.is_dir():raise BlockedError(f'Missing {label}: {directory}')
            not_locked=[str(p) for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and str(p.resolve()) not in self.lock]
            require(not not_locked,f'Untracked input/code assets in {label}: {not_locked[:5]}')
        for p, h in self.lock.items():
            if not Path(p).is_file():
                raise BlockedError(f'Missing locked asset: {p}')
            require(file_hash(Path(p)) == h, f'Asset checksum mismatch: {p}')
        try:
            sha = subprocess.check_output(['git', '-C', str(self.ref), 'rev-parse', 'HEAD'], text=True).strip()
            clean = subprocess.run(['git', '-C', str(self.ref), 'diff', '--quiet', 'HEAD'], check=False).returncode
        except (OSError, subprocess.CalledProcessError) as e:
            raise BlockedError(f'Pinned reference checkout unavailable: {e}') from e
        require(sha == REFERENCE_SHA and clean == 0, 'Use a clean detached 0686b23 reference worktree')
        os.environ['PJ_SOURCE_ROOT'] = str(Path(config['source_root']).resolve())
        os.environ['PJ_ART'] = str(Path(config['artifact_root']).resolve())
        os.environ['PJ_OUT'] = str(Path(config['work_dir']).resolve() / 'native_scratch')
        for name in ('p2_replay', 'strict_common', 'v_replay', 'p1r_eval', 'p2_mc'):
            require(name not in sys.modules, f'{name} already imported: run one protocol process per reference checkout')
        sys.path.insert(0, str(self.ref / 'research/PJ_D0_CIR_P2_RECURSIVE_20261022'))
        self.R2 = importlib.import_module('p2_replay'); self.V = self.R2.V; self.S = self.R2.S
        self.P = importlib.import_module('p1r_eval'); self.MC = importlib.import_module('p2_mc')
        self.core = importlib.import_module('core'); self.RB = importlib.import_module('r2_bias_replay')
        # Raw asset hashes are anchored in the historical input manifest as well as the integrity lock.
        known={v['path']:v for v in self.V.MANIFEST.get('assets',[])}
        for case in self.V.MANIFEST['cases']:
            for field in ('full_path','los_path','samples_path'):
                rel=case[field];path=self.checked(self.V.ROOT/rel)
                require(rel in known and file_hash(path)==known[rel]['sha256'],f'Frozen raw manifest mismatch: {rel}')
        self.source = self.V.SourceFFD()
        self.obs = pd.read_csv(self.checked(self.V.one('OBSERVATION_FEATURES_LABELS.csv.gz')))
        self.par = pd.read_csv(self.checked(self.V.one('OOF_PARAMETERS.csv.gz')))
        pkpath = self.ref / 'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz'
        self.pk = pd.read_csv(self.checked(pkpath))
        require(not self.pk.duplicated(['case', 'pose_id']).any(), 'Duplicate HP packets')
        self.source_hash = digest(lock)
        self.models = {}
        for route in ('R2', 'R4', 'R5'):
            matches = list(Path(config['l4models_root']).rglob(f'{route}_L4TRAIN.joblib'))
            require(len(matches) == 1, f'Missing/ambiguous L4 model for {route}')
            p = self.checked(matches[0]); obj = joblib.load(p)  # trusted, hash-locked own artifact only
            require(obj['held'] == route and route not in obj['train_routes'], 'Held route in frozen model')
            self.models[route] = (obj, file_hash(p))
        self._cache = {}

    def checked(self, path):
        p = Path(path).resolve()
        if not p.is_file():
            raise BlockedError(f'Unavailable original asset: {p}')
        require(str(p) in self.lock, f'Asset not in lock: {p}')
        require(file_hash(p) == self.lock[str(p)], f'Asset changed: {p}')
        return p

    def case(self, case):
        matches = [x for x in self.V.MANIFEST['cases'] if x['id'] == case]
        require(len(matches) == 1, f'Unknown case {case}')
        return matches[0]

    def legacy(self, route, name):
        pack, sha = self.models[route]
        key, mode, conv = {
            'PWIDE_NOES': ('P_D0','PWIDE_NOES','incremental'), 'PCIR3': ('P_X3','PCIR3','incremental'),
            'WIDE_NOES': ('W_D0','WIDE_NOES','total'), 'CIR_ONLY': ('W_X1','CIR_ONLY','total')
        }[name]
        mdl = pack['models'][key]; med = pack['medians'][key]
        names = list(mdl.feature_names_in_)
        medians = np.array([float(med.get(c, 0.)) for c in names])
        return Corrector(name, mdl, mode, medians, model_hash=sha + ':' + key, mean_convention=conv)

    def load(self, case_id, bias, seed_idx, channel='full'):
        from .oracle_scoring import Truth
        cache_key=(case_id,bias,channel)
        if cache_key in self._cache:
            template,model,truth=self._cache[cache_key]
            seed=self.MC.seed_of(seed_idx)
            controls,x0r=self.V.build_positive_bias_controls(template.t,truth.state[:,:3],bias,seed=seed)
            u=np.column_stack([np.asarray(controls[n]) for n in ('ds_odom','dtheta_gyro','dt_s')])
            inp=Inputs(case_id,template.route,bias,channel,seed_idx,seed,template.packets,u,np.r_[x0r,0.],template.P0,template.anchor,template.robot_z,self.source_hash)
            return inp,model,truth
        case = self.case(case_id); route = case['route']; stem = f'{case_id}_{channel}_{bias}'
        trace_path = self.checked(self.V.one(stem+'_TRACE.npz'))
        with np.load(trace_path, allow_pickle=False) as f:
            t, ids, gt = f['t_s'].copy(), f['pose_id'].copy(), f['truth_scoring_only'].copy()
        req = pd.DataFrame({'pose_id': ids})
        obs = exact_rows(self.obs[(self.obs.case == case_id) & (self.obs.channel == channel)], ['pose_id'], req)
        z = obs[['range_m','s_fp']].to_numpy(float)
        pk = exact_rows(self.pk[self.pk.case == case_id], ['pose_id'], req)
        sample_path = self.checked(self.V.ROOT / case['samples_path'])
        sample = pd.DataFrame(json.loads(sample_path.read_text()))
        require(not sample.pose_id.duplicated().any(), 'Raw samples have duplicate pose IDs')
        selection = pd.Series(np.arange(len(sample)), index=sample.pose_id).loc[ids].to_numpy(int)
        hp = self.checked(self.V.ROOT / case['full_path' if channel == 'full' else 'los_path'])
        Hraw = np.load(hp, mmap_mode='r', allow_pickle=False)
        require(len(Hraw) == len(sample), 'Spectrum/sample cardinality')
        q, mask, fps, powers, features = [], [], [], [], []
        for k, index in enumerate(selection):
            qq, mm, ff, pp = spectrum_profile(np.asarray(Hraw[index,:,:,0]))
            q.append(qq); mask.append(mm); fps.append(ff); powers.append(pp)
            require(mm[0], 'First path not measurable')
            require(abs(qq[0]-z[k,1]) < 1e-9, 'RF observer parity failure')
            logp = np.log10(max(pp[0], np.finfo(float).tiny))
            row = np.r_[qq[0], logp, ff, qq[1:], qq[1:] - qq[0]]
            if channel == 'full':
                old = np.r_[pk.iloc[k]['sF_+0'], pk.iloc[k]['log_fp_power'], pk.iloc[k]['fp_full'],
                            [pk.iloc[k][f'sF_{o:+d}'] for o in OFFSETS[1:]],
                            [pk.iloc[k][f'sF_{o:+d}']-pk.iloc[k]['sF_+0'] for o in OFFSETS[1:]]]
                require(np.allclose(row, old, atol=1e-9, rtol=0, equal_nan=True), 'Frozen CIR feature mismatch')
            features.append(row)
        pars = self.par[(self.par.case == case_id) & (self.par.channel == channel) & (self.par.model == 'POWER_DIAG')]
        exact_rows(pars, ['pose_id'], req)
        mu, R = self.V.base_params(self.par, case_id, channel, ids, 'POWER_DIAG')
        seed = self.MC.seed_of(seed_idx)
        controls, x0r = self.V.build_positive_bias_controls(t, gt, bias, seed=seed)
        u = np.column_stack([controls[n].to_numpy() if hasattr(controls[n], 'to_numpy') else controls[n] for n in ('ds_odom','dtheta_gyro','dt_s')])
        P0 = np.diag(np.r_[self.V.INITIAL_POSE_STD**2, self.V.BIAS_PRIOR_STD**2])
        packets = tuple(Packet(int(ids[k]), float(t[k]), z[k], mu[k], R[k], features[k], q[k], mask[k], int(fps[k]), powers[k]) for k in range(len(t)))
        inputs = Inputs(case_id, route, bias, channel, seed_idx, seed, packets, u, np.r_[x0r,0.], P0,
                        case['anchor'], float(case['robot_z_m']), self.source_hash)
        truth4 = np.c_[gt[:,:3], np.full(len(t), math.radians(self.V.BIAS_LEVELS[bias]))]
        sL = pk['sL_+0'].to_numpy(float) if channel == 'full' else z[:,1].copy()
        shift = pk['fp_shift_tap'].to_numpy(float) if channel == 'full' else np.zeros(len(t))
        model = NativeModel(self.source, self.V, self.core, case)
        truth = Truth(truth4, sL, shift)
        self._cache[cache_key]=(inputs,model,truth)
        return inputs, model, truth

    def independent_reference(self, inputs, truth, model):
        route = inputs.route; pack, _ = self.models[route]
        mdl = pack['models']['P_D0']; med = pack['medians']['P_D0']
        frame = pd.DataFrame(np.stack([p.cir_features for p in inputs.packets]), columns=BASE_FEATURES)
        Xf = self.R2.m_inputs(frame, med)[list(mdl.feature_names_in_)[:-1]].to_numpy(float)
        controls = dict(zip(('ds_odom','dtheta_gyro','dt_s'), inputs.controls.T))
        return self.MC.run(self.source, self.case(inputs.case), controls, inputs.x0.copy(), inputs.P0.copy(),
                           np.stack([p.z for p in inputs.packets]), Xf, mdl, np.stack([p.mu for p in inputs.packets]),
                           np.stack([p.R for p in inputs.packets]), truth.s_los)

    def power_predict(self, train, target):
        """Explicit train table; nested splits can exclude validation groups from every teacher."""
        require(len(train) > 0 and len(target) > 0, 'Empty POWER fit/predict split')
        weights = self.S.B.site_weights(np, pd, train)
        mp, cp, _ = self.S.B.fit_model(np, train, target, weights, 'POWER_BIN_JOINT', self.S.GROUPS)
        out = target[['case','pose_id']].copy()
        out['mu_s'], out['Vs'] = mp[:,1], cp[:,1,1]
        return out
