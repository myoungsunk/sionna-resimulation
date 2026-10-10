"""Bounded stage2 CPU diagnostics. No RF, no production options or model edits."""
import argparse, json, hashlib, math, sys, subprocess
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy.stats import chi2
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import sensor_v2 as V
from qclean_uwb.drivesim.filters import FilterConfig, CHI2_1_999
from qclean_uwb.drivesim.filter_v2 import SensorV2Filter,transition,odometry_model,correlated_update,run_filter_v2
OUT=ROOT/'results/SENSOR_V2_STAGE2_20261008'
ORIGINAL=Path('D:/SLAM_bot/artifacts/DRIVE_SIM_SENSOR_V2_20261008_01a11a01/checkout')
REV='2337c33fe25917029c2aa95973e6ae7672386a5e'

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def plain(x):
    if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [plain(v) for v in x]
    if isinstance(x,np.generic):return plain(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x
def write(name,x):
    (OUT/name).write_text(json.dumps(plain(x),indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def motion(route,dt):
    if route=='straight':segments=[(12,.2,0)]
    elif route=='speed':segments=[(4,.1,0),(4,.2,0),(4,.35,0)]
    else:segments=[(2,.2,0),(2,.35,0),(2,0,.4),(2,0,-.4),(2,.2,.2),(2,-.1,-.2)]
    d=[0.];a=[0.]
    for duration,v,w in segments:d.extend([v*dt]*round(duration/dt));a.extend([w*dt]*round(duration/dt))
    d=np.array(d);a=np.array(a);t=np.arange(len(d))*dt
    # Independent arc integration: sine/cosine endpoint differences, no V.integrate.
    pose=np.zeros((len(d),3))
    for k in range(1,len(d)):
        old=pose[k-1];new=old[2]+a[k]
        inc=d[k]*np.array([math.cos(old[2]),math.sin(old[2])]) if a[k]==0 else d[k]/a[k]*np.array([math.sin(new)-math.sin(old[2]),math.cos(old[2])-math.cos(new)])
        pose[k,:2]=old[:2]+inc;pose[k,2]=new
    return t,d,a,pose

def arms():
    rows=[]
    def add(name,**kw):rows.append(dict(name=name,route='mixed',dt=.2,condition='noise_pair',q='commanded',correlation='full',init='all_exact',odom=True,parameters={},**kw))
    # Update defaults via dictionary union so explicit options never conflict.
    def a(name,**kw):
        row=dict(name=name,route='mixed',dt=.2,condition='noise_pair',q='commanded',correlation='full',init='all_exact',odom=True,parameters={});row.update(kw);rows.append(row)
    a('B0_no_error',condition='none')
    a('B1_gyro_propagation',condition='gyro_noise',odom=False)
    a('B1_gyro_wheel_update',condition='gyro_noise')
    a('B2_wheel',condition='wheel_noise')
    a('B3_pair_commanded')
    a('B3_pair_measured',q='measured')
    a('B4_prior_matched',condition='all',init='prior_matched')
    for mode in ('full','wheel_only','gyro_only','none'):a('C_'+mode,condition='all',init='prior_matched',correlation=mode)
    for term,value in [('gyro_bias',math.radians(.12)),('gyro_sf',.0104),('wheel_asymmetry',.0064)]:
        a('D_'+term+'_known',condition=term,init='all_exact',parameters={term:value})
        a('D_'+term+'_unknown_initial',condition=term,init='pose_exact',parameters={term:value})
    a('D_bias_asymmetry',condition='bias_asymmetry',init='pose_exact',parameters={'gyro_bias':math.radians(.12),'wheel_asymmetry':.0064})
    for known in (False,True):a('D_wheelbase_'+('known' if known else 'unknown'),condition='all',parameters={'wheelbase':.0075},known_wheelbase=.0075 if known else 0.)
    a('D_common_scale',condition='all',parameters={'common_scale':.01})
    a('D_production_initial',condition='all',init='production')
    for route in ('straight','speed','mixed'):a('E_identify_'+route,route=route,condition='all',init='pose_exact',parameters={'gyro_bias':math.radians(.12),'gyro_sf':.0104,'wheel_asymmetry':.0064})
    for dt in (.1,.2,.4):
        a('E_dt_'+str(dt),dt=dt)
        a('E_RW_'+str(dt),dt=dt,condition='all',rw=1e-4)
    a('E_slip',condition='all',slip=True)
    return rows

def config(arm):
    active=V.CONDITIONS[arm['condition']]
    return FilterConfig(model_version='sensor-v2',dt=arm['dt'],use_range=False,use_s=False,use_odom_heading=arm['odom'],bias_rw_std=arm.get('rw',0.),known_wheelbase_error=arm.get('known_wheelbase',0.),
       k_s=2e-5 if 'wheel_noise' in active else 0.,k_theta=1e-4 if 'wheel_noise' in active else 0.,k_stheta=1e-5 if 'wheel_noise' in active else 0.,gyro_N_rad_sqrt_s=math.radians(.015) if 'gyro_noise' in active else 0.)

class Diagnostic(SensorV2Filter):
    """Test-only Q and C ablations; never wired into production configuration."""
    def __init__(self,cfg,x0,P0,q_schedule,mode):super().__init__(cfg,None,x0,P0);self.q_schedule=q_schedule;self.mode=mode;self.index=0
    def step(self,d,g,o,dt):
        self.index+=1;c=self.comps[0];cfg=self.cfg;xp=c.x.copy();previousP=c.P.copy()
        c.x,F,G=transition(xp,d,g,dt,cfg.wheel_base/(1+cfg.known_wheelbase_error));pred=c.x.copy()
        Q=np.diag([cfg.k_s*abs(d),cfg.gyro_N_rad_sqrt_s**2*dt,cfg.k_theta*abs(o)+cfg.k_stheta*abs(d)]) if self.q_schedule is None else np.diag(self.q_schedule[self.index])
        P=F@previousP@F.T+G@Q@G.T
        h,H,B=odometry_model(xp,d,g,dt,cfg.wheel_base,cfg.known_wheelbase_error)
        parts=np.column_stack([-G[:,j]*Q[j,j]*B[j] for j in range(3)])
        C=parts.sum(1) if self.mode=='full' else (parts[:,0] if self.mode=='wheel_only' else (parts[:,1] if self.mode=='gyro_only' else np.zeros(6)))
        R=float(B@Q@B);S=float(H@P@H+R+2*H@C);y=o-h;K=(P@H+C)/S if S>1e-20 else np.zeros(6)
        status='disabled';c.P=P
        if cfg.use_odom_heading:
            if S<=1e-20:status='zero_variance'
            elif y*y/S>CHI2_1_999:status='rejected';self.stats['o_rejected']+=1
            else:c.x,c.P,_=correlated_update(c.x,P,H,y,R,C);status='applied';self.stats['o_updates']+=1
        # Independent block-Gaussian conditional covariance, distinct from Joseph.
        reference=P-np.outer(P@H+C,P@H+C)/S if status=='applied' else P
        posterior_error=float(np.max(np.abs(reference-c.P)))
        joint=np.block([[P,C[:,None]],[C[None,:],np.array([[R]])]])
        mineig=float(np.linalg.eigvalsh(joint).min())
        c.P[3,3]+=cfg.bias_rw_std**2*dt
        return dict(innovation=y,R=R,S=S,status=status,H=H,C=C,Q=Q,F=F,G=G,B=B,K=K,predicted_state=pred,predicted_covariance=P,joint_min_eigenvalue=mineig,posterior_reference_error=posterior_error,C_parts=parts)

def run(arm,seed):
    t,d,a,pose=motion(arm['route'],arm['dt']);cfg=config(arm);std=np.array(cfg.p0_std)
    parameters=dict(gyro_bias=0.,gyro_sf=0.,wheel_asymmetry=0.,wheelbase=0.,common_scale=0.);parameters.update(arm['parameters'])
    if arm['init']=='prior_matched':
        # Independent draw of actual calibration, consistent with the stated prior.
        actual=np.random.default_rng([20261008,seed,71]).normal(size=3)*std[3:]
        parameters.update(zip(('gyro_bias','gyro_sf','wheel_asymmetry'),actual))
    elif arm['init']=='production':parameters=None
    sensor=V.SensorV2Config(condition=arm['condition'],level=1,common_scale=arm['parameters'].get('common_scale',0.),bias_rw_rad_s_sqrt_s=arm.get('rw',0.),slip_mode='time' if arm.get('slip') else 'off')
    inp,ev=V.generate(t,d,a,sensor,seed,parameters)
    p=dict(zip(ev['parameter_names'],ev['true_parameters']))
    truth=np.column_stack([pose,ev['true_bias_rad_s'],np.full(len(t),p['gyro_sf']),np.full(len(t),p['wheel_asymmetry'])])
    x0=np.zeros(6);P0=np.zeros((6,6))
    if arm['init']=='all_exact':x0=truth[0].copy()
    elif arm['init']=='prior_matched':
        x0[:3]=pose[0]-np.random.default_rng([20261008,seed,72]).normal(size=3)*std[:3];P0=np.diag(std**2)
    elif arm['init']=='production':
        x0[:3]=pose[0]+V.rng(seed,'initial').normal(size=3)*std[:3];P0=np.diag(std**2)
    else:P0[3:,3:]=np.diag(std[3:]**2)
    # Public predetermined command schedule, not generated noise / truth Q.
    q=np.column_stack([cfg.k_s*np.abs(d),cfg.gyro_N_rad_sqrt_s**2*inp['dt_s'],cfg.k_theta*np.abs(a)+cfg.k_stheta*np.abs(d)])
    f=Diagnostic(cfg,x0,P0,q if arm['q']=='commanded' else None,arm['correlation'])
    est=[x0.copy()];cov=[P0.copy()];trace=[]
    for k in range(1,len(t)):
        rec=f.step(inp['ds_odom'][k],inp['dtheta_gyro'][k],inp['dtheta_odom'][k],inp['dt_s'][k]);trace.append(rec)
        x,P=f.mean_cov();est.append(x.copy());cov.append(P.copy())
    est=np.array(est);cov=np.array(cov);e=truth-est;e[:,2]=np.arctan2(np.sin(e[:,2]),np.cos(e[:,2]));mask=t>=2.
    eig=np.linalg.eigvalsh(cov)
    if not np.isfinite(est).all() or not np.isfinite(cov).all() or eig.min() < -1e-10:raise ValueError('INVALID_POSTERIOR')
    # Empirical covariance analysis uses independent seeds at endpoint.
    def subspace(indices):
        P=cov[-1][np.ix_(indices,indices)];err=e[-1,indices];values,U=np.linalg.eigh(P)
        active=values>max(1e-14,values.max()*1e-10);df=int(active.sum());z=U.T@err
        nees=float(np.sum(z[active]**2/values[active])) if df else None
        return dict(df=df,nees=nees,coverage95=bool(nees<=chi2.ppf(.95,df)) if df else None,lower_tail=bool(nees<chi2.ppf(.025,df)) if df else None,upper_tail=bool(nees>chi2.ppf(.975,df)) if df else None,nullspace_error_norm=float(np.linalg.norm(z[~active])))
    met=dict(pos_rmse_m=float(np.sqrt(np.mean(np.sum(e[mask,:2]**2,1)))),heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[mask,2]**2)))),endpoint_error=e[-1],endpoint_covariance=cov[-1],pose=subspace([0,1,2]),full=subspace(list(range(6))),
       odom_rejected=sum(r['status']=='rejected' for r in trace),odom_applied=sum(r['status']=='applied' for r in trace),zero_variance=sum(r['status']=='zero_variance' for r in trace),
       posterior_min_eigenvalue=float(eig.min()),joint_min_eigenvalue=min(r['joint_min_eigenvalue'] for r in trace),independent_posterior_max_difference=max(r['posterior_reference_error'] for r in trace),
       bias_error_endpoint=float(e[-1,3]),SF_error_endpoint=float(e[-1,4]),asymmetry_error_endpoint=float(e[-1,5]),slip_events=int(ev['slip_event'].sum()),
       variance_approx_relative_norm=float(np.linalg.norm(np.stack([np.diag(r['Q']) for r in trace])-q[1:])/max(np.linalg.norm(q[1:]),1e-30)))
    path=OUT/'raw'/f"{arm['name']}_{seed}.npz"
    archive=dict(time_s=t,truth_state=truth,estimate_state=est,covariance_full=cov,error_state=e,evaluation_mask=mask,initial_state=x0,initial_prior=P0,declared_Q_schedule=q,
      range_status=np.full(len(t),'disabled'),s_status=np.full(len(t),'disabled'))
    archive.update({'sensor_'+k:np.asarray(v) for k,v in inp.items()});archive.update({'evaluation_'+k:np.asarray(v) for k,v in ev.items()})
    archive.update({'odom_'+k:np.array([r[k] for r in trace]) for k in trace[0]})
    with path.open('xb') as stream:np.savez_compressed(stream,**archive)
    return met,inp,ev,est,cov,trace

