"""Post-stop numerical diagnosis of retained RAW only. Never traces paths.

No FFT, detector, attribution, threshold change or PASS reclassification.
"""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_mono_polarized')
import drjit as dr
from sionna.rt.utils import cpx_mul, map_angle_to_canonical_range
from native_math import errors


def compare(actual, archive):
    actual=np.asarray(actual,dtype=np.complex128)
    archive=np.asarray(archive,dtype=np.complex128)
    result=errors(actual,archive)
    result['magnitude_relative_l2']=float(np.linalg.norm(abs(actual)-abs(archive))/np.linalg.norm(abs(archive)))
    phase=np.angle(actual*np.conj(archive))
    weight=abs(archive)**2
    result['phase_rad']=dict(weighted_rms=float(np.sqrt(np.sum(weight*phase**2)/weight.sum())),
                             median_abs=float(np.median(abs(phase))),p95_abs=float(np.quantile(abs(phase),.95)),
                             max_abs=float(np.max(abs(phase))))
    return result


def main(capture,out):
    raw=capture/'RAW.npz';manifest=capture/'MANIFEST.json'
    with np.load(raw,allow_pickle=False) as z:a={k:z[k] for k in z.files}
    indices=a['offsets'][:-1]+a['direct_source_index']
    direct32=a['original_field'][indices]
    cfr_direct=[];cfr_full=[];double_minus_original_phase=[]
    for fi,f in enumerate(a['frequencies_hz']):
        lo,hi=a['offsets'][fi:fi+2];coef=a['a'][lo:hi].transpose(1,2,0);tau=a['tau'][lo:hi];n=len(tau)
        # Exact pinned Paths.cir phase and complex multiplication operations,
        # using raw a/tau only. No scene, solver or PathSolver object exists.
        tau_=mi.TensorXf(tau.reshape(1,1,1,1,n))
        phase=-dr.two_pi*mi.Float(float(f))*tau_
        phase=map_angle_to_canonical_range(phase)
        sin_phase,cos_phase=dr.sincos(phase)
        shifted=cpx_mul((mi.TensorXf(coef.real.reshape(1,2,1,2,n)),mi.TensorXf(coef.imag.reshape(1,2,1,2,n))), (cos_phase,sin_phase))
        fields=(np.asarray(shifted[0])+1j*np.asarray(shifted[1])).reshape(2,2,n)
        cfr_direct.append(fields[:,0,a['direct_source_index'][fi]])
        # Same zero-offset CFR shape/reduction as pinned Paths.cfr.
        h=[]
        for v in shifted:
            v=dr.reshape(mi.TensorXf,v,[1,2,1,2,n,1,1])
            h.append(np.asarray(dr.sum(v,axis=-3)).reshape(2,2)[:,0])
        cfr_full.append(h[0]+1j*h[1])
        phase64=-2*np.pi*float(f)*float(tau[a['direct_source_index'][fi]])
        phase32=-2j*np.pi*np.float64(f)*tau
        exp32=np.exp(phase32)[a['direct_source_index'][fi]]
        double_minus_original_phase.append(np.angle(np.exp(1j*phase64)*np.conj(exp32)))
    cfr_direct=np.asarray(cfr_direct);cfr_full=np.asarray(cfr_full)
    expected=np.asarray(double_minus_original_phase)[:,None]
    observed=np.angle(a['direct_f64']*np.conj(a['archive_los']))
    residual=np.angle(np.exp(1j*(observed-expected)))
    result=dict(scope='Post-stop numerical diagnosis on retained raw only; original STOP_MISMATCH unchanged; no new RF, FFT or attribution',
      capture_status=json.loads(manifest.read_text())['status'],
      hashes={name:hashlib.sha256((capture/name).read_bytes()).hexdigest() for name in ('RAW.npz','MANIFEST.json','ARTIFACT_HASHES.json')},
      diagnosis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      archive_dtype=str(a['archive_los'].dtype),raw_coefficient_dtype=str(a['a'].dtype),raw_tau_dtype=str(a['tau'].dtype),
      original_expression_dtype=str(a['original_field'].dtype),
      direct_f64_vs_archive=compare(a['direct_f64'],a['archive_los']),
      direct_original32_vs_archive=compare(direct32,a['archive_los']),
      direct_cfr32_replay_vs_archive=compare(cfr_direct,a['archive_los']),
      full_f64_vs_archive=compare(a['native_f64'],a['archive_full']),
      full_original32_vs_archive=compare(a['native_original32'],a['archive_full']),
      full_saved_cfr32_vs_archive=compare(a['native_cfr32'],a['archive_full']),
      retained_raw_cfr_replay_vs_saved_cfr=compare(cfr_full,a['native_cfr32']),
      double_vs_original_phase_prediction_residual_rad=dict(max_abs=float(abs(residual).max()),rms=float(np.sqrt(np.mean(residual**2)))),
      expected_double_vs_original_phase_rad=dict(max_abs=float(abs(expected).max()),rms=float(np.sqrt(np.mean(expected**2)))))
    out.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(out/'PHASE_CONTROLS.npz',frequencies_hz=a['frequencies_hz'],direct_original32=direct32,
                        direct_cfr32_replay=cfr_direct,full_cfr32_replay=cfr_full,
                        expected_double_minus_original_phase=expected,observed_double_minus_archive_phase=observed,
                        phase_residual=residual)
    result['controls_sha256']=hashlib.sha256((out/'PHASE_CONTROLS.npz').read_bytes()).hexdigest()
    (out/'NUMERICAL_DIAGNOSIS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
