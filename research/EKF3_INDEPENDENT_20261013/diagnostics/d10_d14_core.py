"""D10-D14 NEW-ONLY shared numerical tools.

Never infer universal co/cross from +/-45 RX port labels.  'reference' means
strongest measured port at the frozen common FP by default.  The cross/other
branch may grow even under pure LoS; excess *relative to the reference pulse*
is tested, not the raw slope alone.  Ground truth is never read by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import subprocess
import tempfile
from typing import Callable

import numpy as np


METHODS = ('W0_FP', 'W0_CO_FP', 'W1_EARLY3', 'W2_ADAPTIVE_CROSS', 'W3_PULSE_TEMPLATE', 'W4_TOTAL_ENERGY')


@dataclass(frozen=True)
class EarlyWindowConfig:
    co_port: str = 'auto'   # auto / rx1 / rx2. Never inferred physical co.
    min_taps: int = 1
    max_taps: int = 4        # intentionally VERY short, zero-pad tap ~0.5ns
    max_search_taps: int = 9
    growth_ratio: float = 1.7
    excess_over_co_fp: float = .025
    rise_factor: float = 1.08
    consecutive: int = 2
    guard_before_cross: int = 0
    noise_floor_power: float = 0.

    def validate(self):
        if self.co_port not in ('auto', 'rx1', 'rx2'):
            raise ValueError('Unknown reference-port selection')
        if (self.min_taps < 1 or self.max_taps < self.min_taps or
            self.max_search_taps < self.max_taps or self.consecutive < 1 or
            not 0 <= self.guard_before_cross < self.max_taps or
            self.growth_ratio <= 1 or self.rise_factor <= 1 or
            self.excess_over_co_fp < 0 or self.noise_floor_power < 0):
            raise ValueError('Invalid short-window detection configuration')
        return self


def signed_power_ratio(p):
    a = np.asarray(p, float)
    if a.shape != (2,) or not np.isfinite(a).all() or a.sum() <= 0:
        raise ValueError('Missing/invalid two-port powers')
    return float((a[0]-a[1])/a.sum())


def rankdata(x):
    v = np.asarray(x, float)
    order = np.argsort(v, kind='stable')
    sorted_v = v[order]
    _, first, counts = np.unique(sorted_v, return_index=True, return_counts=True)
    ranks = np.empty(len(v), float)
    for begin, count in zip(first, counts):
        ranks[order[begin:begin+count]] = begin + (count+1)/2.
    return ranks


def correlation(x, y, *, method='pearson'):
    a, b = np.asarray(x, float), np.asarray(y, float)
    valid = np.isfinite(a) & np.isfinite(b)
    a, b = a[valid], b[valid]
    if len(a) < 3 or np.std(a) < 1e-15 or np.std(b) < 1e-15:
        return None
    if method == 'spearman':
        a, b = rankdata(a), rankdata(b)
    elif method != 'pearson':
        raise ValueError(method)
    return float(np.corrcoef(a, b)[0, 1])


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def read_table(path):
    with Path(path).open('r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def validate_stage(root, stage, names):
    root = Path(root)
    record = root/(stage+'_MANIFEST.json')
    if not record.is_file():
        raise FileNotFoundError(record)
    j = json.loads(record.read_text('utf-8'))
    if j.get('stage') != stage or j.get('scientific_PASS') is not False:
        raise RuntimeError('Invalid frozen diagnostic evidence contract: '+stage)
    for name in names:
        path = root/name
        if not path.is_file() or file_sha(path) != j.get('sha256', {}).get(name):
            raise RuntimeError('Input evidence SHA mismatch: '+str(path))
    return j


def write_rows(path, records):
    if not records:
        raise ValueError('No rows for '+str(path))
    keys = tuple(records[0])
    if any(set(row) != set(keys) for row in records):
        raise RuntimeError('CSV inconsistent row schema')
    path = Path(path)
    with path.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(records)


def json_safe(x):
    if isinstance(x, Path):return str(x)
    if isinstance(x, np.ndarray):return json_safe(x.tolist())
    if isinstance(x, np.generic):return json_safe(x.item())
    if isinstance(x, dict):return {str(k):json_safe(v) for k,v in x.items()}
    if isinstance(x, (tuple,list)):return [json_safe(v) for v in x]
    if x is None or isinstance(x,(str,bool,int)):return x
    if isinstance(x,float):
        if not math.isfinite(x):raise ValueError('Nonfinite manifest value')
        return x
    raise TypeError('Unsupported manifest object '+type(x).__name__)


def save_json(path, obj):
    dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(json_safe(obj), indent=2, ensure_ascii=False, allow_nan=False)
    fd, tmp = tempfile.mkstemp(prefix='.'+dest.name, suffix='.tmp', dir=dest.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def stage_finish(out, stage, files, *, config, evidence=None, warnings=None):
    """Manifest is written LAST; absence implies INCOMPLETE; no overwrite."""
    out = Path(out)
    if any(not Path(f).is_file() for f in files):
        raise RuntimeError('Missing output before final manifest')
    project = Path(__file__).resolve().parent
    repo=project.parents[2]
    script_files=sorted(project.glob('d1[0-4]*.py'))
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo,
                         stderr=subprocess.DEVNULL,timeout=5).decode().strip()
        if len(commit)!=40:commit='UNKNOWN_GIT_HEAD'
    except (OSError,subprocess.SubprocessError):
        commit='NOT_AVAILABLE_GIT_CHECKOUT'

    sha={Path(f).name:file_sha(f) for f in files}
    manifest = {'stage':stage, 'status':'EXPLORATORY_EXECUTION_COMPLETED',
        'scientific_PASS':False, 'independent_rf_scene':False,
        'config':config, 'input_evidence':evidence or {}, 'warnings':warnings or [],
        'sha256':sha,'execution_commit':commit,
        'frozen_D0_D5_reference':'43f755b75a5ac83fd6e7e67c3ef8f1f0da579d5d',
        'script_sha256':{p.name:file_sha(p) for p in script_files}}
    save_json(out/(stage+'_MANIFEST.json'), manifest)


def new_output(p):
    v=Path(p).resolve()
    v.mkdir(exist_ok=False,parents=True)
    return v


def extract_cir_methods(cir, *, fp_index, peak_indices=None, config=None, template=None):
    """Return five receiver alternatives from two complex RX CIRs, no truth.

    W2: co/reference RX FP, then stop BEFORE a sustained growth of the OTHER
    port beyond the shape expected from the co pulse.  All methods use a
    COMMON tap window for both ports.  Explicitly flag fully unresolved
    overlap: no CIR-only algorithm can recover an already-contaminated FP.
    """
    cfg = (config or EarlyWindowConfig()).validate()
    h = np.asarray(cir, complex)
    if h.ndim != 2 or h.shape[1] != 2 or not np.isfinite(h).all():
        raise ValueError('Expected finite two-port complex CIR (n_tap,2)')
    n=len(h); k=int(fp_index)
    if n<3 or k<0 or k>=n:raise ValueError('Invalid frozen FP index')
    p = np.abs(h)**2
    fp_port = int(np.argmax(p[k,:]))
    co = fp_port if cfg.co_port=='auto' else (0 if cfg.co_port=='rx1' else 1)
    cr=1-co
    # Per-channel independent 30%-leading-edge FP.  Do not overwrite the
    # original frozen common FP/range with this diagnostic co-only index.
    co_m=np.abs(h[:,co]); co_peak=float(co_m.max())
    kc=int(np.flatnonzero(co_m>=.3*co_peak)[0])
    if cfg.co_port=='auto' and kc>k:
        # Earliest FP should not silently shift late because selected 'co' may
        # be a reflected port.  Preserve the original earlier detector index.
        kc=k
    k0=kc
    cap=min(n,k0+cfg.max_taps)
    search=min(n,k0+cfg.max_search_taps)
    eps=max(cfg.noise_floor_power,1e-24*float(p[k0,:].sum()))
    # Relative cross growth removes the normal shared LoS pulse rise, to
    # first order.  This cannot detect perfectly unresolved early overlap.
    baseline=float((p[k0,cr]+eps)/(p[k0,co]+eps))
    threshold=max(cfg.excess_over_co_fp*p[k0,co], cfg.noise_floor_power)
    onset=None
    for j in range(k0+1,search-cfg.consecutive+1):
        ids=range(j,j+cfg.consecutive)
        rises=all(
            (p[z,cr]+eps)>cfg.rise_factor*(p[z-1,cr]+eps) and
            (p[z,cr]+eps)/(p[z,co]+eps)>cfg.growth_ratio*baseline and
            (p[z,cr]-baseline*p[z,co])>threshold
            for z in ids)
        if rises:
            onset=j
            break
    reason='NO_CROSS_EXCESS_BEFORE_CAP'
    if onset is not None and onset < cap:
        end=max(k0+cfg.min_taps, onset-cfg.guard_before_cross)
        end=min(end,cap)
        reason='CROSS_EXCESS_RISE'
    else:
        end=cap
    if end<=k0: end=min(n,k0+1)
    if (end-k0)<cfg.min_taps:
        end=min(n,k0+cfg.min_taps)
        reason='MIN_TAPS_FALLBACK_POSSIBLE_CONTAMINATION'
    # W0: frozen first-path single tap, not co-selected FP.
    power0=p[k,:]
    early_end=min(n,k0+3)
    W1=p[k0:early_end].sum(axis=0)
    W2=p[k0:end].sum(axis=0)
    W4=p.sum(axis=0)
    # W3: fit a common, fractionally uncertain Hann-pulse leading edge.
    # Absolute FFT delay is unavailable from the template alone: align its
    # *leading edge* to the CO-ONLY observed FP, then fit complex amplitudes
    # for BOTH ports with the SAME shifted template. The co port alone chooses
    # the shift; NEVER fit a separate reflection-removing shift per port.
    template_len=min(n,k0+8)
    part=h[k0:template_len]
    if template is None:
        g=np.ones(template_len-k0, complex)
        template_mode='NO_REFERENCE_CONSTANT_CONTROL'
    else:
        pure=np.asarray(template,complex)
        if pure.ndim!=1 or len(pure)!=n:raise ValueError('Template length mismatch')
        grid=np.arange(template_len-k0)
        options=[]
        for shift in (3,4,5,6):
            gg=pure[(grid-shift)%n]
            denom=float(np.vdot(gg,gg).real)
            amp=(np.vdot(gg,part[:,co])/max(denom,1e-300))
            misfit=float(np.vdot(part[:,co]-amp*gg,part[:,co]-amp*gg).real)
            options.append((misfit,shift,gg))
        _,best_shift,g=min(options,key=lambda z:z[0])
        template_mode='CO_ALIGNED_HANN_LEADING_EDGE_SHIFT_'+str(best_shift)
    norms=float(np.vdot(g,g).real)
    a=(np.conj(g)@part)/max(norms,1e-300)
    W3=np.abs(a)**2
    values={ 'W0_FP':signed_power_ratio(power0),
        'W0_CO_FP':signed_power_ratio(p[k0,:]),
        'W1_EARLY3':signed_power_ratio(W1),
        'W2_ADAPTIVE_CROSS':signed_power_ratio(W2),
        'W3_PULSE_TEMPLATE':signed_power_ratio(W3),
        'W4_TOTAL_ENERGY':signed_power_ratio(W4)}
    extras={'original_fp_index':k, 'selected_reference_rx':co,
        'co_only_fp_index':kc, 'window_begin':k0,'window_end_exclusive':end,
        'window_width_taps':end-k0,'cross_rise_onset':onset,
        'cross_rise_detected':int(onset is not None),
        'stop_reason':reason, 'cross_to_co_ratio_at_fp':baseline,
        'reference_selection_ambiguous':int(min(p[k,:])/max(p[k,:])>.75),
        'unresolved_at_fp_unidentifiable':True,
        'reference_is_physical_co':False,
        'template_model':template_mode}
    return values, extras


def hann_pulse_template(nbins, ntaps):
    if ntaps!=4*nbins:raise ValueError('Frozen 4N FFT contract required')
    freqs=np.arange(nbins,dtype=float)
    hwin=.5-.5*np.cos(2*math.pi*freqs/(nbins-1))
    return np.fft.ifft(np.pad(hwin,(0,ntaps-nbins)))*nbins


def normalized_ukf_update(x, P, z, hfun: Callable[[np.ndarray],np.ndarray], R, *, gate_threshold):
    """Three-state UKF measurement update (prediction handled separately).

    Returns new state/cov/status/NIS.  Missing RF samples are not supported:
    caller must explicitly select the available dimension before calling.
    """
    x=np.asarray(x,float).copy();P=np.asarray(P,float).copy()
    z=np.atleast_1d(np.asarray(z,float));R=np.asarray(R,float)
    if x.shape!=(3,) or P.shape!=(3,3) or R.shape!=(len(z),len(z)):
        raise ValueError('UKF dimension mismatch')
    if min(np.linalg.eigvalsh(P))<=0 or min(np.linalg.eigvalsh(R))<=0:
        raise ValueError('UKF requires positive definite P and R')
    n=3; lam=1.
    L=np.linalg.cholesky((n+lam)*P)
    sigmas=np.asarray([x,*[x+L[:,i] for i in range(n)], *[x-L[:,i] for i in range(n)]])
    sigmas[:,2]=(sigmas[:,2]+math.pi)%(2*math.pi)-math.pi
    wm=np.full(2*n+1,1/(2*(n+lam)));wm[0]=lam/(n+lam)
    wc=wm.copy();wc[0]+=2.
    zm=np.stack([np.atleast_1d(np.asarray(hfun(v),float)) for v in sigmas])
    if zm.shape!=(7,len(z)) or not np.isfinite(zm).all():raise RuntimeError('Invalid UKF predicted measurement')
    zbar=wm@zm
    dz=zm-zbar
    dx=sigmas-x
    dx[:,2]=(dx[:,2]+math.pi)%(2*math.pi)-math.pi
    S=np.einsum('i,ij,ik->jk',wc,dz,dz)+R
    S=(S+S.T)*.5
    if min(np.linalg.eigvalsh(S))<=0:raise RuntimeError('Invalid UKF S')
    inov=z-zbar
    nis=float(inov@np.linalg.solve(S,inov))
    if nis>gate_threshold:
        return x,P,'rejected_NIS',nis
    Pxz=np.einsum('i,ij,ik->jk',wc,dx,dz)
    K=np.linalg.solve(S,Pxz.T).T
    out=x+K@inov
    out[2]=(out[2]+math.pi)%(2*math.pi)-math.pi
    cov=P-K@S@K.T
    cov=(cov+cov.T)*.5
    if np.linalg.eigvalsh(cov).min()<=0:raise RuntimeError('UKF posterior not PD')
    return out,cov,'applied',nis