def aggregate(rows):
    summary={}
    for arm in arms():
        rs=[r['metrics'] for r in rows if r['arm']==arm['name']]
        if not rs:continue
        errs=np.array([r['endpoint_error'] for r in rs]);Ps=np.array([r['endpoint_covariance'] for r in rs]);meanP=Ps.mean(0)
        centered=np.cov(errs,rowvar=False);second=errs.T@errs/len(errs)
        val=dict(n=len(rs),pos_rmse_mean=float(np.mean([r['pos_rmse_m'] for r in rs])),heading_rmse_mean_deg=float(np.mean([r['heading_rmse_deg'] for r in rs])),
           pos_rmse_worst_seed=float(max(r['pos_rmse_m'] for r in rs)),heading_rmse_worst_seed_deg=float(max(r['heading_rmse_deg'] for r in rs)),
           endpoint_bias=errs.mean(0),actual_centered_covariance=centered,actual_second_moment=second,mean_filter_covariance=meanP,
           actual_to_filter_pose_trace=float(np.trace(second[:3,:3])/np.trace(meanP[:3,:3])) if np.trace(meanP[:3,:3])>0 else None,
           odom_rejected=sum(r['odom_rejected'] for r in rs),zero_variance=sum(r['zero_variance'] for r in rs),slip_events=sum(r['slip_events'] for r in rs),
           posterior_reference_max=max(r['independent_posterior_max_difference'] for r in rs),joint_min=min(r['joint_min_eigenvalue'] for r in rs),q_approx_relative_norm_mean=float(np.mean([r['variance_approx_relative_norm'] for r in rs])))
        for key in ('pose','full'):
            ranks=sorted(set(r[key]['df'] for r in rs));v=[r[key]['nees'] for r in rs if r[key]['nees'] is not None]
            info=dict(ranks=ranks,nullspace_error_max=max(r[key]['nullspace_error_norm'] for r in rs),n_nees=len(v))
            if v and len(ranks)==1:
                df=ranks[0];mean=float(np.mean(v));n=len(v);ci=chi2.ppf([.025,.975],n*df)/n
                draw=np.random.default_rng(20261008).choice(v,size=(2000,n),replace=True).mean(1)
                info.update(mean_nees=mean,expected=df,mean_null_acceptance_interval95=ci,seed_bootstrap_ci95=np.quantile(draw,[.025,.975]),inside_mean_null_interval=bool(ci[0]<=mean<=ci[1]),coverage95=float(np.mean([r[key]['coverage95'] for r in rs])),lower_tail=float(np.mean([r[key]['lower_tail'] for r in rs])),upper_tail=float(np.mean([r[key]['upper_tail'] for r in rs])))
            val[key]=info
        summary[arm['name']]=val
    return summary

