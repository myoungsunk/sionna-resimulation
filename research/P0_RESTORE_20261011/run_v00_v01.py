#!/usr/bin/env python3
"""P0 V00/V01: immutable input audit, corrected 128-seed replay, receiver parity."""
from __future__ import annotations
import argparse,importlib.util,json,sys,urllib.request
from pathlib import Path
import numpy as np,pandas as pd
from rf_pose_index import PoseIndex,sha256,regression_tests
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff'
B=ROOT/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
T=ROOT/'results/DRIVE_SIM_20261007/S1/routes'
CASES=['R2_aA_m0','R2_aA_m45','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0']
ORIGINAL_REF='cd8f3ef90b9307ee079b4ec7a0cef552b4644c10'

def module_at(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False))

def v00(out,nseed):
    tests=regression_tests();all_receipts=[];mapping={};hashes={}
    fq=B/'freqs_hz.npy';fsha=sha256(fq)
    for case in CASES:
        sample=json.loads((B/case/'SAMPLES.json').read_text())
        hpath=B/'FULL_RF'/f'H_{case}.npy';h=np.load(hpath,mmap_mode='r')
        Hsha=sha256(hpath);hashes[case]=Hsha
        index=PoseIndex(sample,len(h))
        for policy in ['Tnone','T10']:
            timeline=pd.read_csv(T/f'timeline_{case[:2]}_{policy}.csv')
            row,rec=index.timeline(timeline,case,Hsha,fsha)
            rec['policy']=policy;all_receipts.append(rec)
            if case=='R2_aA_m0' and policy=='T10':mapping['rows']=row;mapping['receipts']=rec
    joined=pd.concat(all_receipts,ignore_index=True);joined.to_csv(out/'ROW_POSE_PARITY.csv.gz',index=False)
    legacy_path=ROOT/'research/P0_RESTORE_20261011/legacy_cross_time_original.py'
    original_url=f'https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/{ORIGINAL_REF}/research/HEADING_RELIABILITY_20261010/run_pose_rf_cross_time_mc_existing_H.py'
    if not legacy_path.exists():
        legacy_path.write_bytes(urllib.request.urlopen(original_url,timeout=90).read())
    original=legacy_path.read_text()
    marker='obs=O.observe(np.asarray(H[:last+1]),freq,nvar,rng,tx=0)'
    assert original.count(marker)==1,'Original script changed: refuse guessed patch'
    fixed=original.replace(marker,'obs=O.observe(np.asarray(H[RF_BANK_ROWS[:last+1]]),freq,nvar,rng,tx=0)')
    fixed_path=legacy_path.with_name('corrected_cross_time_replay.py');fixed_path.write_text(fixed)
    records=[];summaries={}
    for name,path in [('FAULTY_QUARANTINED',legacy_path),('POSE_ID_FIXED',fixed_path)]:
        mod=module_at('mc_'+name,path)
        mod.RF_BANK_ROWS=mapping['rows']
        ctx=mod.basic_context();snapshots=[];predictions=[]
        for seed in range(nseed):
            snaps,pred=mod.seed_run(seed,ctx);snapshots.append(snaps);predictions.append(pred)
        errors=np.asarray([[x['e'] for x in s] for s in snapshots])
        Ps=np.asarray([[x['P'] for x in s] for s in snapshots])
        radio=np.asarray([[[x['vr'],x['vs']] for x in s] for s in snapshots])
        pairs=[(i,j) for i in range(3) for j in range(i,3)]
        np.savez_compressed(out/f'{name}_128SEED_TENSORS.npz',errors=errors,P6=Ps,rf_residual=radio,
            predicted_Pij=np.asarray([[p[f'{i}:{j}'] for i,j in pairs] for p in predictions]),
            pair_order=np.asarray(pairs),times=ctx[1][list(ctx[5])],RF_pose_ids=np.asarray(ctx[0].iloc[list(ctx[5])].pose_id))
        for t in range(3):
            ee=errors[:,t,:3];P=Ps[:,t,:3,:3]
            nees=np.einsum('ni,ni->n',ee,np.linalg.solve(P,ee[...,None])[...,0])
            records.append(dict(mode=name,snapshot=t,time_s=float(ctx[1][ctx[5][t]]),
                requested_pose_id=int(ctx[0].iloc[ctx[5][t]].pose_id),n_seeds=nseed,
                mean_pose_nees=float(nees.mean()),pose95_coverage=float(np.mean(nees<=7.814727903251179)),
                heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(ee[:,2]**2)))),
                heading_pred_var_rad2=float(P[:,2,2].mean()),heading_mse_rad2=float(np.mean(ee[:,2]**2)),
                position_rmse_m=float(np.sqrt(np.mean(np.sum(ee[:,:2]**2,axis=1)))),
                range_residual_mean_m=float(radio[:,t,0].mean()),s_residual_mean=float(radio[:,t,1].mean())))
        summaries[name]={'seed_count':nseed,'input_correct':name=='POSE_ID_FIXED'}
        print('V00_FINISHED',name,nseed,flush=True)
    metrics=pd.DataFrame(records);metrics.to_csv(out/'CORRECTED_VS_QUARANTINED_MC.csv',index=False)
    change=mapping['receipts'].iloc[:91].copy();change['old_H_row']=change.timeline_k
    samples=json.loads((B/'R2_aA_m0/SAMPLES.json').read_text())
    change['old_H_pose_id']=[int(samples[k]['pose_id']) for k in change.timeline_k]
    change['old_wrong_pose']=change.old_H_pose_id!=change.requested_pose_id
    change.to_csv(out/'FULL_USED_HISTORY_INDEX_CORRECTION.csv',index=False)
    dump(out/'HASH_MANIFEST.json',{'H_sha256':hashes,'frequency_sha256':fsha,
        'original_MC_sha256':sha256(legacy_path),'corrected_MC_sha256':sha256(fixed_path),
        'original_commit':ORIGINAL_REF,'mapping_tests':tests})
    dump(out/'STATUS.json',{'id':'V00','execution':'COMPLETE','mapping_gate':'PASS',
        'receipt_rows':len(joined),'regression_count':len(tests),'seeds_each_mode':nseed,
        'wrong_rows_in_original_first91':int(change.old_wrong_pose.sum()),
        'covariance_scientific_PASS':False,'reason':'Input alignment restored; modeled covariance validation is separate.',
        'metrics':metrics.to_dict('records')})
    (out/'CORRECTION_NOTICE_KO.md').write_text('# V00 정정\n\n원본 128-seed 결과는 QUARANTINED_REFERENCE_ONLY로 보존했습니다. 동일 seed/관측기/필터에서 H 접근만 명시적 pose_id lookup으로 교체하여 첫 프로브부터 전체 이력을 재실행했습니다. 반복 pose는 허용하고 RF packet ID는 시간행별 고유합니다. 수정된 MC의 statistical consistency가 자동 PASS가 되는 것은 아닙니다.\n')
    # Small complete provenance/code bundle, excluding binary RF input.
    for p in (legacy_path,fixed_path,Path(__file__),Path(__file__).with_name('rf_pose_index.py')):
        (out/p.name).write_bytes(p.read_bytes())

