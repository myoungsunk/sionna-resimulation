"""SM0: gated native ray capture; no derived FFT or attribution here.

The original scene, FFD adapter and solver configuration are imported verbatim.
Only an explicit hash-bound GO file permits a PathSolver invocation.
"""
import argparse
import csv
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
from native_math import independent_sum, vector_fields, label_chain, grouped_spectra, errors
from precision_qa import evaluate_precision, PRECISION_CONTRACT, ARCHIVE_LOS_MODEL, COHERENT_SUM_MODEL

HERE = Path(__file__).resolve().parent
BLOCK = 'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
CFG = 'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json'
BANK = 'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json'
PIN = '21734694'
THRESHOLDS = dict(reconstruction_relative_l2=1e-8, reconstruction_max_normalized=1e-8,
                  archive_full_relative_l2=1e-3, archive_los_relative_l2=1e-5)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):h.update(block)
    return h.hexdigest()


def put(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')


def lock_inputs(source, bank):
    source = Path(source); bank = Path(bank)
    hashes = json.loads((source/'SOURCE_HASHES.json').read_text())
    for name, expected in hashes.items():
        if sha(source/name) != expected:raise ValueError('source hash '+name)
    expected = json.loads((source/BANK).read_text())['npz_sha256']
    banks = {n: sha(bank/n) for n in ('LP_plus45_bank.npz','LP_minus45_bank.npz')}
    if any(banks[n] != expected[n] for n in banks):raise ValueError('bank hash')
    return dict(source_sha256=hashes, source_hash_manifest_sha256=sha(source/'SOURCE_HASHES.json'),
                bank_sha256=banks, source_revision=PIN,
                code_sha256={n:sha(HERE/n) for n in ('producer.py','native_math.py','precision_qa.py','diagnostics.py','postprocess.py')},
                precision_contract=PRECISION_CONTRACT, archive_los_reference=ARCHIVE_LOS_MODEL,
                coherent_sum_reference=COHERENT_SUM_MODEL,
                runtime_lock_sha256=sha(HERE/'RUNTIME_LOCK.json'),
                thresholds=THRESHOLDS,
                primary_reference='F64 independent scalar path sum for coherent reconstruction; original complex64 expression for archived LoS',
                grouping='exact canonical JSON ordered semantic object/type chain; no one-to-one ray tracking')


def authorize(go_path, lock, case, pid):
    go=json.loads(Path(go_path).read_text(encoding='utf-8-sig'))
    if go.get('schema')!='SM0_GO_V2' or go.get('decision')!='GO':raise ValueError('no approved V2 GO')
    if dict(case=case,pose_id=pid) not in go.get('authorized',[]):raise ValueError('unauthorized pose')
    for key in ('code_sha256','source_sha256','bank_sha256','thresholds',
                'primary_reference','runtime_lock_sha256','precision_contract',
                'archive_los_reference','coherent_sum_reference'):
        if go.get(key)!=lock[key]:raise ValueError('GO binding '+key)
    return sha(go_path)


def runtime_snapshot():
    """Actual runtime state, checked against prospectively frozen RUNTIME_LOCK."""
    llvm=Path(os.environ['DRJIT_LIBLLVM_PATH'])
    env_keys=('PYTHONHOME','LD_LIBRARY_PATH','PYTHONPATH','DRJIT_LIBLLVM_PATH',
              'OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')
    return dict(python=sys.version,executable=sys.executable,platform=platform.platform(),
                cpu_model=[s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')][:1],
                versions={n:importlib.metadata.version(n) for n in ('numpy','scipy','sionna-rt','mitsuba','drjit')},
                all_distributions={d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[os.environ['PYTHONPATH']])},
                llvm_path=str(llvm),llvm_sha256=sha(llvm),environment={k:os.environ[k] for k in env_keys})


def validate_runtime(lock):
    path=HERE/'RUNTIME_LOCK.json'
    if sha(path)!=lock['runtime_lock_sha256']:raise ValueError('runtime manifest hash changed')
    expected=json.loads(path.read_text());actual=runtime_snapshot()
    for key,value in actual.items():
        if expected.get(key)!=value:raise ValueError('frozen runtime mismatch '+key)
    return actual


def select_pose(source, case, pid):
    d=Path(source)/BLOCK
    poses=json.loads((d/case/'SAMPLES.json').read_text())
    selected=[v for v in poses if int(v['pose_id'])==pid]
    if len(selected)!=1 or int(poses[pid]['pose_id'])!=pid:raise ValueError('sample identity/index')
    pose=selected[0]
    with (d/'INPUTS'/('timeline_'+case.split('_')[0]+'_Tnone.csv')).open() as f:
        rows=[r for r in csv.DictReader(f) if int(r['pose_id'])==pid]
    if len(rows)!=1:raise ValueError('timeline identity')
    timeline=rows[0]
    if any(abs(float(timeline[k])-float(pose[k]))>6e-7 for k in ('x','y','yaw_body_deg')):
        raise ValueError('timeline/sample geometry')
    return dict(pose_id=pid,t=float(timeline['t_s']),x=float(pose['x']),y=float(pose['y']),
                yaw_body_deg=float(pose['yaw_body_deg']),phase=timeline['phase'])


def extract(paths, frequency, lookup, direct_delay):
    # Original native dtypes and coefficients are preserved before any conversion.
    tau=np.asarray(paths.tau).reshape(-1).copy(); n=len(tau)
    if n==0:raise ValueError('no paths')
    a=(np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])).reshape(2,2,n).copy()
    obj=np.asarray(paths.objects).reshape(-1,n).T.copy()
    inter=np.asarray(paths.interactions).reshape(-1,n).T.copy()
    primitives=np.asarray(paths.primitives).reshape(-1,n).T.copy()
    vertices=np.asarray(paths.vertices).reshape(-1,n,3).transpose(1,0,2).copy()
    valid=np.asarray(paths.valid).reshape(-1,n).T.copy()
    valid_any=valid.any(axis=1)
    if np.any(abs(a[:,:,~valid_any])>0):raise ValueError('nonzero invalid path')
    if not np.isfinite(tau).all() or not np.isfinite(a).all():raise ValueError('nonfinite raw coefficients')
    labels=[label_chain(obj[j],inter[j],lookup,bool(valid_any[j])) for j in range(n)]
    direct=np.flatnonzero(np.asarray(labels)=='DIRECT')
    if len(direct)!=1 or abs(float(tau[direct[0]])-direct_delay)>1e-12:
        raise ValueError('DIRECT identity/delay')
    fields=vector_fields(a,tau,frequency)
    # The exact expression and precision path used by original compute.py.
    original=a[:,0,:]*np.exp(-2j*np.pi*np.float64(frequency)*tau)[None,:]
    return dict(a=a.transpose(2,0,1),tau=tau,objects=obj,interactions=inter,
                primitives=primitives,vertices=vertices,valid=valid,
                theta_t=np.asarray(paths.theta_t).reshape(-1,n).T.copy(),
                phi_t=np.asarray(paths.phi_t).reshape(-1,n).T.copy(),
                theta_r=np.asarray(paths.theta_r).reshape(-1,n).T.copy(),
                phi_r=np.asarray(paths.phi_r).reshape(-1,n).T.copy(),
                source_index=np.arange(n,dtype=np.int32),labels=labels,fields=fields,
                original_field=original.T.copy(),original_sum=original.sum(axis=1),
                independent_sum=independent_sum(a,tau,frequency),direct_index=int(direct[0]))