def independent_checks():
    # New sensor geometry and shared input realization, not old local Jacobian tests.
    t=np.arange(61)*.2;d=np.r_[0.,np.full(60,.04)];a=np.r_[0.,np.full(60,.03)]
    cfg=V.SensorV2Config(condition='all',gyro_N_rad_sqrt_s=0.,k_distance_m=0.,k_yaw_rad=0.,k_yaw_distance_rad2_m=0.,slip_mode='off')
    params=dict(gyro_bias=.001,gyro_sf=.02,wheel_asymmetry=.08,wheelbase=.0075,common_scale=.01)
    inp,ev=V.generate(t,d,a,cfg,99001,params);b=.287/(1+.0075);c=.01;eps=.08
    expectd=(1+c)*(d+eps*b*a/4);expecto=(1+c)*(a+eps*d/b)/(1+.0075);expectg=(1+.02)*a+.001*inp['dt_s']
    max_sensor=max(np.max(abs(inp['ds_odom']-expectd)),np.max(abs(inp['dtheta_odom']-expecto)),np.max(abs(inp['dtheta_gyro']-expectg)))
    # One-step nonlinear cross-covariance with calibrated nonzero asymmetry/SF;
    # 4096 fresh independent seeds, one step only, no localization campaign expansion.
    x=np.array([0.,0.,.3,.001,.02,.08]);Q=np.diag([2e-5*.04,math.radians(.015)**2*.2,1e-4*.03+1e-5*.04])
    dclean=.04+.08*.287*.03/4;gclean=1.02*.03+.001*.2
    ideal,F,G=transition(x,dclean,gclean,.2,.287);_,H,B=odometry_model(x,dclean,gclean,.2,.287)
    # Independent exact arc endpoint from true ds/a.
    true=np.r_[.04/.03*(math.sin(.33)-math.sin(.3)),.04/.03*(math.cos(.3)-math.cos(.33)),.33,.001,.02,.08]
    errors=[];vs=[];noise=[]
    ng=np.random.default_rng(20261008).normal(size=(4096,3))*np.sqrt(np.diag(Q))
    for n in ng:
        predicted,_,_=transition(x,dclean+n[0],gclean+n[1],.2,.287)
        actualo=.03+.08*.04/.287+n[2]
        h,_,_=odometry_model(x,dclean+n[0],gclean+n[1],.2,.287)
        errors.append(true-predicted);vs.append(actualo-h);noise.append(n)
    C=-sum((G[:,j]*Q[j,j]*B[j] for j in range(3)),start=np.zeros(6));R=sum(B[j]**2*Q[j,j] for j in range(3))
    empirical=np.cov(np.column_stack([errors,vs]),rowvar=False)[:6,6]
    A=np.array([[.5,.5],[-1/.287,1/.287]]);qlr=np.array([[Q[0,0]+.287**2*Q[2,2]/4,Q[0,0]-.287**2*Q[2,2]/4],[Q[0,0]-.287**2*Q[2,2]/4,Q[0,0]+.287**2*Q[2,2]/4]])
    covariance_transform_error=float(np.max(abs(A@qlr@A.T-np.diag([Q[0,0],Q[2,2]]))))
    np.savez_compressed(OUT/'INDEPENDENT_ONE_STEP.npz',noise=np.array(noise),prediction_errors=np.array(errors),observation_noise=np.array(vs),C=C,empirical_C=empirical,Q=Q,G=G,B=B,R=R)
    return dict(sensor_equation_max_error=float(max_sensor),wheel_covariance_transform_max_error=covariance_transform_error,C=C,empirical_C=empirical,C_relative_error=float(np.linalg.norm(empirical-C)/np.linalg.norm(C)),R=R,empirical_R=float(np.var(vs,ddof=1)),one_step_samples=4096,
      C_wheel=-G[:,0]*Q[0,0]*B[0],C_gyro=-G[:,1]*Q[1,1]*B[1],known_calibration_arc_max_error=float(np.max(abs(ideal-true))),
      rank={route:int(np.linalg.matrix_rank(np.column_stack([-np.diff(motion(route,.2)[0]),-motion(route,.2)[2][1:],motion(route,.2)[1][1:]/.287]))) for route in ('straight','speed','mixed')})

