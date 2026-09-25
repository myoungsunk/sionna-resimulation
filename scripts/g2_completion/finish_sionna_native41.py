"""Bind native per-frequency Sionna paths to saved H, CIR, detector and consumer."""
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from rt_cp_uwb_py.g2_scoped_channel import observe,ARMS
from rt_cp_uwb_py.g2_native_channel import file_sha,load_native_link,sum_native_paths


def write(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False),encoding='utf8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--raw',type=Path,required=True)
    ap.add_argument('--out-name',default='production_v2')
    a=ap.parse_args();out=a.root/a.out_name;out.mkdir(exist_ok=False)
    c=json.loads((a.root/'CONFIG.json').read_text());source=json.loads((a.raw/'STATUS.json').read_text())
    assert source['status']=='NATIVE_BAND_COMPUTED' and source['rows']==41 and source['custom_propagation_calls']==0
    assert source['pathsolver_calls']==41*257*3
    runtime=json.loads((a.raw/'RUNTIME.json').read_text())
    invocation=json.loads((a.root/'NATIVE_INVOCATION.json').read_text())
    runner=ROOT/'scripts/g2_completion/sionna_native_runtime.py'
    assert runtime['runner_sha256']==invocation['runner_sha256']==file_sha(runner)
    assert runtime['versions']['sionna-rt']=='2.0.1'
    inputs=json.loads((a.root/'INPUT_MANIFEST.json').read_text())['inputs']
    # Preparation source receipt is historical; pin the actually executed source separately.
    inputs={p:h for p,h in inputs.items() if not p.endswith('sionna_native_runtime.py')}
    for p,h in inputs.items():assert file_sha(p)==h, 'CHANGED_CANONICAL_INPUT'
    records=[];bound=[];max_sum_error=0.
    for row in c['rows']:
        key=row['link_id'];p=a.raw/(key+'_NATIVE.npz');meta=a.raw/(key+'_RESULT.json')
        inputs[str(p.resolve())]=file_sha(p);inputs[str(meta.resolve())]=file_sha(meta)
        detail=json.loads(meta.read_text());assert detail['tx']==row['tx'] and detail['rx']==row['rx']
        with np.load(p) as z:
            f=z['frequencies_hz'];original=z['H_arms'];ha=np.zeros_like(original,dtype=np.complex128)
            np.testing.assert_array_equal(f,6250400000.+1950000.*np.arange(257))
            np.testing.assert_array_equal(z['tx_m'],row['tx']);np.testing.assert_array_equal(z['rx_m'],row['rx'])
            for fi in range(257):
                for ai,arm in enumerate(ARMS):
                    coef=z[f'{arm}_a_{fi:03d}'].astype(np.complex128);tau=z[f'{arm}_tau_{fi:03d}']
                    expected=sum_native_paths(coef,tau,f[fi]);ha[fi,ai]=expected
                    # The original Linux array used complex64 exp. Bound the
                    # phase arithmetic by float32 eps times |omega*tau|,
                    # weighted by each path amplitude (safe also at nulls).
                    phase_abs=abs(2*np.pi*float(f[fi])*tau.astype(np.float64))
                    roundoff=8*np.finfo(np.float32).eps*np.sum(abs(coef)*(1+phase_abs)[None,None,:],axis=-1)
                    assert np.all(abs(original[fi,ai]-expected)<=roundoff+np.finfo(float).tiny)
                    max_sum_error=max(max_sum_error,float(np.max(abs(original[fi,ai]-expected))))
            h=np.zeros((257,6,6),complex)
            for ai,ix in enumerate(ARMS.values()):
                for ri,r in enumerate(ix):
                    for ti,t in enumerate(ix):h[:,r,t]=ha[:,ai,ri,ti]
            arrays,detections=observe(h,f,row,c['noise'],c['detector'])
            arrays.update(H_arms=ha,arms=np.array(list(ARMS)),tx_m=z['tx_m'],rx_m=z['rx_m'],ports=z['ports'])
            path_metrics={}
            for arm in ARMS:
                interactions=z[f'{arm}_interactions_128'].reshape(3,-1)
                valid=z[f'{arm}_valid_128'].reshape(-1)
                reflected=np.any((interactions & 1)!=0,axis=0)
                transmitted=np.any((interactions & 4)!=0,axis=0)
                powers=np.sum(abs(z[f'{arm}_a_128'].astype(np.complex128))**2,axis=(0,1))
                total=float(powers.sum())
                path_metrics[arm]=dict(native_los_present=bool(np.any(np.all(interactions==0,axis=0)&valid)),
                    paths_with_surface_reflection=int(np.sum(reflected&valid)),
                    paths_with_slab_transmission=int(np.sum(transmitted&valid)),
                    incoherent_reflection_path_power_fraction=float(powers[reflected].sum()/total) if total else None)
        np.savez_compressed(out/(key+'_CHANNEL.npz'),**arrays)
        detail.update(backend='Sionna RT 2.0.1',detections=detections,
            native_midband_path_metrics=path_metrics,
            native_paths_file=str(p.resolve()),native_paths_sha256=inputs[str(p.resolve())],
            taxonomy={'RD_LoS':None,'HB_near_delay':None,'HB_prior':None,'status':'DEFERRED_BY_USER'},
            path_index_policy='frequency-local indices; do not assume index identity across bins')
        write(out/(key+'_RESULT.json'),detail);records.append(detail);bound.append(row)
    write(out/'PRODUCTION_INPUTS.json',bound)
    write(out/'MODEL_CONTRACT.json',{k:c[k] for k in ['backend','model','solver','ideal_material_mapping','exclusions','search_completeness_claim','classification']})
    status=dict(status='NATIVE_PIPELINE_COMPUTED',backend='Sionna RT 2.0.1',rows=len(records),frequency_bins=257,
        ports=6,cir_taps=1028,pathsolver_calls=source['pathsolver_calls'],custom_propagation_calls=0,
        RD_HB='DEFERRED_BY_USER',search_completeness_established=False,final_seal=False,G3_run=False)
    write(out/'STATUS.json',status)
    for p in [runner,a.root/'CONFIG.json',a.root/'NATIVE_INVOCATION.json',a.raw/'RUNTIME.json',a.raw/'STATUS.json',Path(__file__),ROOT/'rt_cp_uwb_py/g2_native_channel.py',ROOT/'rt_cp_uwb_py/g2_scoped_channel.py',ROOT/'rt_cp_uwb_py/rf_channel_closure.py',ROOT/'rt_cp_uwb_py/features.py',ROOT/'rt_cp_uwb_py/matlab_rng.py']:
        inputs[str(p.resolve())]=file_sha(p)
    write(out/'MANIFEST.json',dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,config_sha256=file_sha(a.root/'CONFIG.json'),inputs=inputs,outputs={p.name:file_sha(p) for p in out.iterdir() if p.is_file()}))
    consumed=[]
    for row in bound:
        got=load_native_link(out,row['link_id']);data=got['channel']
        for ai,(arm,ix) in enumerate(ARMS.items()):
            np.testing.assert_array_equal(data[arm+'_H'],data['H_arms'][:,ai])
            np.testing.assert_array_equal(data[arm+'_H_noisy'],data[arm+'_H']+data['noise_H'])
            taps=np.array([0,1,128,514,1027]);phase=np.exp(2j*np.pi*np.outer(taps,np.arange(257))/1028)
            for suffix,spectrum in [('',data[arm+'_H_noisy']),('_clean',data[arm+'_H'])]:
                expected=257/1028*np.einsum('tk,kij->tij',phase,np.hanning(257)[:,None,None]*spectrum)
                bound_error=128*np.finfo(float).eps*(257/1028)*np.sum(abs(np.hanning(257)[:,None,None]*spectrum),axis=0)+1e-12*abs(expected)
                assert np.all(abs(data[arm+'_CIR'+suffix][taps]-expected)<=bound_error)
        consumed.append(dict(link_id=row['link_id'],tx=row['tx'],rx=row['rx'],status='PASS',backend=status['backend'],
                             channel_file=str((out/(row['link_id']+'_CHANNEL.npz')).resolve())))
    write(a.root/'CONSUMER_RECEIPT.json',dict(status='NATIVE_PIPELINE_PASS',rows=consumed,H_sum_check='PASS',CIR_direct_sum_check='PASS',noise_pairing_check='PASS'))
    write(a.root/'PHASE_PRECISION_RECEIPT.json',dict(original_bitwise_cross_platform_check='FAILED_AND_PRESERVED',
        fix='reconstruct H from unchanged Sionna a and tau with explicit complex128 carrier phase',
        max_absolute_change_from_native_saved_sum=max_sum_error,
        original_float32_roundoff_bound_check='PASS',new_rf_calls=0))
    print(json.dumps(status))


if __name__=='__main__':main()