def load_diagnostics(path):
    """Mother's diagnostics.evaluate arguments after raw capture and QA."""
    with np.load(path,allow_pickle=False) as z:
        return dict(freq=z['frequencies_hz'], fields=z['group_fields'],
                    labels=z['group_labels'].tolist(),direct=int(z['direct_group']),
                    native_full=z['native_f64'],archive_full=z['archive_full'],archive_los=z['archive_los'])


def run(source, bank, output, case, pid, go):
    source=Path(source);bank=Path(bank);output=Path(output)
    lock=lock_inputs(source,bank);go_sha=authorize(go,lock,case,pid)
    runtime=validate_runtime(lock)
    if output.exists():raise ValueError('preserve previous evidence; new output directory required')
    pose=select_pose(source,case,pid)
    output.mkdir(parents=True);(output/'bins').mkdir()
    receipt=dict(status='RUNNING',pose=pose,case=case,original_not_counterfactual=True,
                 lock=lock,go_sha256=go_sha,runtime_lock_sha256=lock['runtime_lock_sha256'],validated_runtime=runtime,
                 command=sys.argv,start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    put(output/'MANIFEST.json',receipt)
    try:
        # No simulator imported, scene constructed or path traced before authorization.
        sys.path[:0]=[str(source/'scripts'),str(source/'src')]
        import corridor_sionna_run as C
        import mitsuba as mi
        import sionna.rt as rt
        import drjit as dr
        versions={v:importlib.metadata.version(v) for v in ('numpy','scipy','sionna-rt','mitsuba','drjit')}
        expected=dict(numpy='1.26.4',scipy='1.14.1',**{'sionna-rt':'2.0.1','mitsuba':'3.8.0','drjit':'1.3.1'})
        if versions!=expected or mi.variant()!='llvm_ad_mono_polarized':raise ValueError('runtime mismatch')
        if sys.version_info[:2]!=(3,11):raise ValueError('Python minor mismatch')
        dr.set_thread_count(1)
        if dr.thread_count()!=1:raise ValueError('DrJit thread count mismatch')
        receipt['environment']=dict(versions=versions,python=sys.version,platform=platform.platform(),
                                    cpu=platform.processor(),variant=mi.variant(),drjit_threads=1,
                                    llvm_path=os.environ.get('DRJIT_LIBLLVM_PATH'),
                                    threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
        C.BANK_DIR=bank;banks=C.load_banks();freq=np.asarray(banks[0]['freqs_hz'],float)
        archived_freq=np.load(source/BLOCK/'freqs_hz.npy')
        if len(freq)!=257 or not np.array_equal(freq,archived_freq):raise ValueError('frequency grid')
        cfg=json.loads((source/CFG).read_text())['solver']
        if cfg['max_depth']!=3 or cfg['seed']!=20260924:raise ValueError('solver contract')
        setup=C.CorridorSetup(anchor_x_m=10.)
        if not all(v['passed'] for v in setup.validate()):raise ValueError('setup validation')
        scene,bindings=C.build_scene(setup,output/'scene')
        manifest=json.loads((source/BLOCK/case/'MANIFEST.json').read_text())
        expected_bindings={v['object']:v['ply_sha256'] for v in manifest['material_bindings']}
        if {v['object']:v['ply_sha256'] for v in bindings}!=expected_bindings:raise ValueError('scene PLY mismatch')
        scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=C.euler(C.ANCHOR_ROTATION)))
        rxpos=setup.robot_position(pose['x'],pose['y'])
        scene.add(rt.Receiver('rx',position=rxpos.tolist(),orientation=C.euler(setup.robot_rotation(pose['yaw_body_deg']))))
        lookup={int(v.object_id):key for key,v in scene.objects.items()}
        tx,rx=C.make_ports(banks);solver=rt.PathSolver();bins=[]
        receipt.update(solver=cfg,scene_bindings=bindings,object_lookup=lookup,tx_position=setup.anchor_position.tolist(),rx_position=rxpos.tolist(),
                       selected_tx='LP_plus45 column0',rx_order=['LP_plus45','LP_minus45'],frequency_sha256=sha(source/BLOCK/'freqs_hz.npy'))
        put(output/'MANIFEST.json',receipt)
        started=time.perf_counter()
        for fi,frequency in enumerate(freq):
            C.set_bin(scene,banks,tx,rx,fi,float(frequency))
            paths=solver(scene,**cfg)
            row=extract(paths,float(frequency),lookup,float(np.linalg.norm(setup.anchor_position-rxpos)/299792458.))
            # Independent native API output, kept separately; never the F64 QA reference.
            row['cfr32']=np.asarray(paths.cfr(frequencies=mi.Float([0.]),normalize_delays=False,normalize=False,out_type='numpy')).reshape(2,2)[:,0]
            np.savez_compressed(output/'bins'/f'{fi:03d}.npz',**row,frequency_hz=np.asarray(frequency))
            bins.append(row)
            if fi%32==0:print('SM0_BIN',case,pid,fi,len(row['tau']),flush=True)
        grouped=grouped_spectra(bins)
        arrays={k:np.concatenate([v[k] for v in bins],axis=0) for k in ('a','tau','objects','interactions','primitives','vertices','valid','theta_t','phi_t','theta_r','phi_r','source_index','fields','original_field')}
        arrays.update(grouped,offsets=np.r_[0,np.cumsum([len(v['tau']) for v in bins])],
                      frequencies_hz=freq,direct_source_index=np.asarray([v['direct_index'] for v in bins],np.int32),
                      native_f64=np.asarray([v['independent_sum'] for v in bins]),
                      native_original32=np.asarray([v['original_sum'] for v in bins]),native_cfr32=np.asarray([v['cfr32'] for v in bins]))
        arrays['archive_full']=np.asarray(np.load(source/BLOCK/'FULL_RF'/('H_'+case+'.npy'),mmap_mode='r')[pid,:,:,0])
        arrays['archive_los']=np.asarray(np.load(source/BLOCK/('H_LoS_'+case+'.npy'),mmap_mode='r')[pid,:,:,0])
        if arrays['archive_full'].shape!=(257,2) or arrays['archive_los'].shape!=(257,2):raise ValueError('archive axes')
        arrays['direct_f64']=arrays['group_fields'][int(arrays['direct_group'])]
        precision=evaluate_precision(arrays,THRESHOLDS)
        # Keep both precision paths inspectable. The legacy expression is the
        # archive LoS comparator; F64 remains the independent coherent sum.
        arrays['direct_legacy32']=precision['direct_legacy32']
        np.savez_compressed(output/'RAW.npz',**arrays)
        reconstruction=precision['reconstruction_primary_f64']
        ef=precision['archive_full_primary_f64']
        el=precision['archive_los_primary_legacy32']
        receipt.update(raw_sha256=sha(output/'RAW.npz'),elapsed_s=time.perf_counter()-started,
                       array_schema={key:dict(shape=list(value.shape),dtype=str(value.dtype)) for key,value in arrays.items()},
                       reconstruction=reconstruction,archive_full_error=ef,archive_los_error=el,
                       precision_contract=PRECISION_CONTRACT,
                       archive_los_reference=ARCHIVE_LOS_MODEL,coherent_sum_reference=COHERENT_SUM_MODEL,
                       archive_los_error_f64_diagnostic=precision['archive_los_diagnostic_f64'],
                       archive_full_error_legacy32_diagnostic=precision['archive_full_diagnostic_legacy32'],
                       original32_vs_f64=errors(arrays['native_original32'],arrays['native_f64']),
                       cfr32_vs_f64=errors(arrays['native_cfr32'],arrays['native_f64']),
                       groups=len(grouped['group_labels']),paths_per_bin=[len(v['tau']) for v in bins],
                       multiple_same_chain_bins=int((grouped['group_count']>1).sum()),
                       note='Group identity is semantic chain. Per-bin ray IDs are not tracked one-to-one across frequencies.')
        passed=precision['pass_all']
        receipt['status']='PASS' if passed else 'STOP_MISMATCH'
        if not passed:raise ValueError('SM0 first mismatch; retained raw; no expansion')
    except BaseException as exc:
        if receipt['status']!='STOP_MISMATCH':receipt['status']='STOP_ERROR'
        receipt['error']=repr(exc)
        raise
    finally:
        receipt['end_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        put(output/'MANIFEST.json',receipt)
        put(output/'ARTIFACT_HASHES.json',{str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='ARTIFACT_HASHES.json'})
    print('SM0_RESULT',json.dumps(dict(status=receipt['status'],case=case,pose_id=pid,
                      reconstruction=receipt['reconstruction'],full=receipt['archive_full_error'],
                      los_legacy32=receipt['archive_los_error'],
                      los_f64_diagnostic=receipt['archive_los_error_f64_diagnostic'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--bank',type=Path,required=True)
    p.add_argument('--lock-only',type=Path);p.add_argument('--out',type=Path);p.add_argument('--go',type=Path)
    p.add_argument('--case',choices=['R2_aB_m0','R4_aB_m0','R5_aB_m0'],default='R4_aB_m0');p.add_argument('--pose-id',type=int,default=194)
    a=p.parse_args()
    if a.lock_only:
        if a.lock_only.exists():raise ValueError('preserve existing lock')
        put(a.lock_only,lock_inputs(a.source,a.bank))
    else:
        if not a.out or not a.go:p.error('--out and --go required for native solve')
        run(a.source,a.bank,a.out,a.case,a.pose_id,a.go)
