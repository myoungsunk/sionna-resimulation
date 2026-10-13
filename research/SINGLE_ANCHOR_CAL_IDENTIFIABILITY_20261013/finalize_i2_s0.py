"""I2 S0 episode summaries and diagnostic qualification without claim promotion."""
from pathlib import Path
import json,hashlib,datetime,sys
import numpy as np
import pandas as pd
from i2_ideal_range_calibration import write
from i2_s0 import summary
HERE=Path(__file__).resolve().parent;OUT=HERE/'out/i2_s0_run_01'

def agreement(items):
    means=np.array([i['mean'] for i in items]);sd=np.array([i['sd'] for i in items])
    if not np.all(sd>0):return dict(mean_gap=None,sd_ratio=None,valid=False)
    gaps=[np.max(np.abs(means[i]-means[j])/np.sqrt((sd[i]**2+sd[j]**2)/2)) for i in range(len(items)) for j in range(i)]
    return dict(mean_gap=float(max(gaps)),sd_ratio=float(np.max(sd.max(axis=0)/sd.min(axis=0))),valid=True)

def main():
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    frame=pd.read_csv(OUT/'I2_S0_CALIBRATION_POSTERIOR.csv')
    final=frame.sort_values('k').groupby(['episode','label'],as_index=False).tail(1)
    aggregates=[];rng=np.random.default_rng(202610132306)
    for (world,route,label),g in final.groupby(['world','route','label']):
        g=g.sort_values('seed');base=final[(final.world==world)&(final.route==route)&(final.label=='DR_area')].set_index('seed').loc[g.seed]
        row=dict(world=world,route=route,label=label,arm=g.arm.iloc[0],prior=g.prior.iloc[0],n=len(g),ancestors_min=int(g.ancestors.min()),ancestors_max=int(g.ancestors.max()),joint_valid_n=int(g.joint_coverage.notna().sum()),joint_coverage_valid_only=float(g.joint_coverage.mean()))
        for state,err,sd in [('bg','bg_error_dps','bg_sd_dps'),('eps','eps_error','eps_sd')]:
            e=g[err].to_numpy();delta=e**2-base[err].to_numpy()**2
            draws=rng.integers(0,len(g),size=(10000,len(g)))
            bounds=np.quantile(delta[draws].mean(axis=1),[.025,.975])
            row.update({state+'_rmse':float(np.sqrt(np.mean(e*e))),state+'_sd_mean':float(g[sd].mean()),state+'_coverage':float(g[state+'_coverage'].mean()),state+'_paired_mse_delta':float(delta.mean()),state+'_paired_mse_delta_boot_lo':float(bounds[0]),state+'_paired_mse_delta_boot_hi':float(bounds[1])})
        aggregates.append(row)
    table=pd.DataFrame(aggregates);table.to_csv(OUT/'I2_S0_PERFORMANCE_CURVES.csv',index=False)
    sens=[]
    for _,r in final[(final.prior!='area')|final.cutoff.notna()].iterrows():
        b=final[(final.episode==r.episode)&(final.label==r.arm+'_area')].iloc[0]
        sens.append(dict(episode=r.episode,arm=r.arm,prior=r.prior,cutoff=r.cutoff,bg_mean_shift_dps=r.bg_error_dps-b.bg_error_dps,eps_mean_shift=r.eps_error-b.eps_error,bg_sd_change_dps=r.bg_sd_dps-b.bg_sd_dps,eps_sd_change=r.eps_sd-b.eps_sd,ancestors=int(r.ancestors),baseline_ancestors=int(b.ancestors),interpretation='REFERENCE_NOT_VALIDATED: prior effect and particle degeneracy not separated'))
    pd.DataFrame(sens).to_csv(OUT/'I2_S0_PRIOR_SENSITIVITY.csv',index=False)
    radius_rows=[]
    for path in OUT.rglob('*_posterior.json'):
        if '_N' in path.name or path.name.startswith('DR'):continue
        first=json.loads(path.read_text())[0]
        radius_rows.append(dict(episode=path.parent.name,label=path.stem.removesuffix('_posterior'),rho_q025=first['initial_rho_quantiles'][0],rho_q50=first['initial_rho_quantiles'][1],rho_q975=first['initial_rho_quantiles'][2],heading_resultant=first['initial_delta_resultant']))
    pd.DataFrame(radius_rows).to_csv(OUT/'I2_S0_INITIAL_RADIUS_SENSITIVITY.csv',index=False)
    references=[];batch_sensitivity=[]
    for path in sorted(OUT.rglob('*_batch.json')):
        label=path.stem.removesuffix('_batch');episode=path.parent.name
        prior=next(p for p in ['halfnormal100','radius','area'] if label.endswith('_'+p))
        arm=label[:-(len(prior)+1)]
        b=json.loads(path.read_text());d=b['diagnostics']
        with np.load(path.with_suffix('.npz')) as z:samples=z['calibration_samples'];raw=z['samples']
        flat=samples.reshape(-1,3);bs=summary(flat,np.ones(len(flat))/len(flat))
        primary=json.loads((path.parent/f'{label}_posterior.json').read_text())[-1]
        high=[]
        if prior=='area':
            high=[json.loads(p.read_text())[-1] for p in sorted(path.parent.glob(f'{arm}_area_N*_posterior.json'))]
        match=agreement([primary,*high,bs])
        checks=dict(rhat=all(v is not None and v<1.05 for v in d['split_rhat']),ess=all(v is not None and v>400 for v in d['within_chain_ess']),pf_ancestry=all(s['ancestors']>=100 for s in [primary,*high]),mean_agreement=match['valid'] and match['mean_gap']<=.25,sd_agreement=match['valid'] and match['sd_ratio']<=1.25)
        references.append(dict(episode=episode,arm=arm,prior=prior,necessary_checks=checks,status='NECESSARY_CHECKS_PASS_NOT_GLOBAL_PROOF' if all(checks.values()) else 'REFERENCE_NOT_VALIDATED',diagnostics=d,calibration_diagnostics=b['calibration_diagnostics'],pf_ancestors=[s['ancestors'] for s in [primary,*high]],agreement=match,batch_cal_summary=bs,initial_range_consumed=b['initial_range_consumed'],subsequent_range_count=b['subsequent_range_count'],delta_chain_resultants=np.abs(np.mean(np.exp(1j*raw[:,:,1]),axis=1)).tolist(),delta_chain_circular_means=np.angle(np.mean(np.exp(1j*raw[:,:,1]),axis=1)).tolist(),multimodality='global mode completeness unresolved; inspect chain/particle circular distributions'))
        batch_sensitivity.append(dict(episode=episode,arm=arm,prior=prior,bg_mean=float(bs['mean'][0]),eps_mean=float(bs['mean'][1]),bg_sd=float(bs['sd'][0]),eps_sd=float(bs['sd'][1]),rhat_max=max(d['split_rhat']) if all(v is not None for v in d['split_rhat']) else None,ess_min=min(d['within_chain_ess']) if all(v is not None for v in d['within_chain_ess']) else None))
    pd.DataFrame(batch_sensitivity).to_csv(OUT/'I2_S0_BATCH_PRIOR_SENSITIVITY.csv',index=False)
    write(OUT/'I2_S0_REFERENCE_VALIDATION.json',dict(status='REFERENCE_NOT_VALIDATED',cases=references,note='Necessary checks are diagnostic. No exact-posterior or global-mode-completeness claim.'))
    radial=json.loads((OUT/'I2_S0_RADIAL_INITIALIZATION.json').read_text())
    rr=[r['diagnostics'] for r in radial if 'numerical_tail_mass_bound' in r['diagnostics']]
    numerical=dict(max_tail_bound=max(r['numerical_tail_mass_bound'] for r in rr),max_quadrature_relative_error=max(r['quadrature_relative_error'] for r in rr),max_quantile_resolution_error_m=max(r['quantile_resolution_error_m'] for r in rr),max_cutoff_excluded_mass=max(r['excluded_mass_fraction'] for r in rr))
    numerical['status']='PASS' if numerical['max_tail_bound']<=1e-12 and numerical['max_quadrature_relative_error']<=1e-9 and numerical['max_quantile_resolution_error_m']<=1e-5 else 'FAIL'
    write(OUT/'I2_S0_GATE.json',dict(implementation='PASS',execution='PASS',overall='INCONCLUSIVE',reference='REFERENCE_NOT_VALIDATED',radial_numerical=numerical,prior_robustness='INCONCLUSIVE',practical_sufficiency='INCONCLUSIVE',primary_and_sensitivity_pf_runs=len(final),high_pf_runs=len(list(OUT.rglob('*_N*_pf.npz'))),batch_runs=len(references),I3='NOT_RUN',I7='NOT_RUN',reasons=['Prior/domain experiments recorded; posterior robustness requires converged references','Operational error requirements remain unspecified']))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,route in zip(axs,['R2','R4']):
        g=final[(final.world=='A2_3_GAUSS_LEVEL')&(final.route==route)&(final.seed<=8001)&final.label.str.startswith('RANGE_0.05_5_')]
        rmse=g.groupby('prior').bg_error_dps.apply(lambda v:np.sqrt(np.mean(v*v)))
        ax.bar(rmse.index,rmse.values);ax.set(title=route,xlabel='Initial radial reference prior',ylabel='Gyro bias RMSE (deg/s)');ax.tick_params(axis='x',rotation=20)
    fig.suptitle('S0 prior sensitivity: unvalidated PF, same 2 development seeds')
    fig.savefig(OUT/'I2_S0_PRIOR_SENSITIVITY.png',dpi=160);plt.close(fig)
    write(OUT/'I2_S0_ANALYSIS_MANIFEST.json',dict(start=start,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),output_sha256={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='I2_S0_ANALYSIS_MANIFEST.json'}))
    print(json.dumps(dict(reference_cases=len(references),necessary_pass=sum(all(c['necessary_checks'].values()) for c in references),numerical=numerical),indent=2))

if __name__=='__main__':main()
