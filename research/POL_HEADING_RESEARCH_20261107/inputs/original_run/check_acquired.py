from pathlib import Path
import hashlib,io,json,zipfile,shutil
import numpy as np
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
archive=R/'original_RF_R2.zip'
assert sha(archive)=='88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63'
assert archive.stat().st_size==7907090
lut=R/'repo/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT'
lut.mkdir(exist_ok=True)
checks={}
for name,blob in [('hs_lut_2deg.npy','9a53057f6f646f63574574b9a70186452cb5aca9'),('hs_lut_meta.json','5a24bf5f371eb3ad49b77e972b2bc77abecd679f')]:
    p=R/name;raw=p.read_bytes()
    actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    assert actual==blob,(name,actual)
    checks[name]={'sha256':sha(p),'git_blob':actual,'bytes':len(raw)}
    shutil.copyfile(p,lut/name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    summary_raw=z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json')
    assert hashlib.sha256(summary_raw).hexdigest()=='8412e39cbeafa41656041ffe9f7778ef7f0d597508d3cfb2747e4735c4e83634'
    summary=json.loads(summary_raw)
    descs=summary['per_case'];print('descriptors',len(descs))
    traces={}
    for d in descs:
        raw=z.read('P2_OUT/'+d['trace_file'])
        assert hashlib.sha256(raw).hexdigest()==d['trace_sha256']
        if d['case']=='R2_aB_m0':
            with np.load(io.BytesIO(raw),allow_pickle=False) as a:traces[d['channel']]={k:a[k].copy() for k in a.files}
            print(d['channel'],d['trace_file'],[(k,traces[d['channel']][k].shape) for k in ('t_s','truth_for_offline_scoring_only','xminus','Pminus')])
    for key in ('t_s','pose_id','truth_for_offline_scoring_only','xminus','Pminus'):
        assert np.array_equal(traces['los'][key],traces['full'][key]),key
    checks['original_archive']={'sha256':sha(archive),'traces_verified':len(descs),'anchor_b_channels':list(traces),
                               'summary_sha256':hashlib.sha256(summary_raw).hexdigest(),'cross_channel_prior_identity':True}
    # Compare historical observations with the frozen packet sources used in the prior paper task.
    control=R.parent/'DualLP_Physics_Link_Validation_20261101/recovered/inputs/traces/R2_aB_m0_B0_CONTROL.npz'
    los=next(Path('C:/Users/Myoungsun Kim/Obsidian Vault/03_Research/EKF/2026-11-01 논문 초안/figures').rglob('R2_aB_m0_B0_LOS_ZERO_MEAN.npz'))
    with np.load(control) as c,np.load(los) as l:
        j=c['names'].tolist().index('OFF_BB')
        full=c['nu'][:,j]+c['h'][:,j]+c['mu'][:,j]
        for channel,obs in [('los',l['z_los']),('full',full)]:
            a=traces[channel]
            assert np.array_equal(c['pose_id'],a['pose_id'])
            dt=float(np.abs(c['t_s']-a['t_s']).max())
            truthdiff=float(np.abs(c['truth_scoring_only'][:,:3]-a['truth_for_offline_scoring_only']).max())
            diff=np.abs(np.column_stack([a['z_r_m'],a['z_s']])-obs)
            checks['prior_task_observation_comparison_'+channel]={'max_range_m':float(diff[:,0].max()),'max_s':float(diff[:,1].max()),'max_time_s':dt,'max_truth_abs':truthdiff}
(R/'ACQUISITION_CHECK.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
