"""Gate before main experiment: archived independent DR3 and P2 single-update parity."""
import argparse,io,json,math
from pathlib import Path
import numpy as np
from anchor_b_inputs import ROOT,open_verified_archive,sha_file
from pack_anchor_b import validate_trace
from r2_bias_replay import build_positive_bias_controls,predict_one,filter_one,INITIAL_POSE_STD
from p3_rf_adapter4 import FrozenLut,R0

def check(archive,out):
    lut=FrozenLut()
    manifest=json.loads((ROOT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
    case=next(x for x in manifest['cases'] if x['id']=='R2_aB_m0')
    rows=[]
    with open_verified_archive(archive) as z:
        for channel in ('los','full'):
            with np.load(io.BytesIO(z.read(f'P2_OUT/R2_aB_m0_{channel}_seed0_ONE_STEP.npz')),allow_pickle=False) as a:
                d={k:a[k].copy() for k in a.files}
            validate_trace(d)
            controls,x=build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],'B0')
            P=np.diag(INITIAL_POSE_STD**2)
            dx=dp=0.
            for k in range(len(d['t_s'])):
                if k:x,P=predict_one(x,P,controls['ds_odom'][k],controls['dtheta_gyro'][k],controls['dt_s'][k])
                error=x-d['xminus'][k];error[2]=(error[2]+math.pi)%(2*math.pi)-math.pi
                dx=max(dx,float(np.abs(error).max()));dp=max(dp,float(np.abs(P-d['Pminus'][k]).max()))
            row={'channel':channel,'DR3_X_max_abs':dx,'DR3_P_max_abs':dp,'one_step':{}}
            assert max(dx,dp)<=1e-7,('DR3_PARITY_FAILED',row)
            obs=np.column_stack([d['z_r_m'],d['z_s']])
            for arm,index in [('S3',0),('J3',2)]:
                dx=dp=0.;mask_mismatch=0;dr=0.
                for k in range(len(obs)):
                    x,P,status,nis=filter_one(d['xminus'][k],d['Pminus'][k],obs[k],arm,case,lut)
                    error=x-d['xplus'][k,index];error[2]=(error[2]+math.pi)%(2*math.pi)-math.pi
                    dx=max(dx,float(np.abs(error).max()));dp=max(dp,float(np.abs(P-d['Pplus'][k,index]).max()))
                    mask_mismatch+=int((status=='APPLIED')!=(d['status'][k,index]=='applied'))
                    expected_R=d['R'][k,index,:1,:1] if arm=='S3' else d['R'][k,index][::-1,::-1]
                    current_R=R0[1:,1:] if arm=='S3' else R0
                    dr=max(dr,float(np.abs(current_R-expected_R).max()))
                row['one_step'][arm]={'X_max_abs':dx,'P_max_abs':dp,'mask_mismatch':mask_mismatch,'R_max_abs':dr}
                assert dx<=1e-7 and dp<=1e-7 and mask_mismatch==0 and dr<=1e-12,('P2_ONE_STEP_PARITY_FAILED',row)
            rows.append(row)
    result={'question_id':'DLP-ANCHORB-8ARM-20261102','status':'PASS','archive_sha256':sha_file(archive),'checks':rows,
            'scope':'independently archived DR3 prior and S3/J3 one-step X/P/mask/R with exact archived times and pose IDs',
            'independent_audit':False,'scientific_PASS':False}
    with Path(out).open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();check(a.archive,a.out)
