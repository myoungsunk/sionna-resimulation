from pathlib import Path
import sys,json,importlib.util,hashlib,math
import numpy as np,pandas as pd
J=Path('/job');src=J/'source';out=J/'REPLAY_ATTEMPT2';out.mkdir(exist_ok=False)
sys.path[:0]=[str(src/'src')]
spec=importlib.util.spec_from_file_location('a23',src/'scripts/drive_sim/structured_noise_control.py'); m=importlib.util.module_from_spec(spec);sys.modules['a23']=m;spec.loader.exec_module(m)
meta=json.loads((J/'SOURCE_REVISION.json').read_text());m.git_info=lambda:dict(head=meta['head'],branch=meta['branch'],dirty_files=[],runtime_git_available=False,provenance_method=meta['provenance_method'],archive_sha256=meta['archive_sha256'],local_checkout_dirty_files=meta['dirty_files'])
def run(a):
 m.resolve_inputs(a);m.setup(a); man=m.base_manifest(a,a.cases,a.mounts,'supplement')
 check=json.loads(Path('/previous/OUTPUT/A0_CHECK.json').read_text())
 req=m.requested_keys(a.cases,a.mounts,a.drifts,a.seeds,a.seed0)
 keys=[tuple(r) for r in req.itertuples(index=False,name=None)]
 ok,why=m.a0_gate(check,man,keys);assert ok,why
 (out/'A0_GATE_RECHECK.json').write_text(json.dumps({'passed':ok,'reason':why,'fingerprint':man['fingerprint']},indent=2))
 m.init_worker(vars(a));arms=json.loads((J/'PLAN.json').read_text())['replay']['arms']
 old=pd.concat([pd.read_csv(Path('/previous/OUTPUT')/n) for n in ['A0_ARMS.csv','ARMS_controls.csv','ARMS_q1.csv','ARMS_q2.csv','ARMS_joint.csv']])
 diffs=[];rows=[];units=[];blockrecords=[];arraymax={}
 original_block=m.block_index;capture={}
 def capture_block(n,length,length_series,rng):
  idx=original_block(n,length,length_series,rng);capture.update(index=idx.copy(),n=n,length=length,length_series=length_series);return idx
 m.block_index=capture_block
 for arm in arms:
  for drift in a.drifts:
   for seed in range(5):
    capture.clear();rr,uu=m.work(('R2A',0.,arm,seed,drift));assert len(rr)==1 and not rr[0].get('error'),rr
    r=rr[0];rows.extend(rr);units.append(uu)
    prev=old[(old.arm==arm)&(old.seed==seed)&(old.drift==drift)]
    assert len(prev)==1
    d={k:abs(float(r[k])-float(prev.iloc[0][k])) for k in ['heading_rmse_deg','pos_rmse_m','nees_mean']}
    assert max(d.values())<=1e-9,(arm,seed,drift,d);diffs.append(dict(arm=arm,seed=seed,drift=drift,**d))
    p=out/'TRACES'/f'R2A_m0_{arm}_s{seed}_d{drift}.npz';z=np.load(p)
    if seed<2:
     oldz=np.load(Path('/previous/OUTPUT/TRACES')/p.name)
     for k in oldz.files:
      assert np.array_equal(oldz[k],z[k],equal_nan=True),(p.name,k)
    if arm=='J3_joint_block':
     assert 'index' in capture
     data={k:z[k] for k in z.files};data.update(block_indices=capture['index'],block_start_positions=np.arange(0,capture['n'],capture['length']),block_start_indices=capture['index'][::capture['length']],block_length=capture['length'],residual_series_length=capture['length_series'])
     z.close();np.savez_compressed(p,**data)
     # Independent RNG replay, distinct implementation; all consumed indices must match.
     rng=np.random.default_rng([seed,drift,107]);starts=rng.integers(0,capture['length_series'],math.ceil(capture['n']/capture['length']))
     ii=(np.repeat(starts,capture['length'])[:capture['n']]+np.arange(capture['n'])%capture['length'])%capture['length_series']
     assert np.array_equal(ii,capture['index']);blockrecords.append({'seed':seed,'drift':drift,'blocks':len(starts),'independent_indices_equal':True})
    print(arm,seed,drift,'matched',flush=True)
 pd.DataFrame(rows).to_csv(out/'REPLAY_ARMS.csv',index=False);pd.DataFrame(units).to_csv(out/'REPLAY_UNIT_STATS.csv',index=False)
 pd.DataFrame(diffs).to_csv(out/'REPLAY_METRIC_DIFFERENCES.csv',index=False)
 (out/'VERIFICATION.json').write_text(json.dumps({'runs':len(rows),'traces':len(list((out/'TRACES').glob('*.npz'))),'all_metric_differences_within_1e-9':True,'max_difference':{k:max(d[k] for d in diffs) for k in ['heading_rmse_deg','pos_rmse_m','nees_mean']},'seed0_1_old_trace_arrays_exact':True,'J3':blockrecords,'source_modified':False},indent=2))
m.cmd_run=run
sys.argv=['structured_noise_control.py','run','--s1','/routes/source/results/DRIVE_SIM_20261007/S1','--h-dir','/routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2','--lut','/legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy','--lut-meta','/legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_meta.json','--bank-freqs','/job/freqs_hz.npy','--cases','R2A','--mounts','0','--drifts','0','1','2','--seeds','5','--seed0','0','--trace-seeds','0','1','2','3','4','--out',str(out)]
m.main()