def prepare():
    if OUT.exists():raise FileExistsError('ADDITIVE_OUTPUT_REQUIRED')
    OUT.mkdir(parents=True);(OUT/'raw').mkdir()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if head!=REV:raise ValueError('REVISION_DRIFT')
    copied=json.loads((ROOT.parent/'COPIED_SOURCE_MANIFEST.json').read_text())
    source_ok=all(sha(ORIGINAL/x['path'])==x['sha256'] for x in copied['files'])
    if not source_ok:raise ValueError('ORIGINAL_SOURCE_CHANGED_SINCE_COPY')
    paths=list((ROOT/'src/qclean_uwb/drivesim').glob('*.py'))+list((ROOT/'tests').glob('test_sensor_v2*.py'))+list(ROOT.parent.glob('*.*'))
    paths += [ORIGINAL/x['path'] for x in copied['files']]+list((ORIGINAL/'results/SENSOR_V2_20261008').rglob('*'))
    hashes={str(p):sha(p) for p in paths if p.is_file()}
    write('PLAN.json',dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),revision=head,branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),dirty=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
      original_uncommitted_source_manifest=str(ROOT.parent/'COPIED_SOURCE_MANIFEST.json'),original_source_manifest_matches=source_ok,protected_hashes=hashes,script_sha256=sha(__file__),
      seeds=list(range(81000,81064)),arms=arms(),T_seconds=12,default_dt=.2,total_runs=64*len(arms()),raw_est_cov_input_innovation_status_mask=True,
      matched='Declared command schedule fixes Q before sensor generation; estimator sees public schedule only, never generated noise or evaluation true Q. Nonlinear EKF remains a first-order approximation.',
      measured='Unmodified sensor-v2 formula uses measured increments, distinct from commanded-Q diagnostic.',
      initial='all_exact: full6 true state and P0=0, explicit externally calibrated diagnostic. prior_matched: actual calibration Gaussian with default prior std, independent pose error Gaussian. pose_exact: pose exact, actual nuisance fixed and estimate0 with default nuisance prior. production: existing pose-only RNG, nuisance estimate0 and signed sensitivity parameters.',
      criteria='No RF/production PASS. Algebra tolerance1e-10. One-step empirical C/R within15% diagnostic. Endpoint seed NEES null mean interval95 for actual rank; coverage/tails reported with finite-sample uncertainty. Singular P: eigen subspace rank threshold max(1e-14,lambda_max*1e-10), nullspace error separate; no regularization.',
      statistical_unit='independent seed/run; endpoint MC inferential, t>=2 trajectory RMSE descriptive; one_step4096 only, no expansion',
      command='py -3.10 -X utf8 scripts/drive_sim/validate_sensor_v2_stage2.py --run',stop='After stage2, no L1/L2 or RF'))
    print('PLAN FROZEN',len(arms()),'arms',64*len(arms()),'runs',len(hashes),'protected files',flush=True)

