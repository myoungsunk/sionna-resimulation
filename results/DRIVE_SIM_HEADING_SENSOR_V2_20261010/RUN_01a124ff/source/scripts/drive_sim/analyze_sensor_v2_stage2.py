"""Reclassify saved stage2 evidence; no new Monte Carlo or RF execution."""
import json,math
from pathlib import Path
import numpy as np
from scipy.stats import chi2,norm
import validate_sensor_v2_stage2 as V
from qclean_uwb.drivesim.filter_v2 import covariance_diagnostic
P=V.OUT

def wilson(success,n):
    z=1.95996398454;p=success/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [center-half,center+half]

def main():
    base=json.loads((P/'SUMMARY.json').read_text());runs=json.loads((P/'RUNS.json').read_text())['rows']
    failures=[];groups={};max_sym=0.;Kmax=0.;Smax=0.;postmax=0.
    corrections={};noise_stats={};initial_stats={}
    for arm in V.arms():
        accepted=[];invalid=[];nulls=[];initials=[];noise=[];biases=[];rwangles=[];qs=[];events=0;eligible=0
        for seed in range(81000,81064):
            path=P/'raw'/f"{arm['name']}_{seed}.npz"
            with np.load(path,allow_pickle=False) as z:
                est=z['estimate_state'];cov=z['covariance_full'];truth=z['truth_state'];n=len(est)
                initial_scale=float(np.linalg.norm(z['initial_prior'],2));bad=np.zeros(n,bool);jointbad=np.zeros(n,bool)
                for k in range(n):
                    reference=initial_scale
                    if k:
                        F=z['odom_F'][k-1];G=z['odom_G'][k-1];Q=z['odom_Q'][k-1]
                        pred=F@cov[k-1]@F.T+G@Q@G.T;reference=max(reference,float(np.linalg.norm(pred,2)))
                        H=z['odom_H'][k-1];C=z['odom_C'][k-1];R=z['odom_R'][k-1];S=z['odom_S'][k-1]
                        J=np.block([[pred,C[:,None]],[C[None,:],np.array([[R]])]])
                        jointdiag=covariance_diagnostic(J,reference);jointbad[k]=not jointdiag['valid']
                        if S>1e-20 and not jointbad[k]:
                            W=np.r_[H,1.];Sj=float(W@J@W);Kj=(J@W)[:6]/Sj
                            Kmax=max(Kmax,float(abs(Kj-z['odom_K'][k-1]).max()));Smax=max(Smax,abs(Sj-S))
                            if z['odom_status'][k-1]=='applied':
                                expected=pred-np.outer((J@W)[:6],(J@W)[:6])/Sj
                                expected[3,3]+=arm.get('rw',0.)**2*z['sensor_dt_s'][k]
                                postmax=max(postmax,float(abs(expected-cov[k]).max()))
                    diag=covariance_diagnostic(cov[k],reference);bad[k]=not diag['valid']
                max_sym=max(max_sym,float(abs(cov-cov.transpose(0,2,1)).max()))
                if bad.any() or jointbad.any():
                    first=int(np.flatnonzero(bad|jointbad)[0]);diag=covariance_diagnostic(cov[first],max(initial_scale,float(np.linalg.norm(cov[first],2))))
                    invalid.append(seed);failures.append(dict(arm=arm['name'],seed=seed,first_invalid_sample=first,time_s=float(z['time_s'][first]),minimum_eigenvalue=diag['minimum_eigenvalue'],tolerance=diag['tolerance'],status='INVALID_COVARIANCE_NEES_NOT_APPLICABLE'))
                else:accepted.append(seed)
                np.savez_compressed(P/'raw'/f"VALIDITY_{arm['name']}_{seed}.npz",covariance_invalid_mask=bad,joint_covariance_invalid_mask=jointbad,raw_sha256=np.array(V.sha(path)))
                err=truth[0]-z['initial_state'];err[2]=math.atan2(math.sin(err[2]),math.cos(err[2]));initials.append(err)
                t=z['time_s'];dt=z['sensor_dt_s'];ds=z['evaluation_true_increments'][:,0];a=z['evaluation_true_increments'][:,1]
                params=dict(zip(z['evaluation_parameter_names'],z['evaluation_true_parameters']));b=.287/(1+params['wheelbase']);c=params['common_scale'];eps=params['wheel_asymmetry']
                clean_d=(1+c)*(ds+eps*b*a/4);clean_o=(1+c)*(a+eps*ds/b)/(1+params['wheelbase'])
                bias=z['evaluation_true_bias_rad_s'];start=np.r_[bias[0],bias[:-1]]
                ng=z['sensor_dtheta_gyro']-(1+params['gyro_sf'])*a-start*dt
                nd=z['sensor_ds_odom']-clean_d;no=z['sensor_dtheta_odom']-clean_o-z['evaluation_slip_yaw_rad']
                noise.append([nd.sum(),ng.sum(),no.sum()]);biases.append(bias[-1]-bias[0]);rwangles.append(float(np.dot(start-bias[0],dt)))
                qs.append(z['evaluation_generated_variance'].sum(0));events+=int(z['evaluation_slip_event'].sum());eligible+=int(z['evaluation_slip_eligible'].sum())
        groups[arm['name']]=dict(expected_runs=64,valid_runs=len(accepted),invalid_runs=len(invalid),invalid_seeds=invalid,chi_square_note='Conditional fixed-parameter mismatch arms are diagnostic, not prior-matched chi-square null tests.')
        if invalid:
            # Preserve pre-correction tables, but never silently discard failures.
            corrections[arm['name']]={k:v for k,v in base[arm['name']].items() if k not in ('pose','full')}
            corrections[arm['name']].update(status='INVALID_COVARIANCE',pose=dict(nees=None,coverage95=None),full=dict(nees=None,coverage95=None),validity=groups[arm['name']])
        else:
            corrections[arm['name']]=base[arm['name']].copy();corrections[arm['name']]['validity']=groups[arm['name']]
            for sub in ('pose','full'):
                info=corrections[arm['name']][sub]
                if info.get('n_nees')==64 and 'coverage95' in info:info['coverage_wilson_ci95']=wilson(round(info['coverage95']*64),64)
                info['standard_full_subspace_claim']=len(info['ranks'])==1 and info['ranks'][0]>0 and info['nullspace_error_max']<1e-10
        initial_stats[arm['name']]=dict(mean=np.mean(initials,0),centered_covariance=np.cov(initials,rowvar=False))
        if arm['name'].startswith(('E_dt','E_RW')):
            sample=np.cov(noise,rowvar=False);expected=np.mean(qs,0)
            n=64;variance_ci=np.column_stack([(n-1)*np.diag(sample)/chi2.ppf(.975,n-1),(n-1)*np.diag(sample)/chi2.ppf(.025,n-1)])
            T=12.;h=arm['dt'];nb=round(T/h);sigma=arm.get('rw',0.)
            noise_stats[arm['name']]=dict(sample_aggregate_sensor_covariance=sample,expected_aggregate_variance=expected,variance_ci95=variance_ci,
                endpoint_bias_RW_variance=float(np.var(biases,ddof=1)),endpoint_bias_RW_expected=sigma**2*T,
                integrated_bias_angle_variance=float(np.var(rwangles,ddof=1)),left_endpoint_expected=sigma**2*h**3*(nb-1)*nb*(2*nb-1)/6,continuous_Brownian_reference=sigma**2*T**3/3)
        if arm.get('slip'):noise_stats[arm['name']]=dict(events=events,eligible_intervals=eligible,expected_events=eligible*(-math.expm1(-(-math.log1p(-.01)/.2)*arm['dt'])),note='Only64 seeds, few tail events; no Gaussian match/robustness claim.')
    one=np.load(P/'INDEPENDENT_ONE_STEP.npz');sampleQ=np.cov(one['noise'],rowvar=False)
    sample_prediction=-one['G']@sampleQ@one['B'];emp=one['empirical_C'];analytic=one['C']
    # Product covariance sampling SE for iid Gaussian pairs; descriptive, not a new gate.
    predP=one['G']@one['Q']@one['G'].T;se=np.sqrt((np.diag(predP)*float(one['R'])+analytic**2)/4096)
    z=np.divide(emp-analytic,se,out=np.zeros(6),where=se>0)
    onecheck=dict(preregistered_C_relative_gate_met=False,empirical_C_relative_error=float(np.linalg.norm(emp-analytic)/np.linalg.norm(analytic)),
        sample_noise_covariance=sampleQ,sample_covariance_predicted_C=sample_prediction,
        nonlinear_vs_sample_linear_relative_error=float(np.linalg.norm(sample_prediction-emp)/np.linalg.norm(emp)),
        analytic_sampling_SE=se,standardized_C_differences=z,
        explanation='Keep failed15% criterion. Drawn finite sample has off-diagonal noise covariance; empirical nonlinear C agrees with finite-sample linear prediction, not population expectation within15%. No sample/seed expansion.')
    V.write('SUMMARY_VALIDATED.json',corrections);V.write('VALIDITY.json',dict(groups=groups,failures=failures,max_symmetry_error=max_sym,independent_block_gain_max_difference=Kmax,independent_block_innovation_variance_max_difference=Smax,independent_block_posterior_max_difference=postmax))
    V.write('DT_AND_INITIALIZATION.json',dict(noise_dt=noise_stats,initial_distribution=initial_stats));V.write('ONE_STEP_INTERPRETATION.json',onecheck)
    after=[]
    for name in ('D_bias_asymmetry','B4_prior_matched','B3_pair_measured','B1_gyro_wheel_update'):
        arm=next(a for a in V.arms() if a['name']==name)
        with np.load(P/'raw'/f'{name}_81000.npz') as z:
            inp={k[7:]:z[k] for k in z.files if k.startswith('sensor_')}
            try:
                out=V.run_filter_v2(V.config(arm),None,inp,{}, {},z['initial_state'],z['initial_prior']);after.append(dict(arm=name,accepted=True,minimum_eigenvalue=float(np.linalg.eigvalsh(out['cov_full']).min())))
            except FloatingPointError as exc:after.append(dict(arm=name,accepted=False,error=str(exc)))
    V.write('COVARIANCE_GUARD_AFTER.json',dict(cases=after))
    print('RECLASSIFIED',len(failures),'INVALID RUNS; no new MC.');print(V.plain(onecheck));print(after);print(V.plain(noise_stats))

if __name__=='__main__':main()
