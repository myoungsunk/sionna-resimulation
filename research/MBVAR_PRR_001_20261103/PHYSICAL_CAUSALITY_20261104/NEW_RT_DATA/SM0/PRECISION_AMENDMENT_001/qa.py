"""SM0-PRECISION-001. Pure retained-ray QA, no solver or FFT imports."""
import math
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native_math import independent_sum, vector_fields

THRESHOLDS = dict(reconstruction_relative_l2=1e-8, reconstruction_max_normalized=1e-8,
                  archive_full_relative_l2=1e-3, archive_los_relative_l2=1e-5)
ATTRIBUTION = 'original complex64 per-ray phase expression; semantic groups accumulated in complex128'
SUCCESS_STATUS = 'AMENDED_NUMERICAL_PASS'


def error(actual, reference):
    actual = np.asarray(actual, np.complex128)
    reference = np.asarray(reference, np.complex128)
    if actual.shape != reference.shape or not np.isfinite(actual).all() or not np.isfinite(reference).all():
        raise ValueError('nonfinite or shape mismatch')
    norm = float(np.linalg.norm(reference))
    peak = float(abs(reference).max())
    if norm == 0 or peak == 0:
        raise ValueError('zero reference')
    delta = actual - reference
    return dict(relative_l2=float(np.linalg.norm(delta) / norm),
                max_normalized=float(abs(delta).max() / peak),
                max_absolute=float(abs(delta).max()))


def scalar_sum(fields):
    return np.array([complex(math.fsum(float(v.real) for v in fields[:, r]),
                             math.fsum(float(v.imag) for v in fields[:, r])) for r in range(2)])


def evaluate_arrays(a):
    if np.__version__ != '1.26.4':
        raise ValueError('pinned numpy 1.26.4 required for scalar-promotion semantics')
    if a['a'].dtype != np.complex64 or a['tau'].dtype != np.float32:
        raise ValueError('raw dtype changed')
    freq = a['frequencies_hz']
    offsets = a['offsets']
    labels = a['group_labels'].tolist()
    ng = len(labels)
    if freq.shape != (257,) or freq.dtype != np.float64 or not np.isfinite(freq).all() or np.any(np.diff(freq) <= 0):
        raise ValueError('frequency grid')
    if offsets.shape != (258,) or offsets.dtype.kind not in 'iu' or offsets[0] != 0 or offsets[-1] != len(a['tau']) or np.any(np.diff(offsets) <= 0):
        raise ValueError('offsets')
    n = len(a['tau'])
    if a['a'].shape != (n,2,2) or a['fields'].shape != (n,2) or a['original_field'].shape != (n,2):
        raise ValueError('raw shape')
    if len(set(labels)) != ng or labels.count('DIRECT') != 1 or int(a['direct_group']) != labels.index('DIRECT'):
        raise ValueError('group identity')
    gids = a['source_group']
    if gids.shape != (n,) or gids.dtype.kind not in 'iu' or np.any(gids < 0) or np.any(gids >= ng):
        raise ValueError('source_group')
    if a['direct_source_index'].shape != (257,) or a['direct_source_index'].dtype.kind not in 'iu':
        raise ValueError('direct index schema')
    for name in ('a','tau','fields','original_field','group_fields','archive_full','archive_los','native_f64','native_original32','direct_f64'):
        if not np.isfinite(a[name]).all():
            raise ValueError('nonfinite '+name)
    legacy_groups = np.zeros((ng,257,2),np.complex128)
    f64_groups = np.zeros_like(legacy_groups)
    legacy_sum, original_sum, scalar_f64, direct = [], [], [], []
    checks = {}
    for fi, f in enumerate(freq):
        lo, hi = map(int, offsets[fi:fi+2])
        # Original extract() creates a C-contiguous [RX,TX,path] coefficient.
        # NumPy reduction order depends on strides, so restore that layout too.
        coef = np.ascontiguousarray(a['a'][lo:hi].transpose(1,2,0))
        tau = a['tau'][lo:hi]
        legacy = (coef[:,0,:] * np.exp(-2j*np.pi*np.float64(f)*tau)[None,:]).T
        if legacy.dtype != np.complex64 or not np.array_equal(legacy, a['original_field'][lo:hi]):
            raise ValueError('legacy per-ray replay mismatch')
        f64 = vector_fields(coef,tau,f)
        if not np.array_equal(f64,a['fields'][lo:hi]):
            raise ValueError('F64 per-ray replay mismatch')
        di = int(a['direct_source_index'][fi])
        local = gids[lo:hi]
        direct_local = np.flatnonzero(local == int(a['direct_group']))
        if not np.array_equal(direct_local,np.array([di])):
            raise ValueError('direct identity')
        for j, gi in enumerate(local):
            legacy_groups[gi,fi] += legacy[j]
            f64_groups[gi,fi] += f64[j]
        legacy_sum.append(scalar_sum(legacy))
        original_sum.append(legacy.T.sum(axis=1))
        scalar_f64.append(independent_sum(coef,tau,f))
        direct.append(legacy[di])
    original_sum, legacy_sum, scalar_f64, direct = map(np.asarray,(original_sum,legacy_sum,scalar_f64,direct))
    if not np.array_equal(original_sum,a['native_original32']):
        raise ValueError('legacy reduction mismatch')
    if not np.array_equal(f64_groups,a['group_fields']):
        raise ValueError('saved F64 grouping mismatch')
    if 'INVALID' in labels and np.any(legacy_groups[labels.index('INVALID')]):
        raise ValueError('invalid path carries field')
    for name, actual, ref in (
        ('f64_reconstruction',f64_groups.sum(0),scalar_f64),
        ('f64_saved_native',a['native_f64'],scalar_f64),
        ('f64_saved_direct',a['direct_f64'],f64_groups[int(a['direct_group'])]),
        ('legacy_reconstruction',legacy_groups.sum(0),legacy_sum)):
        checks[name] = error(actual,ref)
        if checks[name]['relative_l2'] > 1e-8 or checks[name]['max_normalized'] > 1e-8:
            raise ValueError(name+' failed')
    for name, actual, ref, limit in (
        ('archive_full_original32',original_sum,a['archive_full'],1e-3),
        ('archive_full_attribution',legacy_groups.sum(0),a['archive_full'],1e-3),
        ('archive_los_legacy',direct,a['archive_los'],1e-5)):
        checks[name] = error(actual,ref)
        checks[name]['per_rx'] = [error(actual[:,r],ref[:,r]) for r in range(2)]
        if any(x['relative_l2'] > limit for x in [checks[name],*checks[name]['per_rx']]):
            raise ValueError(name+' failed')
    checks['f64_archive_full_diagnostic'] = error(scalar_f64,a['archive_full'])
    checks['f64_archive_los_diagnostic'] = error(a['direct_f64'],a['archive_los'])
    checks['legacy_group_vs_original32_diagnostic'] = error(legacy_groups.sum(0),original_sum)
    return dict(status=SUCCESS_STATUS,amendment_id='SM0-PRECISION-001',
                attribution_reference=ATTRIBUTION,thresholds=THRESHOLDS,checks=checks), legacy_groups