def v01(out):
    old=module_at('old_observer',RUN/'source/src/qclean_uwb/drivesim/observation.py')
    new=module_at('native_observer',ROOT/'src/qclean_uwb/drivesim/observation.py')
    fq=np.load(B/'freqs_hz.npy');df=np.diff(fq);assert np.allclose(df,df[0],rtol=0,atol=1e-5)
    records=[]
    for case in CASES:
        for family,path in [('FULL_LEGACY',B/'FULL_RF'/f'H_{case}.npy'),('LOS_ARCHIVED',B/f'H_LoS_{case}.npy')]:
            h=np.load(path,mmap_mode='r');h=np.asarray(h[np.unique(np.linspace(0,len(h)-1,min(len(h),96)).astype(int))])
            for snr in [None,30.,10.]:
                nv=None if snr is None else old.noise_var_from_snr(snr)
                r1=old.observe(h,fq,nv,np.random.default_rng(7),return_h=True)
                r2=new.observe(h,fq,nv,np.random.default_rng(7),return_h=True)
                # Independent explicit DFT-chain recreation, not using observer helpers.
                window=(1-np.cos(2*np.pi*np.arange(len(fq))/(len(fq)-1)))/2
                hh=r1['h_noisy']*window[None,:,None]
                C=np.fft.ifft(hh,n=4*len(fq),axis=1)*len(fq)
                amp=np.abs(C);port=amp.max(axis=1).argmax(axis=1)
                strongest=amp[np.arange(len(h))[:,None],np.arange(C.shape[1])[None,:],port[:,None]]
                tap=(strongest>=.3*strongest.max(axis=1)[:,None]).argmax(axis=1)
                power=np.abs(C[np.arange(len(h)),tap])**2
                independent_s=(power[:,0]-power[:,1])/power.sum(axis=1)
                detected=r1['detected']
                assert np.array_equal(tap,r1['index'])
                assert np.array_equal(r1['index'],r2['index']) and np.array_equal(detected,r2['detected'])
                err=float(np.nanmax(abs(r1['s'][detected]-independent_s[detected]))) if detected.any() else 0.
                brancherr=float(np.nanmax(abs(r1['s'][detected]-r2['s'][detected]))) if detected.any() else 0.
                assert err<1e-12 and brancherr<1e-12
                records.append(dict(case=case,family=family,snr_db=snr,n=len(h),n_detected=int(detected.sum()),
                    s_independent_max_abs=err,s_branch_max_abs=brancherr,FP_tap_exact=True))
    pd.DataFrame(records).to_csv(out/'CROSS_BRANCH_OBSERVER_PARITY.csv',index=False)
    step=299792458./(4*len(fq)*df[0]);oldstep=299792458./(1028*1.953125e6)
    contract={'version':'FP_COMMON_RX_AMP30_HANN_257_PAD4_V1',
       'frequency_sha256':sha256(B/'freqs_hz.npy'),'n_frequency':len(fq),'frequency_step_hz':float(df[0]),
       'FFT_points':4*len(fq),'Hann':'symmetric 0.5*(1-cos(2pi n/(N-1)))',
       'IFFT_multiplier':len(fq),'threshold_domain':'amplitude','leading_edge_fraction':.3,
       'port_selection':'max peak amplitude over RX; same first crossing tap for both LP',
       'range_step_m':float(step),'range_quant_var_m2':float(step**2/12),
       'legacy_filter_range_step_m':float(oldstep),'legacy_filter_quant_var_m2':float(oldstep**2/12),
       'primary_early_gate_version':'COMMON_FP_START_LENGTH_4_8_16_TAPS_V1',
       'legacy_early_gate_version':'COMMON_FP_START_LENGTH_5_9_17_TAPS_V0',
       'noise_definition':'complex per-bin power variance; real and imaginary each var/2',
       'hardware_amplitude_CIR_support':'UNKNOWN','hardware_delay_ns':None,
       'legacy_detector_offset_m':-.531598390625,
       'native_calibration_offsets_m':{'mount0':-.5124272934,'mount45':-.5327236346},
       'offsets_interchangeable':False,'source_family_gate':'NOT_VALIDATED_12CASE_FULL_NATIVE_VS_LEGACY'}
    dump(out/'OBSERVATION_CONTRACT.json',contract)
    dump(out/'STATUS.json',{'id':'V01','execution':'COMPLETE_WITH_LIMIT',
        'same_input_observer_gate':'PASS','tests':len(records),'independent_FP_recalculation':'PASS',
        'source_family_equivalence':'NOT_VALIDATED','full_P0_PASS':False})
    print('V01_CONTRACT',json.dumps(contract),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('task',choices=['V00','V01']);p.add_argument('--out',type=Path,required=True);p.add_argument('--seeds',type=int,default=128)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    try:(v00(a.out,a.seeds) if a.task=='V00' else v01(a.out))
    except Exception as e:
        dump(a.out/'EXECUTION_FAILURE.json',{'exception':type(e).__name__,'message':str(e)});raise
