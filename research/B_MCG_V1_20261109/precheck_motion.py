"""P2: evaluate raw motion shape without current RF. Truth is evaluator-only."""
from __future__ import annotations
import argparse, json, hashlib, sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/research/EKF4_RANGE_S_STAGED_20261014'))
import core

def run(assets, archives, out):
    out.mkdir(parents=True,exist_ok=True)
    reports={}; rows=[]
    for route in ('R2','R4','R5'):
        with np.load(assets/f'{route}_B0_Full_10__online.npz',allow_pickle=False) as f:
            on={k:f[k] for k in ('t','pose_id','ds','gy','dt','x0')}
        with np.load(assets/f'{route}_B0_Full_10__evaluator.npz',allow_pickle=False) as f:
            truth=f['truth']; assert np.array_equal(f['t'],on['t']) and np.array_equal(f['pose_id'],on['pose_id'])
        with np.load(archives/route/f'{route}_B_FROZEN.npz',allow_pickle=False) as f: prior=f['prior']
        t=on['t']; assert np.all(np.diff(t)>0) and np.allclose(np.diff(t),on['dt'][1:],rtol=0,atol=1e-12)
        dpsi=core.wrap(np.diff(truth[:,2])); raw_bg=(on['gy'][1:]-dpsi)/on['dt'][1:]
        reports[route]={'n':len(t),'control_units':'ds m; gy integrated rad; dt s',
            'raw_gyro_minus_true_rate_deg_s_quantiles':np.degrees(np.quantile(raw_bg,[0,.01,.5,.99,1])).tolist(),
            'true_yaw_step_deg_quantiles':np.degrees(np.quantile(abs(dpsi),[.5,.95,.99,1])).tolist(),
            'anchor_position_error_p99_m':float(np.quantile(np.linalg.norm(prior[:,:2]-truth[:,:2],axis=1),.99)),
            'anchor_yaw_error_p99_deg':float(np.degrees(np.quantile(abs(core.wrap(prior[:,2]-truth[:,2])),.99))),
            'windows':{}}
        for span in (2.,5.,10.):
            steps=int(round(span/.2)); groups={}
            for k in range(steps,len(t)):
                a=k-steps
                # Both use a true pose so these errors isolate motion shape and bias.
                for mode,bg in [('zero_bg',0.),('frozen_anchor_bg',prior[a,3])]:
                    x=np.r_[truth[a],bg]
                    for j in range(a+1,k+1): x=core.transition(x,on['ds'][j],on['gy'][j],on['dt'][j])[0]
                    e=x[:3]-truth[k];e[2]=core.wrap(e[2])
                    row={'route':route,'k':k,'a':a,'span_s':span,'mode':mode,
                         'relative_yaw_error_rad':float(e[2]),'relative_xy_error_m':float(np.linalg.norm(e[:2])),
                         'window_abs_rotation_rad':float(abs(core.wrap(truth[k,2]-truth[a,2]))),
                         'anchor_bg_rad_s':float(bg)}
                    rows.append(row);groups.setdefault(mode,[]).append(row)
            reports[route]['windows'][str(span)]={}
            for mode,rr in groups.items():
                yaw=np.array([r['relative_yaw_error_rad'] for r in rr]); xy=np.array([r['relative_xy_error_m'] for r in rr])
                reports[route]['windows'][str(span)][mode]={'n':len(rr),'yaw_abs_p50_p95_p99_max_deg':np.degrees(np.quantile(abs(yaw),[.5,.95,.99,1])).tolist(),
                   'xy_p50_p95_p99_max_m':np.quantile(xy,[.5,.95,.99,1]).tolist()}
    import csv
    with (out/'MOTION_WINDOWS.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    # Train-only motion envelopes and anchor bounds. Floors are explicit engineering
    # protection for wrong-reference stress tests, not claimed confidence intervals.
    folds={}
    for heldout in reports:
        train=[r for r in reports if r!=heldout]
        chosen=[r for r in rows if r['route'] in train and r['span_s']==5. and r['mode']=='frozen_anchor_bg']
        qyaw=float(np.quantile([abs(r['relative_yaw_error_rad']) for r in chosen],.99))
        qxy=float(np.quantile([r['relative_xy_error_m'] for r in chosen],.99))
        bounds=[max(.5,1.5*max(reports[r]['anchor_position_error_p99_m'] for r in train))]*2
        bounds += [float(np.radians(max(30.,1.5*max(reports[r]['anchor_yaw_error_p99_deg'] for r in train)))),float(np.radians(.2))]
        test=[r for r in rows if r['route']==heldout and r['span_s']==5. and r['mode']=='frozen_anchor_bg']
        envelope_yaw=max(np.radians(.15),1.5*qyaw);envelope_xy=max(.03,1.5*qxy)
        folds[heldout]={'train_routes':train,'n_train_windows':len(chosen),'anchor_delta_bounds':bounds,
            'motion_yaw_envelope_rad':float(envelope_yaw),'motion_xy_envelope_m':float(envelope_xy),
            'heldout_yaw_coverage':float(np.mean([abs(r['relative_yaw_error_rad'])<=envelope_yaw for r in test])),
            'heldout_xy_coverage':float(np.mean([r['relative_xy_error_m']<=envelope_xy for r in test]))}
    result={'status':'EXECUTED_DESCRIPTIVE_P2','scope':'R2/R4/R5 B0 Full seed10; overlapping windows are not independent samples',
            'truth_role':'Offline evaluation and training-fold envelope only; never runtime monitor input',
            'routes':reports,'folds':folds,'design_floors':{'position_bounds_m':.5,'yaw_bounds_deg':30.,'bg_bounds_deg_s':.2,
                'yaw_envelope_floor_deg':.15,'xy_envelope_floor_m':.03,'empirical_q99_multiplier':1.5}}
    (out/'P2_MOTION.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--archives',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.assets,a.archives,a.out)
