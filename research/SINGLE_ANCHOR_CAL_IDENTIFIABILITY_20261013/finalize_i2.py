"""Descriptive episode summaries and frozen necessary reference diagnostics."""
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
from i2_ideal_range_calibration import summarize, write
HERE=Path(__file__).resolve().parent
OUT=HERE/'out/i2_run_01'

def main():
    frame=pd.read_csv(OUT/'I2_CALIBRATION_POSTERIOR.csv')
    # A collapsed static-parameter cloud cannot define a 2D credible region.
    # Preserve original numeric outputs; exclude such regions in derived summaries.
    frame.loc[frame.ancestors<3,'joint_coverage']=np.nan
    final=frame.sort_values('k').groupby(['episode','arm'],as_index=False).tail(1)
    rng=np.random.default_rng(202610132204)
    rows=[]
    for (world,route,arm),g in final.groupby(['world','route','arm']):
        base=final[(final.world==world)&(final.route==route)&(final.arm=='DR')].set_index('seed')
        g=g.sort_values('seed'); b=base.loc[g.seed]
        row=dict(world=world,route=route,arm=arm,n=len(g),sigma_m=g.sigma_m.iloc[0],rate_hz=int(g.rate_hz.iloc[0]))
        for state,unit in [('bg','dps'),('eps','')]:
            err=state+'_error'+('_'+unit if unit else '')
            sd=state+'_sd'+('_'+unit if unit else '')
            e=g[err].to_numpy(); delta=e**2-b[err].to_numpy()**2
            ratio=g[sd].to_numpy()/b[sd].to_numpy()
            indices=rng.integers(0,len(g),size=(10000,len(g)))
            ci=np.quantile(delta[indices].mean(axis=1),[.025,.975])
            row.update({state+'_rmse':float(np.sqrt(np.mean(e*e))),state+'_mean_posterior_sd':float(g[sd].mean()),state+'_coverage':float(g[state+'_coverage'].mean()),state+'_paired_sd_ratio':float(ratio.mean()),state+'_paired_mse_delta':float(delta.mean()),state+'_paired_mse_delta_boot_lo':float(ci[0]),state+'_paired_mse_delta_boot_hi':float(ci[1])})
        row['joint_coverage_valid_only']=float(g.joint_coverage.mean())
        row['joint_region_valid_n']=int(g.joint_coverage.notna().sum())
        row['joint_region_invalid_n']=int(g.joint_coverage.isna().sum())
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUT/'I2_PERFORMANCE_CURVES.csv',index=False)
    time_rows=[]
    for (episode,arm),g in frame.groupby(['episode','arm']):
        g=g.sort_values('k'); initial=g.iloc[0]
        for _,r in g.iterrows():
            dr=frame[(frame.episode==episode)&(frame.arm=='DR')&(frame.k==r.k)].iloc[0]
            time_rows.append(dict(episode=episode,arm=arm,t_s=r.t_s,
                bg_width_vs_initial=r.bg_sd_dps/initial.bg_sd_dps,
                eps_width_vs_initial=r.eps_sd/initial.eps_sd,
                bg_variance_ratio_dr=dr.bg_sd_dps**2/r.bg_sd_dps**2 if r.bg_sd_dps>0 else None,
                eps_variance_ratio_dr=dr.eps_sd**2/r.eps_sd**2 if r.eps_sd>0 else None,
                interpretation='algorithmic variance ratio, not validated information gain'))
    pd.DataFrame(time_rows).to_csv(OUT/'I2_WIDTH_TIMESERIES.csv',index=False)
    validation=json.loads((OUT/'I2_REFERENCE_VALIDATION.json').read_text())
    for case in validation['cases']:
        d=OUT/case['episode']; arm=case['arm']
        summaries=[json.loads((d/f'{arm}_posterior.json').read_text())[-1]]+[json.loads((d/f'{arm}_pf_high_{j}.json').read_text())[-1] for j in range(2)]
        with np.load(d/f'{arm}_batch.npz') as z:
            samples=z['samples']; flat=samples.reshape(-1,6)
            bs=summarize(flat,np.full(len(flat),1/len(flat)))
        means=np.array([s['mean'] for s in summaries]+[bs['mean']])
        sds=np.array([s['sd'] for s in summaries]+[bs['sd']])
        gaps=[]
        for i in range(4):
            for j in range(i): gaps.append(np.abs(means[i]-means[j])/np.sqrt((sds[i]**2+sds[j]**2)/2))
        gap=float(np.max(gaps)); ratio=float(np.max(sds.max(axis=0)/sds.min(axis=0))) if np.all(sds>0) else None
        rh=case['batch']['split_rhat']; ess=case['batch']['within_chain_ess']
        checks=dict(rhat=all(v is not None and v<1.05 for v in rh),ess=all(v is not None and v>400 for v in ess),ancestry=min([case['primary_ancestors']]+case['high_ancestors'])>=100,posterior_mean_agreement=gap<=.25,posterior_sd_agreement=ratio is not None and ratio<=1.25)
        case.update(necessary_checks=checks,max_cal_mean_gap_pooled_sd=gap,max_cal_sd_ratio=ratio,batch_cal_summary=bs,multimodality='NOT_RESOLVED: chain diagnostics cannot exclude unvisited modes',status='NECESSARY_CHECKS_PASS_NOT_GLOBAL_PROOF' if all(checks.values()) else 'REFERENCE_NOT_VALIDATED')
    validation['reason']='Frozen necessary convergence/ancestry/agreement checks applied; no unconditional reference approval.'
    write(OUT/'I2_REFERENCE_VALIDATION.json',validation)
    # Curves depict exploratory PF output, not validated posterior information.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    table=pd.DataFrame(rows)
    fig,axes=plt.subplots(2,2,figsize=(11,8),layout='constrained')
    for ax,((world,route),g) in zip(axes.flat,table.groupby(['world','route'])):
        for hz in [1,5]:
            z=g[(g.arm!='DR')&(g.rate_hz==hz)].sort_values('sigma_m')
            ax.plot(z.sigma_m,z.bg_rmse,'o-',label=f'{hz} Hz RMSE')
            ax.plot(z.sigma_m,z.bg_mean_posterior_sd,'o--',label=f'{hz} Hz posterior SD')
        ax.axhline(g[g.arm=='DR'].bg_rmse.iloc[0],color='gray',label='DR RMSE')
        ax.set(title=f'{world} / {route}',xlabel='Range sigma (m)',ylabel='Gyro bias (deg/s)')
        ax.legend(fontsize=7); ax.grid(alpha=.25)
    fig.suptitle('I2 S1 development: 4 episodes/cell; reference NOT VALIDATED')
    fig.savefig(OUT/'I2_PERFORMANCE_CURVES.png',dpi=160); plt.close(fig)
    gate=json.loads((OUT/'I2_GATE.json').read_text())
    gate.update(reference='REFERENCE_NOT_VALIDATED',reference_cases=len(validation['cases']),primary_runs=int(final.shape[0]),episodes=int(final.episode.nunique()),reason=['Operational precision unspecified: performance curves only','S0 gauge/domain pending','Reference diagnostics recorded; practical information claims withheld'])
    write(OUT/'I2_GATE.json',gate)
    manifest=json.loads((OUT/'I2_RUN_MANIFEST.json').read_text())
    manifest['finalization_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['outputs_sha256']={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name not in ('I2_RUN_MANIFEST.json','I2_FINALIZATION_MANIFEST.json')}
    write(OUT/'I2_RUN_MANIFEST.json',manifest)
    write(OUT/'I2_FINALIZATION_MANIFEST.json',dict(script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),output_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='I2_FINALIZATION_MANIFEST.json'}))
    print(table[['world','route','arm','bg_rmse','bg_mean_posterior_sd','bg_coverage']].to_string(index=False))

if __name__=='__main__': main()