def execute():
    plan=json.loads((OUT/'PLAN.json').read_text())
    if sha(__file__)!=plan['script_sha256']:raise ValueError('SCRIPT_DRIFT')
    if not all(sha(p)==h for p,h in plan['protected_hashes'].items()):raise ValueError('INPUT_DRIFT')
    check=independent_checks();write('INDEPENDENT_CHECKS.json',check)
    rows=[];failures=[];regression=None
    for arm in plan['arms']:
        for seed in plan['seeds']:
            try:
                met,inp,ev,est,cov,trace=run(arm,seed);rows.append(dict(arm=arm['name'],seed=seed,metrics=met))
                if arm['name']=='B3_pair_measured' and seed==plan['seeds'][0]:
                    orig=run_filter_v2(config(arm),None,inp,{}, {},np.zeros(6),np.zeros((6,6)))
                    regression=dict(state_max_error=float(np.max(abs(est-orig['est']))),covariance_max_error=float(np.max(abs(cov-orig['cov_full']))))
            except Exception as exc:failures.append(dict(arm=arm['name'],seed=seed,error=repr(exc)))
        write('RUNS.json',dict(rows=rows,failures=failures));print('DONE',arm['name'],flush=True)
    summary=aggregate(rows);write('SUMMARY.json',summary)
    preserved=all(sha(p)==h for p,h in plan['protected_hashes'].items())
    write('STATUS.json',dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),completed_runs=len(rows),expected_runs=plan['total_runs'],failures=failures,original_source_results_preserved=preserved,production_measured_regression=regression,scientific_PASS=False,F01='OPEN',F02='OPEN',next_stage_started=False))
    print('COMPLETE',len(rows),'FAILURES',len(failures),'PRESERVED',preserved,flush=True)
    if failures or not preserved:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');args=p.parse_args()
    if args.prepare:prepare()
    elif args.run:execute()
    else:p.error('select --prepare or --run')
