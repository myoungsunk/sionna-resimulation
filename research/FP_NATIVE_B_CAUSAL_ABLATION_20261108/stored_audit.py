#!/usr/bin/env python3
"""Reproduce descriptive native↔B and B↔K1/K2 feedback findings from stored CSVs.

Reads no FFD bank or oracle at inference time; uses saved eval labels for reporting.
This is NOT the four-arm NN/BN/NB/BB causal experiment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT_REL=Path('research/FP_SC_RECOVERY_R0_R5_20261107')
T1_REL=Path('research/FP_SC_MISSED_ONSET_T0T1_20261106/RUN_001')
MB_REL=Path('research/MBVAR_PRR_001_20261103')


def wrap(v):return (v+np.pi)%(2*np.pi)-np.pi


def run(repo:Path):
    root=repo/ROOT_REL
    rows=pd.read_csv(root/'R45_RUN_001/R5_ROWS.csv')
    met=pd.read_csv(root/'R45_RUN_001/R5_METRICS.csv')
    frames=[]
    for route in ['R2','R4','R5']:
        p=repo/T1_REL/f'{route}_B0_Full_10_FEATURES.csv'
        f=pd.read_csv(p)
        assert len(f)=={'R2':979,'R4':742,'R5':1415}[route]
        frames.append(f)
    f=pd.concat(frames,ignore_index=True)
    f.rename(columns={'raw':'native','TWO_PORT_GLOBAL30':'B','reference':'ref'},inplace=True)
    assert not f.duplicated(['case','k']).any()
    assert len(f)==3136
    assert (f['B']<=f['native']).all()
    changes=f[f.B!=f.native]
    cases={
        'both_correct':int(((f.native==f.ref)&(f.B==f.ref)).sum()),
        'native_correct_B_wrong':int(((f.native==f.ref)&(f.B!=f.ref)).sum()),
        'native_wrong_B_correct':int(((f.native!=f.ref)&(f.B==f.ref)).sum()),
        'both_wrong':int(((f.native!=f.ref)&(f.B!=f.ref)).sum()),
    }
    assert len(changes)==572 and cases['native_correct_B_wrong']==229 and cases['native_wrong_B_correct']==233
    base={'n':3136,'changed_tap':len(changes),'changed_fraction':float(len(changes)/len(f)),
          'changed_earlier':int((changes.B<changes.native).sum()),
          'changed_later':int((changes.B>changes.native).sum()),
          'mean_changed_shift_taps':float((changes.native-changes.B).mean()),
          'native_mean_abs_tap_error':float(np.mean(abs(f.native-f.ref))),
          'B_mean_abs_tap_error':float(np.mean(abs(f.B-f.ref))),
          'pair_categories':cases}
    # Verify T1/B parity on the same waveform and keys.
    bb=rows[rows.arm=='B'].copy()
    assert len(bb)==3136 and not bb.duplicated(['case','k']).any()
    check=f.merge(bb[['case','k','B','reference','time_s']],on=['case','k'],validate='1:1',suffixes=('_T1','_R5'))
    assert (check.B_T1==check.B_R5).all()
    assert (check.ref==check.reference).all()
    assert np.max(abs(check.t-check.time_s))<1e-9

    # W0 NN: route-specific existing W0 results, not a newly computed NN.
    mR2=pd.read_csv(repo/MB_REL/'POST_S3_PROPOSER_20261104/R2_EXTENSION/FULL_002/NATURAL_SUMMARY.csv')
    mR45=pd.read_csv(repo/MB_REL/'S1/runs/EVAL_001/SCORES_PER_SEED.csv')
    old=[]; new=[]
    for route in ['R2','R4','R5']:
        if route=='R2':
            qq=mR2[(mR2.route=='R2')&(mR2.bias=='B0')&(mR2.channel=='Full')&(mR2.seed==10)&(mR2.stage=='S2')&(mR2.arm=='A')&(mR2.window=='all')]
        else:
            qq=mR45[(mR45.route==route)&(mR45.bias=='B0')&(mR45.channel=='Full')&(mR45.seed==10)&(mR45.arm=='W0')&(mR45.window=='all')]
        assert len(qq)==1
        one=qq.iloc[0]
        old.append(dict(route=route,n=int(one.n),heading_rmse_deg=float(one.heading_rmse_deg),xy_rmse_m=float(one.xy_rmse_m)))
        current=met[(met.case==f'{route}_B0_Full_10')&(met.arm=='B')]
        assert len(current)==1
        cur=current.iloc[0]
        new.append(dict(route=route,n=int(cur.n),heading_rmse_deg=float(cur.heading_RMSE_deg),xy_rmse_m=float(cur.XY_RMSE_m)))
    def pool(src,key):
        n=sum(x['n'] for x in src)
        return float(np.sqrt(sum(x['n']*x[key]**2 for x in src)/n))
    r2={'native':{'heading_rmse_deg':pool(old,'heading_rmse_deg'),'XY_rmse_cm':100*pool(old,'xy_rmse_m')},
        'B':{'heading_rmse_deg':pool(new,'heading_rmse_deg'),'XY_rmse_cm':100*pool(new,'xy_rmse_m')},
        'native_routes':old,'B_routes':new}

    feedback=[]
    for arm in ['K1_R','K2_R','K1_RS','K2_RS']:
        p=rows[rows.arm==arm]
        both=bb.merge(p,on=['case','k'],validate='1:1',suffixes=('_B','_A'))
        assert len(both)==3136
        same=both.selected_A==both.B_B
        # K?_R always retains B s; K?_RS also uses B s when no tap change.
        state_xy=np.hypot(both.x_A-both.x_B,both.y_A-both.y_B)
        state_yaw=np.abs(wrap(both.heading_rad_A-both.heading_rad_B))
        diverged=(state_xy>1e-7)|(state_yaw>1e-7)
        harm=both.selected_normal_harm_A.astype(bool)
        assert (both[ harm ].B_A==both[ harm ].reference_A).all()
        mean_center=float(np.mean(abs(both.loc[harm,'P_center_m_A']-both.loc[harm,'P_center_m_B']))*100)
        feedback.append(dict(arm=arm,
            same_current_observation=int(same.sum()),
            same_observation_different_posterior=int((same&diverged).sum()),
            same_observation_mean_posterior_XY_separation_cm=float(np.mean(state_xy[same])*100),
            same_observation_changed_gate=int((same&(both.accepted_A!=both.accepted_B)).sum()),
            B_normal_harm=int(harm.sum()),
            harm_not_alarmed_by_B=int((harm&~both.alarm_B).sum()),
            harm_accepted=int((harm&both.accepted_A).sum()),
            harm_mean_Pcenter_shift_from_B_cm=mean_center,
            exact_recovery=int(((both.B_A!=both.reference_A)&(both.selected_A==both.reference_A)).sum())))
    return dict(status='PASS_STORED_CSV_SELF_CHECK',independent_audit=False,
                causal_2x2_executed=False,native_B_detection=base,
                native_vs_B_W0=r2,closed_loop_recovery_feedback=feedback)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--out',type=Path)
    arg=ap.parse_args()
    result=run(arg.repo.resolve())
    if arg.out:
        if arg.out.exists():raise FileExistsError('Output path already exists: '+str(arg.out))
        arg.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    else:print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))

if __name__=='__main__':main()
