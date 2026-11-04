"""C3 raw QA adapted from frozen SM0 qa; no archive substitution or RT imports."""
import math
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'NEW_RT_DATA/SM0'))
from native_math import independent_sum, vector_fields
from native_math import label_chain


def repeat_check(first, second):
    keys=('a','tau','valid','objects','interactions','primitives','vertices','theta_t','phi_t','theta_r','phi_r','source_index','original_field','fields')
    for k in keys:
        if first[k].dtype!=second[k].dtype or first[k].shape!=second[k].shape or not np.array_equal(first[k],second[k]):
            raise ValueError('repeat raw mismatch '+k)
    if first['labels']!=second['labels']:raise ValueError('repeat semantic labels')
    e=error(second['original_sum'],first['original_sum'])
    if e['relative_l2']>1e-8 or e['max_normalized']>1e-8:raise ValueError('repeat channel')
    return dict(raw_exact=True,channel_error=e)


def source_groups(a,lookup):
    labels=a['group_labels'].tolist();freq=a['frequencies_hz'];counts=np.zeros((len(labels),len(freq)),np.int32)
    if a['group_ids'].tolist()!=[hashlib.sha256(x.encode()).hexdigest() for x in labels]:raise ValueError('semantic hash')
    for fi in range(len(freq)):
        lo,hi=map(int,a['offsets'][fi:fi+2])
        if not np.array_equal(a['source_index'][lo:hi],np.arange(hi-lo)):raise ValueError('source index')
        for i in range(lo,hi):
            valid=bool(a['valid'][i].any())
            if not valid and np.any(a['a'][i]):raise ValueError('nonzero invalid')
            name=label_chain(a['objects'][i],a['interactions'][i],lookup,valid)
            gi=int(a['source_group'][i])
            if labels[gi]!=name:raise ValueError('raw semantic chain')
            counts[gi,fi]+=1
    if not np.array_equal(counts,a['group_count']) or not np.array_equal(counts==0,a['group_missing']):raise ValueError('count/missing')
    if any(not np.isfinite(a[k]).all() for k in ('a','tau','vertices','theta_t','phi_t','theta_r','phi_r')):raise ValueError('nonfinite raw')


def direct_projection(a,banks,xyz,yaw_deg):
    """Original los_check independent FFD projection on retained DIRECT rays, all 257 bins."""
    from scipy.interpolate import RegularGridInterpolator
    angle=math.radians(yaw_deg);c,s=math.cos(angle),math.sin(angle)
    rots={'tx':np.diag([1.,-1.,-1.]),'rx':np.array([[c,-s,0],[s,c,0],[0,0,1.]])}
    tx=np.array([10.,0.,2.7-.05]);rx=np.asarray(xyz);distance=float(np.linalg.norm(rx-tx));u=(rx-tx)/distance
    predicted=[];actual=[];delay=[];per_bin=[]
    for fi,f in enumerate(a['frequencies_hz']):
        fields={}
        for role in ('tx','rx'):
            loc=rots[role].T@(u if role=='tx' else -u)
            theta=np.arccos(np.clip(loc[2],-1,1));phi=np.arctan2(loc[1],loc[0]);vec=[]
            for b in banks:
                th,ph=np.deg2rad(b['theta_deg']),np.deg2rad(b['phi_deg']);pp=(phi-ph[0])%(2*np.pi)+ph[0]
                e=RegularGridInterpolator((th,ph),np.stack((b['e_theta'][fi],b['e_phi'][fi]),axis=-1))([[theta,pp]])[0]
                et=np.array([np.cos(theta)*np.cos(phi),np.cos(theta)*np.sin(phi),-np.sin(theta)])
                ep=np.array([-np.sin(phi),np.cos(phi),0.])
                vec.append(rots[role]@(et*e[0]+ep*e[1])*np.sqrt(2*np.pi/376.730313668))
            fields[role]=np.asarray(vec)
        expected=fields['rx']@fields['tx'].T*299792458./f/(4*np.pi*distance)
        di=int(a['offsets'][fi])+int(a['direct_source_index'][fi]);observed=a['a'][di]
        d=abs(float(a['tau'][di])-distance/299792458.)
        e=error(observed,expected)
        if e['relative_l2']>1e-4 or d>1e-12:raise ValueError('direct projection/delay bin '+str(fi))
        predicted.append(expected);actual.append(observed);delay.append(d);per_bin.append(e['relative_l2'])
    actual=np.asarray(actual);predicted=np.asarray(predicted)
    out=dict(joint=error(actual,predicted),per_rx=[error(actual[:,r],predicted[:,r]) for r in range(2)],max_bin_relative=max(per_bin),max_delay_s=max(delay))
    if any(e['relative_l2']>1e-4 for e in [out['joint'],*out['per_rx']]):raise ValueError('direct projection port')
    return out

THRESHOLDS = dict(reconstruction_relative_l2=1e-8, reconstruction_max_normalized=1e-8, direct_coefficient_relative=1e-4, direct_delay_s=1e-12)
ATTRIBUTION = 'original complex64 per-ray phase expression; semantic groups accumulated in complex128'
SUCCESS_STATUS = 'C3_RAW_NUMERICAL_PASS'


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
    if 'archive_full' in a or 'archive_los' in a:raise ValueError('new yaw has no archive comparator')
    if np.__version__ != '1.26.4':
        raise ValueError('pinned numpy 1.26.4 required for scalar-promotion semantics')
    if a['a'].dtype != np.complex64 or a['tau'].dtype != np.float32:
        raise ValueError('raw dtype changed')
    if a['original_field'].dtype!=np.complex64 or a['fields'].dtype!=np.complex128:raise ValueError('phase precision changed')
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
    for name in ('a','tau','fields','original_field','group_fields','native_f64','native_original32','direct_f64'):
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
        checks[name]['per_rx']=[error(actual[:,r],ref[:,r]) for r in range(2)]
        if any(v['relative_l2']>1e-8 or v['max_normalized']>1e-8 for v in [checks[name],*checks[name]['per_rx']]):
            raise ValueError(name+' failed')
    return dict(status=SUCCESS_STATUS,attribution_reference=ATTRIBUTION,thresholds=THRESHOLDS,checks=checks,archive_comparison='NOT_APPLICABLE_NEW_YAW'),legacy_groups
