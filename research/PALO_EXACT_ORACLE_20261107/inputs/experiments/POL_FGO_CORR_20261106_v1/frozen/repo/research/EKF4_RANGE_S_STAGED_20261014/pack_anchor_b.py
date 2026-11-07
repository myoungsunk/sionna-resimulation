"""Package existing frozen observations; no H-to-observation physics reimplementation.

Requires a separately archived DR3 B0 prior. RF-conditioned CONTROL priors are forbidden.
This packer does not generate, fit, or score any estimator output.
"""
import argparse, io, json, zipfile
from pathlib import Path
import numpy as np
from anchor_b_inputs import sha_file

def validate_trace(d):
    shapes={'t_s':(979,), 'pose_id':(979,), 'truth_for_offline_scoring_only':(979,3),
            'z_r_m':(979,), 'z_s':(979,), 'xminus':(979,3),'Pminus':(979,3,3)}
    for key,shape in shapes.items():
        if key not in d or d[key].shape!=shape or not np.isfinite(d[key]).all():
            raise ValueError('INVALID_ARRAY:'+key)
    if not np.all(np.diff(d['t_s'])>0) or len(np.unique(d['pose_id']))!=979:
        raise ValueError('TIME_OR_POSE_ID_INVALID')
    if int(np.count_nonzero(d['t_s']>=30))!=829:
        raise ValueError('SCORING_MASK_CHANGED')
    if not np.allclose(d['Pminus'],d['Pminus'].transpose(0,2,1),rtol=0,atol=1e-14) or np.linalg.eigvalsh(d['Pminus']).min()<=0:
        raise ValueError('INVALID_PRIOR_COVARIANCE')

def pack(control,los,prior,prior_sha256,out):
    if sha_file(prior)!=prior_sha256:raise ValueError('INDEPENDENT_PRIOR_HASH_MISMATCH')
    with np.load(control,allow_pickle=False) as c, np.load(los,allow_pickle=False) as l, np.load(prior,allow_pickle=False) as p:
        if not {'xminus','Pminus','t_s','pose_id','truth_for_offline_scoring_only'}<=set(p.files):
            raise ValueError('INDEPENDENT_DR3_PRIOR_REQUIRED_NOT_CONTROL_PRIOR')
        if Path(control).name!='R2_aB_m0_B0_CONTROL.npz':
            raise ValueError('WRONG_CONTROL_CASE_OR_BIAS_FILENAME')
        # CONTROL provenance is also frozen in the packing receipt below.
        names=c['names'].tolist();j=names.index('OFF_BB')
        full=c['nu'][:,j]+c['h'][:,j]+c['mu'][:,j]
        if not np.array_equal(c['t_s'],l['t']) or not np.array_equal(c['truth_scoring_only'],l['gt']):
            raise ValueError('LOS_FULL_PAIRING_MISMATCH')
        common={k:p[k].copy() for k in ('xminus','Pminus','t_s','pose_id','truth_for_offline_scoring_only')}
        if not np.array_equal(p['t_s'],c['t_s']) or not np.array_equal(p['pose_id'],c['pose_id']) or not np.array_equal(p['truth_for_offline_scoring_only'],c['truth_scoring_only'][:,:3]):
            raise ValueError('PRIOR_PAIRING_MISMATCH')
        members={};desc=[]
        for channel,z in [('los',l['z_los']),('full',full)]:
            d=dict(common,z_r_m=z[:,0],z_s=z[:,1]);validate_trace(d)
            buf=io.BytesIO();np.savez_compressed(buf,**d);raw=buf.getvalue()
            import hashlib
            name=f'R2_aB_m0_{channel}_seed0_ONE_STEP.npz'
            members['P2_OUT/'+name]=raw
            desc.append({'case':'R2_aB_m0','channel':channel,'trace_file':name,'trace_sha256':hashlib.sha256(raw).hexdigest()})
    members['P2_OUT/P2_ONE_STEP_SUMMARY.json']=json.dumps({'per_case':desc}).encode()
    out=Path(out)
    with out.open('xb') as f, zipfile.ZipFile(f,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(members.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,11,2,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,raw)
    receipt={'status':'PACKED_NOT_REPLAYED','archive_sha256':sha_file(out),
             'sources':{str(x):sha_file(x) for x in (control,los,prior)},
             'observation_method':'Full = nu + h + mu (undo stored mean subtraction); LoS = archived z_los',
             'prior_note':'separately supplied DR3 prior; numerical parity still mandatory at replay',
             'scientific_PASS':False}
    out.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('control','los','prior','prior-sha256','out'):p.add_argument('--'+name,required=True)
    print(json.dumps(pack(**vars(p.parse_args()))))
