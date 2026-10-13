"""D13: matched D0/A/B/C recursive sensitivity to initial yaw and gyro bias.

What exists: D5 has gyro_bias, noise_pair, all for D0/A/B/C; D6 MC is
DR-only no RF. This runner adds the missing FACTORIAL paired experiment.
No RF channel generation; only frozen H and original motion generator.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import numpy as np
from d10_d14_core import new_output,write_rows,save_json,stage_finish,file_sha
from d13_d14_filter_core import VARIANTS,run_cell,verify_frozen_d5,ARCHIVED_D5
from d6_d9_common import (REPO,B_OLD,check_inputs,spectrum,original_lut,rf_case)
from d6_bias_observability import generate_paired
from ekf3 import archived_direct_s_model
from run_d5_regimes import timelines


def paired_table(results):
    p={}
    for row in results:
        key=(row['case'],row['channel'],row['level'],row['seed'],
             row['sigma_heading_deg'],row['arm'],row['method'])
        if (key,row['bias_mode']) in p:raise RuntimeError('Duplicate D13 paired row')
        p[key,row['bias_mode']]=row
    comparison=[]
    keys=set(k for k,mode in p)
    for key in sorted(keys):
        a,b=p.get((key,'off')),p.get((key,'on'))
        if a is None or b is None:continue
        comparison.append(dict(case=key[0],channel=key[1],level=key[2],
          seed=key[3],sigma_heading_deg=key[4],arm=key[5],method=key[6],
          delta_heading_rmse_deg=float(b['heading_rmse_deg']-a['heading_rmse_deg']),
          delta_xy_rmse_m=float(b['xy_rmse_m']-a['xy_rmse_m']),
          delta_pose95=float(b['pose95']-a['pose95']),
          delta_mean_pose_nees=float(b['mean_pose_NEES']-a['mean_pose_NEES']),
          paired_same_initial_and_white_noise=True))
    return comparison


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--cases',nargs='*',default=[])
    ap.add_argument('--channels',nargs='+',choices=['los','full'],default=['los','full'])
    ap.add_argument('--seeds',type=int,nargs='+',default=[0,1,2])
    ap.add_argument('--levels',type=int,nargs='+',default=[0,1,2])
    ap.add_argument('--heading-std-deg',type=float,nargs='+',default=[5,10,17,20,30])
    ap.add_argument('--bias-modes',nargs='+',choices=['off','on'],default=['off','on'])
    ap.add_argument('--methods',nargs='+',choices=VARIANTS,default=['EKF3','UT_PRED','UT_BOTH','BIAS4'])
    ap.add_argument('--save-trace',action='store_true')
    ap.add_argument('--bias-prior-std-dps',type=float,default=.1)
    ap.add_argument('--d5-reference',type=Path,default=REPO/ARCHIVED_D5)
    args=ap.parse_args()
    if (any(n not in (0,1,2) for n in args.levels) or
        any(x<=0 for x in args.heading_std_deg) or args.bias_prior_std_dps<=0 or
        any(len(set(q))!=len(q) for q in (args.cases,args.channels,args.seeds,args.levels,
                                        args.heading_std_deg,args.methods,args.bias_modes))):
        raise ValueError('Invalid/duplicate D13 experiment grid')
    p0=check_inputs();bycase={c['id']:c for c in p0['cases']}
    selected=args.cases or list(bycase)
    if any(c not in bycase for c in selected):raise ValueError('Unknown case')
    routes=timelines(p0);fr=spectrum(p0);lut=original_lut(p0)
    metrics=[];steps=[]
    for name in selected:
        case=bycase[name];t,truth,pids=routes[case['route']]
        model=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),
             tag_height_m=float(case['robot_z_m']),mount_deg=float(case['mount_deg']))
        for ch in args.channels:
            observation=rf_case(p0,case,ch,fr,pids)
            z_s=np.asarray(observation['s'],float)
            r_phys=np.asarray(observation['range_raw_m'],float)-float(B_OLD)
            for level in args.levels:
                for seed in args.seeds:
                    meas0,meas_bias,_=generate_paired(t,truth,level,seed)
                    for bias in args.bias_modes:
                        meas=meas0 if bias=='off' else meas_bias
                        for sigma in args.heading_std_deg:
                            for arm in ('D0','A','B','C'):
                                for method in args.methods:
                                    r,s=run_cell(case,t,truth,meas,z_s,r_phys,model,
                                        channel=ch,seed=seed,level=level,bias_mode=bias,
                                        sigma_heading_deg=float(sigma),arm=arm,variant=method,
                                        save_trace=args.save_trace,
                                        bias_prior_std_dps=args.bias_prior_std_dps)
                                    metrics.append(r);steps.extend(s)
    baseline=[r for r in metrics if r['method']=='EKF3' and r['bias_mode']=='off'
              and r['sigma_heading_deg']==5]
    parity=(verify_frozen_d5(baseline,args.d5_reference) if baseline
            else {'status':'NOT_RUN_NO_5DEG_EKF3_BIAS_OFF_CONTROL'})
    paired=paired_table(metrics)
    out=new_output(args.out)
    a=out/'D13_ARM_NONLINEARITY_BIAS.csv';files=[a];write_rows(a,metrics)
    if paired:
        b=out/'D13_PAIRED_BIAS_EFFECT.csv';write_rows(b,paired);files.append(b)
    if steps:
        c=out/'D13_STEP_TRACE.csv';write_rows(c,steps);files.append(c)
    q=out/'D13_F0_D5_PARITY.json';save_json(q,parity);files.append(q)
    stage_finish(out,'D13',files,config=vars(args),evidence={
        'd5_reference_sha256':file_sha(args.d5_reference) if baseline else None,
        'D13_parity':parity},warnings=[
        'Gyro bias injected into SAME original noise stream; route/H/seed paired',
        'Only BIAS4 has bias as a state; default 3state has no gyro bias estimate',
        'Initial sigma 17-30deg tests EKF/UT but NOT independent RF site',
        'UT_PRED is NOT full nonlinear measurement update; UT_BOTH tests both',
        'Step sample count is not independent ensemble count; ensemble by seed/case',
        'No 3state generic slip robustness claim',
        'All conclusions exploratory until independent RF/seed confirmation'])
    print('D13_EXPLORATORY_DONE',str(out))
if __name__=='__main__':main()
