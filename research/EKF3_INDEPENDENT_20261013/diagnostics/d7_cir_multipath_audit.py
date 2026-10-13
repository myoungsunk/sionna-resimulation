"""D7: frozen Full/LoS CIR feature and truth-labelled counterfactual audit.

USER-RUN ONLY.  Online RX1/RX2 features are written to a SEPARATE CSV with
NO ground truth or LoS counterfactual.  Oracle labels are saved only to a
second file.  RX1/RX2 are +-45-degree physical ports, NOT universal co/cross.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from d6_d9_common import (B_OLD, OBS, EVAL_START, check_inputs,
                          checked_path, finish, make_out, original_lut,
                          spectrum, tap_metres, write_csv, s_model, file_sha, P3_MODEL, corrected_ranges)
from p3_compat import frozen_detector
from run_d0_d4 import flat_eval_range
from run_d5_regimes import timelines

# All values in this schema are available from observed Full RF H (or LoS H
# in the control arm).  The D8 estimator and D9 runtime explicitly whitelist
# numeric FEATURES and cannot access labels/truth.
NUMERIC_FEATURES = (
    's_fp','range_raw_m','mount_deg','fp_tap','rx1_fp_power','rx2_fp_power',
    'log_fp_power','peak_fp_ratio','peak_minus_fp_m',
    'late_energy_fraction','tau_rms_ns', 'first_late_s_difference',
    'rx_port_first_tap_delta_m','s_neighborhood_std',
    'phase_fp_rad','phase_late_shift_rad','phase_valid',
    'tap_step_delta_m', 'rx1_first_tap','rx2_first_tap',
)
GEOMETRY_BASE = ('case','route','channel','sample_index','pose_id','t_s','eval_after_30s')
ONLINE_KEYS = GEOMETRY_BASE + NUMERIC_FEATURES


def ratio(p1, p2):
    den = p1 + p2
    return float((p1-p2)/den) if den > 0 else math.nan


def one_feature(cir: np.ndarray, detected: dict, pos: int,
                first_previous: int | None, tm: float,
                *, guard: int = 8) -> dict:
    """Compute observable CIR features from a single selected TX0 column."""
    if cir.ndim != 2 or cir.shape[1] != 2 or guard < 1:
        raise ValueError('Expected 2-RX CIR and positive leakage guard')
    n = len(cir)
    k = int(detected['index'][pos])
    pk = int(detected['peak_idx'][pos])
    if not (0 <= k < n and 0 <= pk < n):
        raise RuntimeError('Invalid first-path/peak index')
    power = abs(cir)**2
    total = power.sum(axis=1)
    fp = power[k, :]
    first_power = float(fp.sum())
    if first_power <= 0:
        raise RuntimeError('Undefined first-path polarimetry')
    peak_power = float(total.max())
    x = np.arange(n, dtype=float)
    sum_total = float(total.sum())
    mean_delay = float(x @ total/sum_total)
    spread = float(math.sqrt(max(0., (((x-mean_delay)**2) @ total)/sum_total)))
    # Suppress a few taps of deterministic window sidelobes near the FP; this
    # is a *heuristic descriptor*, not a guaranteed reflection isolation.
    late_begin = min(k+guard+1, n)
    late = power[late_begin:, :].sum(axis=0)
    late_tot = float(late.sum())
    s1 = ratio(float(fp[0]),float(fp[1]))
    sl = ratio(float(late[0]),float(late[1]))
    # RX-specific 30%-leading-edge taps (as *quality features* only);
    # do not alter the common FP index used for range and s.
    magnitudes = abs(cir)
    port_indices = []
    for col in range(2):
        pmag = magnitudes[:,col]
        port_indices.append(int(np.argmax(pmag >= .3*pmag.max())))
    neigh = power[max(k-4,0):min(k+5,n)]
    s_neigh = (neigh[:,0]-neigh[:,1])/np.maximum(neigh.sum(axis=1),1e-300)
    cross_fp = complex(cir[k,0] * np.conj(cir[k,1]))
    cross_late = complex(np.sum(cir[late_begin:,0]*np.conj(cir[late_begin:,1])))
    # Invalid phase is zero only as a numerical storage convention; the
    # separate validity indicator is REQUIRED for all downstream models.
    valid = bool(min(fp)/max(fp)>1e-4 and abs(cross_late)>1e-20)
    phase_fp = float(np.angle(cross_fp)) if valid else 0.
    phase_late_shift = float(np.angle(cross_late*np.conj(cross_fp))) if valid else 0.
    return dict(s_fp=s1,range_raw_m=k*tm,
        fp_tap=k,rx1_fp_power=float(fp[0]),rx2_fp_power=float(fp[1]),
        log_fp_power=math.log(max(first_power,1e-300)),
        peak_fp_ratio=peak_power/first_power,
        peak_minus_fp_m=(pk-k)*tm,
        late_energy_fraction=late_tot/max(sum_total,1e-300),
        tau_rms_ns=spread*tm/299792458.0*1e9,
        first_late_s_difference=(s1-sl) if math.isfinite(sl) else 0.,
        rx_port_first_tap_delta_m=(port_indices[0]-port_indices[1])*tm,
        s_neighborhood_std=float(np.std(s_neigh)),
        phase_fp_rad=phase_fp,
        phase_late_shift_rad=phase_late_shift,
        phase_valid=int(valid),
        tap_step_delta_m=0. if first_previous is None else (k-first_previous)*tm,
        rx1_first_tap=port_indices[0],rx2_first_tap=port_indices[1])


def case_receiver(p0, case, channel, freqs, indices, guard, chunk_size, e1_fold=None):
    H = np.load(checked_path(p0,case[f'{channel}_path']),
                allow_pickle=False,mmap_mode='r')
    if tuple(H.shape) != tuple(case['H_shape']):
        raise RuntimeError('RF H frozen shape mismatch')
    if chunk_size <= 0:
        raise ValueError('chunk-size must be positive')
    tm = tap_metres(freqs)
    features=[]; previous=None
    raw_s=[]; raw_r=[]; raw_idx=[]; e1_physical=[]
    for begin in range(0,len(indices),chunk_size):
        sample_indices=indices[begin:begin+chunk_size]
        batch=np.asarray(H[sample_indices],complex)
        det=frozen_detector(batch,freqs,float(case['mount_deg']),OBS,
                            chunk_size=len(batch))
        if e1_fold is not None:
            e1 = corrected_ranges(det, e1_fold, channel='full',
                                  allow_e1_on_los=False)['E1_FULL_LORO']
            e1_physical.extend(e1.tolist())
        cir=OBS.cir_batch(batch[...,0])
        raw=OBS.first_path_batch(cir,float(freqs[1]-freqs[0]))
        if not (np.array_equal(det['index'],raw['index']) and
                np.allclose(det['s'],raw['s'],atol=1e-12,rtol=0) and
                np.allclose(det['range_raw_m'],raw['range_m'],atol=1e-10,rtol=0)):
            raise RuntimeError('Frozen first-path observer parity failed')
        for j in range(len(batch)):
            feat=one_feature(cir[j],det,j,previous,tm,guard=guard)
            feat['mount_deg']=float(case['mount_deg'])
            if not np.isclose(feat['s_fp'],det['s'][j],atol=1e-12):
                raise RuntimeError('CIR signed power ratio parity failed')
            if not np.isclose(feat['range_raw_m'],det['range_raw_m'][j],atol=1e-10):
                raise RuntimeError('CIR range parity failed')
            features.append(feat)
            raw_s.append(float(det['s'][j])); raw_r.append(float(det['range_raw_m'][j]))
            raw_idx.append(int(det['index'][j]));previous=int(det['index'][j])
    return (features,np.asarray(raw_s),np.asarray(raw_r),np.asarray(raw_idx),
            np.asarray(e1_physical,float))


def at_tap_s(H: np.ndarray, fr: np.ndarray, indices: np.ndarray,
             taps: np.ndarray, chunk_size=64):
    """OFFLINE counterfactual: Full RF polarization at the LoS-chosen tap."""
    s=np.empty(len(indices))
    for a in range(0,len(indices),chunk_size):
        block=np.asarray(H[indices[a:a+chunk_size],...,0],complex)
        cir=OBS.cir_batch(block)
        t=taps[a:a+len(block)].astype(int)
        p=abs(cir[np.arange(len(block)),t,:])**2
        s[a:a+len(block)]=(p[:,0]-p[:,1])/np.maximum(p.sum(axis=1),1e-300)
    return s


def build_case(p0,case,fr,t,truth,pids,*,guard,chunk,alphas):
    pospath=checked_path(p0,case['samples_path'])
    poses=json.loads(pospath.read_text(encoding='utf-8'))
    index_by_id={int(s['pose_id']):i for i,s in enumerate(poses)}
    if len(index_by_id)!=len(poses):raise RuntimeError('Duplicate frozen RF pose id')
    ids=np.asarray([index_by_id[int(pid)] for pid in pids],int)
    p3 = json.loads(P3_MODEL.read_text(encoding='utf-8'))
    if p3.get('chosen') != 'E1_on_B' or case['route'] not in p3['loro_fold_params']:
        raise RuntimeError('Frozen E1 route-held-out coefficient contract changed')
    fold = p3['loro_fold_params'][case['route']]
    lo, sl, rl, kl, _=case_receiver(p0,case,'los',fr,ids,guard,chunk)
    fu, sf, rf, kf, e1_full=case_receiver(p0,case,'full',fr,ids,guard,chunk,e1_fold=fold)
    if len(e1_full) != len(t) or not np.isfinite(e1_full).all():
        raise RuntimeError('Frozen E1 range label generation failed')
    if not len(lo)==len(fu)==len(t):raise RuntimeError('timeline observation length mismatch')
    # True geometry and LoS LUT are scoring-only.  None are present in online.
    anc=np.asarray(case['anchor'],float)
    d=np.linalg.norm(np.column_stack([truth[:,:2]-anc[:2],
                          np.full(len(t),float(case['robot_z_m'])-anc[2])]),axis=1)
    lut=original_lut(p0)
    s_true=np.asarray(s_model(lut,case['anchor'],case['robot_z_m'],
                 truth[:,0],truth[:,1],truth[:,2],case['mount_deg']),float)
    flat=flat_eval_range(d,fr)
    full_H=np.load(checked_path(p0,case['full_path']),mmap_mode='r',allow_pickle=False)
    s_at_los=at_tap_s(full_H,fr,ids,kl,chunk_size=chunk)
    e_flat=flat-d;e_ffd=rl-flat;e_mp=rf-rl
    if not np.allclose(e_flat+e_ffd+e_mp,rf-d,atol=1e-9,rtol=0):
        raise RuntimeError('D7 range flat/FFD/MP identity failed')
    tap_effect=sf-s_at_los
    channel_effect=s_at_los-sl
    if not np.allclose(tap_effect+channel_effect,sf-sl,atol=1e-10,rtol=0):
        raise RuntimeError('D7 s tap/channel identity failed')
    online=[];labels=[]
    for k in range(len(t)):
        for channel,feat,s_obs,r_obs,index in (
            ('los',lo[k],sl[k],rl[k],kl[k]),
            ('full',fu[k],sf[k],rf[k],kf[k])):
            metadata=dict(case=case['id'],route=case['route'],channel=channel,
                          sample_index=k,pose_id=int(pids[k]),t_s=float(t[k]),
                          eval_after_30s=int(t[k]>=EVAL_START))
            o=metadata|feat
            if set(o)!=set(ONLINE_KEYS):
                raise RuntimeError('Online feature schema changed or contains oracle keys')
            online.append({key:o[key] for key in ONLINE_KEYS})
            labels.append(dict(**metadata,true_x_m=float(truth[k,0]),
               true_y_m=float(truth[k,1]),true_heading_rad=float(truth[k,2]),
               true_range_m=float(d[k]),s_model_at_truth=float(s_true[k]),
               error_s=float(s_obs-s_true[k]),
               error_range_B_OLD_m=float(r_obs-B_OLD-d[k]),
               error_range_E1_FULL_LORO_m=(float(e1_full[k]-d[k])
                   if channel=='full' else None),
               e_flat_m=float(e_flat[k]),e_ffd_m=float(e_ffd[k]),e_mp_m=float(e_mp[k]),
               full_minus_los_s=float(sf[k]-sl[k]),
               tap_selection_effect_s=float(tap_effect[k]),
               same_tap_channel_effect_s=float(channel_effect[k]),
               full_at_los_tap_s=float(s_at_los[k]),
               tap_switch=int(kf[k]!=kl[k]),
               oracle_label_only=1))
    hybrids=[]
    for alpha in alphas:
        # H_LOS + alpha*(H_FULL - H_LOS) is a constructed numerical
        # counterfactual, NOT a new physically independent RF environment.
        Hlos=np.load(checked_path(p0,case['los_path']),mmap_mode='r',allow_pickle=False)
        for a in range(0,len(ids),chunk):
            inds=ids[a:a+chunk]
            synthetic=np.asarray(Hlos[inds],complex)+alpha*(
                np.asarray(full_H[inds],complex)-np.asarray(Hlos[inds],complex))
            obs=frozen_detector(synthetic,fr,float(case['mount_deg']),OBS,
                                chunk_size=len(inds))
            for j in range(len(inds)):
                k=a+j
                if t[k]<EVAL_START:continue
                hybrids.append(dict(case=case['id'],route=case['route'],
                    sample_index=k,alpha_mp=alpha,range_error_B_OLD_m=float(
                    obs['range_raw_m'][j]-B_OLD-d[k]),
                    s_error=float(obs['s'][j]-s_true[k]),
                    fp_tap=int(obs['index'][j]),
                    scene_type='CONSTRUCTED_INTERPOLATION_NOT_RF_REALIZATION'))
    return online,labels,hybrids


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--cases',nargs='*',default=[])
    ap.add_argument('--guard-taps',type=int,default=8)
    ap.add_argument('--chunk-size',type=int,default=64)
    ap.add_argument('--hybrid-alphas',type=float,nargs='*',default=[])
    args=ap.parse_args()
    if not 0 < args.guard_taps < 100 or not args.chunk_size>0:
        raise ValueError('invalid window/chunk')
    if any(not 0.<=x<=1. for x in args.hybrid_alphas):
        raise ValueError('Counterfactual MP alpha must be within [0,1]')
    p0=check_inputs()
    fr=spectrum(p0)
    bycase={c['id']:c for c in p0['cases']}
    cases=args.cases or list(bycase)
    if len(set(cases))!=len(cases) or any(c not in bycase for c in cases):
        raise ValueError('Bad case selector')
    routes=timelines(p0)
    online=[];labels=[];hybrids=[]
    for cid in cases:
        case=bycase[cid]
        t,truth,pids=routes[case['route']]
        a,b,c=build_case(p0,case,fr,t,truth,pids,
                         guard=args.guard_taps,chunk=args.chunk_size,
                         alphas=args.hybrid_alphas)
        online.extend(a);labels.extend(b);hybrids.extend(c)
    out=make_out(args.out)
    a=out/'D7_ONLINE_CIR_FEATURES.csv'
    b=out/'D7_ORACLE_EVALUATION_LABELS.csv'
    write_csv(a,online);write_csv(b,labels)
    artifacts=[a,b]
    if hybrids:
        c=out/'D7_NUMERICAL_HYBRID_COUNTERFACTUAL.csv'
        write_csv(c,hybrids);artifacts.append(c)
    finish(out,'D7',vars(args)|{'out':str(out)},artifacts,caveats=[
        'Two physical RX +/-45 channels are not invariant co/cross labels',
        'Additional CIR attributes are not separate independent RF sensors',
        'E1 range residual is offline-only label from frozen route-held-out E1; LoS field is blank',
        'phase_valid is NUMERICAL only, not SNR or phase hardware-calibration evidence',
        'Delay spread/late energy include Hann sidelobes and finite bandwidth',
        'Oracle labels and Full-at-LoS-tap may only be used for OFFLINE scoring',
        'Synthetic H alpha mixtures are numerical attribution probes, not new scenes'])
    print('D7_EXPLORATORY_DONE',str(out))

if __name__=='__main__':
    main()
