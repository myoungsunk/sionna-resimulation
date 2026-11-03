#!/usr/bin/env python3
"""Independent R1B numerical representation audit of existing raw Native arrays.
Do not import the implementer's precision_v1/v2 files or invoke PathSolver.
This is a separate arithmetic/checksum/process validation, not science signoff.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.constants import speed_of_light
import mitsuba as mi
mi.set_variant("llvm_ad_mono_polarized")
import drjit as dr

POSES=(75,305,610,809)
NF=257
def hash_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()

def delay_from_source_geometry(xyz,anchor):
    # Reconstructed separately from Sionna RT 2.0.1 field_calculator.py:
    # path_length = dr.norm(mi.Vector3f(target-source));
    # tau = path_length * dr.rcp(speed_of_light).
    tx=mi.Point3f(*[float(c) for c in anchor])
    rx=mi.Point3f(*[float(c) for c in xyz])
    diff=mi.Vector3f(rx-tx)
    d=dr.norm(diff)
    t=d*dr.rcp(speed_of_light)
    return float(np.asarray(t).reshape(-1)[0])

def observe(h):
    window=(1-np.cos(2*np.pi*np.arange(NF)/(NF-1)))/2
    field=np.fft.ifft(h*window[:,None],n=NF*4,axis=0)*NF
    mag=np.abs(field)
    port=int(np.argmax(mag.max(axis=0)))
    edge=np.flatnonzero(mag[:,port]>=.3*np.max(mag[:,port]))[0]
    power=np.square(np.abs(field[edge]))
    return dict(tap=int(edge),port=port,s=float((power[0]-power[1])/sum(power)))

def independent_check(root):
    results=[]
    for pid in POSES:
        data_path=root / f"pose_{pid:04d}.npz"
        meta_path=root / f"pose_{pid:04d}.json"
        metadata=json.loads(meta_path.read_text())
        assert metadata['pose_id']==pid
        assert hash_file(data_path)==metadata['raw_sha256']
        with np.load(data_path,allow_pickle=False) as data:
            frequencies=data['freq_hz']
            assert np.array_equal(frequencies,6250400000.+1950000.*np.arange(NF))
            raw_native=data['H_los'][:,:,0]
            source=data['source_physical_h']
            xyz=data['xyz_m']
            anchor=data['anchor_xyz_m']
            assert source.shape==raw_native.shape==(NF,2)
            tau_rep=delay_from_source_geometry(xyz,anchor)
            tau64=np.linalg.norm(xyz.astype(float)-anchor.astype(float))/speed_of_light
            correction=np.exp(1j*(-2*np.pi*frequencies*(tau_rep-tau64)))
            calculated=source*correction[:,None]
            eps=np.linalg.norm(raw_native)
            old=float(np.linalg.norm(raw_native-source)/eps)
            now=float(np.linalg.norm(raw_native-calculated)/eps)
            obs_raw=observe(raw_native);obs_src=observe(calculated)
            synthesis_absmax=0.
            for mode in ('los','full'):
                raw_h=data[f'H_{mode}']
                amp=data[f'{mode}_a']
                tau=data[f'{mode}_tau_s']
                offsets=data[f'{mode}_path_offsets']
                assert len(offsets)==NF+1
                assert offsets[-1]==len(tau)
                for k in range(NF):
                    start,end=offsets[k:k+2]
                    assert end>start
                    rebuild=(amp[:,:,start:end]*np.exp(-1j*2*np.pi*frequencies[k]*tau[start:end])[None,None,:]).sum(-1)
                    synthesis_absmax=max(synthesis_absmax,float(np.max(abs(raw_h[k]-rebuild))))
            tau_saved=data['los_tau_s']
            assert len(tau_saved)==NF
            results.append(dict(pose_id=pid,raw_sha256=metadata['raw_sha256'],
                raw_complex_relative=old,adjusted_complex_relative=now,
                signed_s_abs=abs(obs_raw['s']-obs_src['s']),
                tap_mismatch=int(obs_raw['tap']!=obs_src['tap']),
                port_mismatch=int(obs_raw['port']!=obs_src['port']),
                path_reconstruction_absolute_max=synthesis_absmax,
                source_only_tau_matches_saved_native_all_bins=bool(np.array_equal(
                    tau_saved,np.full(NF,tau_rep,dtype=np.float64))),
                native_minus_source_delay_max_fs=float(np.max(abs(tau_saved-tau_rep))*1e15)))
    errors=np.array([x['adjusted_complex_relative'] for x in results])
    s=np.array([x['signed_s_abs'] for x in results])
    metrics=dict(n=len(results),
       complex_rms=float(np.sqrt(np.mean(errors**2))),
       complex_max=float(np.max(errors)),
       s_rms=float(np.sqrt(np.mean(s**2))),
       s_max=float(np.max(s)),
       all_tau_match=all(x['source_only_tau_matches_saved_native_all_bins'] for x in results),
       largest_path_reconstruction_absolute_error=max(x['path_reconstruction_absolute_max'] for x in results),
       total_tap_mismatches=sum(x['tap_mismatch'] for x in results),
       total_port_mismatches=sum(x['port_mismatch'] for x in results))
    pass_check=(metrics['n']==4 and metrics['complex_rms']<=1e-4 and metrics['complex_max']<=5e-4
      and metrics['s_rms']<=2e-6 and metrics['s_max']<=2e-5
      and metrics['all_tau_match'] and metrics['largest_path_reconstruction_absolute_error']<1e-10
      and metrics['total_tap_mismatches']==metrics['total_port_mismatches']==0)
    return dict(schema="R1B_PREC_V2_INDEPENDENT_ARITHMETIC_4_V1",
        status="INDEPENDENT_V2_NUMERIC_PARITY_PASS" if pass_check else "INDEPENDENT_V2_NUMERIC_HOLD",
        original_science_status="HOLD_RF_PARITY",independent_scientific_signoff=False,
        source_only_physical_model_unchanged=True,
        no_fitted_parameters=True,no_native_data_used_to_predict_source=True,
        auditor_native_solver_calls=0,limits_unchanged=True,metrics=metrics,records=results)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--raw-dir",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(str(args.out))
    out=independent_check(args.raw_dir)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(status=out['status'],metrics=out['metrics'])),flush=True)
    return 0 if out['status']=="INDEPENDENT_V2_NUMERIC_PARITY_PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
