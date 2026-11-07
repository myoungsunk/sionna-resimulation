"""Prespecified numerical refinement, not statistical parameter tuning."""
import run_heading as m
import numpy as np,json,time
def main():
 d=m.e.data('full');ctrl,x0=m.e.build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],'B0');saved=np.load(m.e.OLD/'results/replay/R2_aB_m0_full_B0_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED'
 m.dump('GRID_CHECK_CONTRACT.json',dict(condition='Full B0 HeadingVariable_matched',original_deg=.25,refined_deg=.125,thresholds={'heading_rmse_difference_deg':.02,'xy_rmse_difference_m':.005,'relative_sigma_change':.02},purpose='numerical convergence only, all other parameters and masks fixed'))
 X,P,ex=m.run(ctrl,d['z_s'],x0,True,mask,np.deg2rad(np.arange(-180,180,.125)))
 np.savez_compressed(m.BASE/'GRID_REFINED.npz',estimate=X,covariance=P,t_s=d['t_s'],**ex)
 refined=m.e.metrics(X,P,d['truth_for_offline_scoring_only'],d['t_s']);orig=np.load(m.BASE/'outputs/full_B0_HeadingVariable_matched.npz');coarse=m.e.metrics(orig['estimate'],orig['covariance'],d['truth_for_offline_scoring_only'],d['t_s'])
 differences={k:refined[k]-coarse[k] for k in ['heading_rmse_deg','xy_rmse_m','heading_sigma_rms_deg','xy_sigma_rms_m']}
 passed=abs(differences['heading_rmse_deg'])<=.02 and abs(differences['xy_rmse_m'])<=.005 and all(abs(refined[k]/coarse[k]-1)<=.02 for k in ['heading_sigma_rms_deg','xy_sigma_rms_m'])
 m.dump('GRID_CHECK.json',dict(status='PASS' if passed else 'FAIL',coarse=coarse,refined=refined,differences=differences));print(json.dumps(differences))
if __name__=='__main__':main()
