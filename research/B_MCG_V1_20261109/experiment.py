"""Reproducible B-MCG source-model checks and true recursive research replay."""
from __future__ import annotations
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import argparse, json, sys, time, hashlib,datetime
from dataclasses import asdict,replace
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/FP_NATIVE_B_CAUSAL_ABLATION_20261108'))
from fp_ns_ablation import load_original_replay,identical_input_condition,metrics
from mcg import Config,Monitor,covariance_update,weights,wrap

STRATA=('B_FROZEN','B_BIAS_COV')
ALLOWED=('t','pose_id','ds','gy','dt','x0','P0','muMB','muBASE','R','D')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,d):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def read_npz(p):
    with np.load(p,allow_pickle=False) as f:return {k:f[k] for k in f.files}
def context(repo=ROOT):return load_original_replay(repo)

def runtime_receipt():
    import scipy
    return {'runtime_code_sha256':{p.name:sha(p) for p in (Path(__file__),Path(__file__).with_name('mcg.py'))},
        'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':sys.version,
        'numpy':np.__version__,'scipy':scipy.__version__,'execution_git_sha':os.environ.get('GITHUB_SHA','LOCAL_RESEARCH')}

def assert_receipt(receipt):
    assert receipt['runtime_code_sha256']==runtime_receipt()['runtime_code_sha256'],'CODE_CHANGED_DURING_RUN'

def packet_for(r45,route,stratum,archives):
    raw=r45.data(route+'_B0_Full_10','online.npz')
    B,native,zN,zB=identical_input_condition(raw,r45,route)
    packet={k:np.asarray(raw[k]).copy() for k in ALLOWED};packet['z']=zB.copy()
    if stratum=='B_BIAS_COV':
        fit=json.loads((archives/route/'RESULTS.json').read_text())['fit']
        packet['muMB']+=np.asarray(fit['delta_mu']);packet['muBASE']+=np.asarray(fit['delta_mu'])
        packet['R']+=np.asarray(fit['R_add_diag'])
    if set(packet)!=set(ALLOWED)|{'z'}:raise AssertionError('RUNTIME_WHITELIST')
    return packet,B,native

def config_for(tau=3.,span=5.):
    # Pre-score fixed conservative floors. P2's training-only empirical envelopes
    # are all below these floors, so one identical deployed config serves all routes.
    return Config(span_s=span,minimum_s=min(2.,span),tau_r=tau,tau_s=tau,tau_joint=float(np.sqrt(2)*tau))

def compare_trace(a,b):
    errors={}
    for key in ('x','P','prior','Pprior','h','H','mu','Reff','K','nu','S','mask'):
        aa=np.asarray(a[key]);bb=np.asarray(b[key]);assert aa.shape==bb.shape,(key,'SHAPE')
        errors[key]=float(np.max(abs(aa.astype(float)-bb.astype(float))/np.maximum(1.,abs(bb.astype(float)))))
    assert max(errors.values())<=1e-10,errors
    assert np.array_equal(a['mask'],b['mask'])
    return errors

def baseline(route,archives,out):
    r45,core,online,model,hashes=context();out.mkdir(parents=True,exist_ok=True);report={}
    for stratum in STRATA:
        packet,_,_=packet_for(r45,route,stratum,archives)
        controls={k:packet[k] for k in ('ds','gy','dt')};controls['x0']=packet['x0'][:3]
        tr=online.replay(packet,controls,'W0',core,model,r45.SPEC)
        old=read_npz(archives/route/f'{route}_{stratum}.npz')
        report[stratum]=compare_trace(tr,old)
        np.savez_compressed(out/f'{route}_{stratum}.npz',**tr,t=packet['t'],pose_id=packet['pose_id'])
        print('BASELINE_PARITY_PASS',route,stratum,max(report[stratum].values()),flush=True)
    dump(out/f'{route}_PARITY.json',{'status':'PASS','route':route,'strata':report,'source_hashes':hashes,
        'input_whitelist':list(ALLOWED)+['z'],'archive_sha256':{s:sha(archives/route/f'{route}_{s}.npz') for s in STRATA}})

def save_profiles(p,records,t,pose_id,cfg):
    n=len(records)
    def arr(key,default,typ=float):return np.asarray([v.get(key,default) for v in records],dtype=typ)
    np.savez_compressed(p,scores=arr('scores',[np.nan]*3),valid=arr('valid_channels',[False,False],bool),
       states=arr('status','UNKNOWN','U40'),reasons=arr('reason','UNSET','U50'),
       rank=arr('rank',0,int),bound_hit=arr('bound_hit',False,bool),linearity=arr('linearity_sigma',np.nan),
       stationarity=arr('stationarity_per_sample',np.nan),refinements=arr('refinements',0,int),boundary_support=arr('boundary_support',False,bool),
       span=arr('target_span_sigma',[np.nan,np.nan]),theta=arr('theta',[np.nan]*4),candidate_count=arr('candidate_count',0,int),
       profile_cost=arr('profile_cost',np.nan),duration_ms=arr('duration_ms',0.),
       anchor_index=arr('anchor_index',0,int),history_end=arr('history_end',-1,int),
       anchor_sha256=arr('anchor_sha256','','U64'),t=t[:n],pose_id=pose_id[:n],config_json=json.dumps(asdict(cfg),sort_keys=True))

def profiles(route,stratum,archives,out,span=5.,limit=None):
    receipt=runtime_receipt();out.mkdir(parents=True,exist_ok=True)
    if (out/f'{route}.json').exists():raise FileExistsError('COMPLETED_PROFILE_IMMUTABLE')
    dump(out/f'{route}_RUNNING.json',receipt)
    r45,core,online,model,hashes=context();packet,_,_=packet_for(r45,route,stratum,archives)
    tr=read_npz(archives/route/f'{route}_{stratum}.npz');n=len(packet['t']) if limit is None else min(limit,len(packet['t']))
    cfg=config_for(span=span);mon=Monitor(core,model,r45.SPEC,cfg);rows=[];start=time.perf_counter()
    out.mkdir(parents=True,exist_ok=True)
    for k in range(n):
        sc,info=mon.observe(k,packet['t'][k],tr['prior'][k],np.array([packet[x][k] for x in ('ds','gy','dt')]),
            packet['z'][k],packet['muMB'][k],tr['Reff'][k])
        rows.append(dict(info,**{v:sc[v] for v in ('scores','valid_channels','status','reason')}))
        if k%100==0:
            print('PROFILE',route,stratum,k,n,'valid',sum(np.any(r['valid_channels']) for r in rows),'elapsed',round(time.perf_counter()-start,1),flush=True)
            save_profiles(out/f'{route}_PARTIAL.npz',rows,packet['t'],packet['pose_id'],cfg)
    save_profiles(out/f'{route}.npz',rows,packet['t'],packet['pose_id'],cfg)
    states,counts=np.unique([r['status'] for r in rows],return_counts=True)
    reasons,rc=np.unique([r['reason'] for r in rows],return_counts=True)
    lat=np.array([r.get('duration_ms',0) for r in rows])
    assert_receipt(receipt)
    report={'status':'OFFLINE_PROFILE_EXECUTED','route':route,'stratum':stratum,'n':n,'config':asdict(cfg),'config_sha256':cfg.digest(),**receipt,
        'counts':dict(zip(states.tolist(),counts.tolist())),'reason_counts':dict(zip(reasons.tolist(),rc.tolist())),
        'latency_p50_p95_p99_ms':np.quantile(lat,[.5,.95,.99]).tolist(),'elapsed_s':time.perf_counter()-start,
        'archive_sha256':sha(archives/route/f'{route}_{stratum}.npz'),'source_hashes':hashes,
        'scope':'archived B priors; no active recursive guard yet; no current observation in history fit'}
    dump(out/f'{route}.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)

def replay_active(packet,core,online,model,spec,cfg,mode,*,fixed_scores=None):
    n=len(packet['t']);x=packet['x0'].copy();P=packet['P0'].copy();sx=x.copy();sp=P.copy()
    controls={k:packet[k] for k in ('ds','gy','dt')};controls['x0']=packet['x0'][:3]
    mon=Monitor(core,model,spec,cfg)
    dims={'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'h':(2,),'H':(2,4),'mu':(2,),
          'Reff':(2,2),'Rbase':(2,2),'K':(4,2),'nu':(2,),'S':(2,2),'beta':(2,),'scores':(3,),
          'trial_delta':(4,),'actual_delta':(4,),'shadow_x':(4,),'shadow_P':(4,4),'theta':(4,),'target_span':(2,)}
    tr={key:np.full((n,*shape),np.nan) for key,shape in dims.items()}
    for key in ('mask','guard_valid_r','guard_valid_s','used_r','used_s'):tr[key]=np.zeros(n,bool)
    for key in ('latency_ms','guard_ms','gate_nis','nis','actual_used_nis','anchor_index','history_end','rank','linearity','profile_cost'):tr[key]=np.full(n,np.nan)
    tr['status']=np.empty(n,dtype='U40');tr['reason']=np.empty(n,dtype='U50');tr['anchor_sha256']=np.empty(n,dtype='U64')
    for k,z in enumerate(packet['z']):
        start=time.perf_counter_ns()
        # Preserve raw-B legacy shadow exactly, separately from the main guard.
        sx,sp=online.predict(core,sx,sp,k,controls)
        sh,sH=model.batch(sx[None],spec);sh=sh[0];sH=sH[0]
        rr=packet['R'][k];sv=z-sh-packet['muBASE'][k];ss=sH@sp@sH.T+rr
        gate_nis=float(sv@np.linalg.solve(ss,sv));allow=bool(gate_nis<=online.GATE)
        if allow:
            gain=np.linalg.solve(ss,sH@sp).T;sx=sx+gain@sv;sx[2]=wrap(sx[2]);A=np.eye(4)-gain@sH
            sp=A@sp@A.T+gain@rr@gain.T;sp=(sp+sp.T)*.5
        rho=np.linalg.norm(x[:2]-np.asarray(spec['anchor'])[:2]);sig=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
        xp,pp=online.predict(core,x,P,k,controls);h,H=model.batch(xp[None],spec);h=h[0];H=H[0]
        R=packet['R'][k].copy();R[1,1]+=sig**2;mu=packet['muMB'][k];nu=z-h-mu
        # Rejected actual and forced diagnostic trial are recorded separately.
        trial=online.joseph(xp.copy(),pp.copy(),H,nu,R,True,1.)[0]
        gstart=time.perf_counter_ns()
        if mode in ('OFF','DR_ONLY'):
            sc={'status':'OFF','reason':'BASELINE' if mode=='OFF' else 'DR_ONLY','scores':np.full(3,np.nan),'valid_channels':np.zeros(2,bool)};info={}
        else:
            sc,info=mon.observe(k,packet['t'][k],xp,np.array([packet[v][k] for v in ('ds','gy','dt')]),z,mu,R)
        beta,status=weights(sc,cfg,mode)
        if mode=='DR_ONLY':beta[:]=0
        if mode=='NAIVE_YAW_CLIP':
            # Deliberately unsafe diagnostic comparator; never a deployable policy.
            delta=abs(float(wrap(trial[2]-xp[2])))
            beta[:]=1. if delta<=np.radians(.2) else .25
            status='NAIVE_PRIOR_CORRECTION_TEST'
        guard_ms=(time.perf_counter_ns()-gstart)/1e6
        x,P,K,re,used=covariance_update(xp,pp,H,nu,R,beta,allow)
        S=H@pp@H.T+re;S=(S+S.T)*.5
        trial_delta=trial-xp;trial_delta[2]=wrap(trial_delta[2])
        actual_delta=x-xp;actual_delta[2]=wrap(actual_delta[2])
        actual_nis=float(nu[used]@np.linalg.solve(S[np.ix_(used,used)],nu[used])) if len(used) else np.nan
        for key,val in [('x',x),('P',P),('prior',xp),('Pprior',pp),('h',h),('H',H),('mu',mu),('Reff',re),('Rbase',R),('K',K),('nu',nu),('S',S),
            ('beta',beta),('scores',sc['scores']),('trial_delta',trial_delta),('actual_delta',actual_delta),('shadow_x',sx),('shadow_P',sp),('theta',info.get('theta',np.full(4,np.nan))),('target_span',info.get('target_span_sigma',np.full(2,np.nan))),
            ('mask',allow),('used_r',0 in used),('used_s',1 in used),('guard_valid_r',sc['valid_channels'][0]),('guard_valid_s',sc['valid_channels'][1]),
            ('gate_nis',gate_nis),('nis',float(nu@np.linalg.solve(S,nu))),('actual_used_nis',actual_nis),('status',status),('reason',sc['reason']),('guard_ms',guard_ms),
            ('anchor_index',info.get('anchor_index',-1)),('history_end',info.get('history_end',-1)),('rank',info.get('rank',0)),('linearity',info.get('linearity_sigma',np.nan)),('profile_cost',info.get('profile_cost',np.nan)),('anchor_sha256',info.get('anchor_sha256',''))]:tr[key][k]=val
        tr['latency_ms'][k]=(time.perf_counter_ns()-start)/1e6
        if k%200==0:print('REPLAY',mode,k,n,flush=True)
    assert np.isfinite(tr['x']).all() and np.isfinite(tr['P']).all()
    assert np.linalg.eigvalsh(tr['P']).min()>-1e-12
    return tr

def active(route,stratum,archives,out,mode,tau=2.,span=5.,policy_role='predeclared_diagnostic',policy_lock=None):
    receipt=runtime_receipt();out.mkdir(parents=True,exist_ok=True)
    if (out/f'{route}_{mode}.json').exists():raise FileExistsError('COMPLETED_REPLAY_IMMUTABLE')
    receipt['execution_policy_role']=policy_role
    receipt['policy_lock_sha256']=sha(policy_lock) if policy_lock else None
    dump(out/f'{route}_{mode}_RUNNING.json',receipt)
    r45,core,online,model,hashes=context();packet,_,_=packet_for(r45,route,stratum,archives)
    cfg=config_for(tau,span);out.mkdir(parents=True,exist_ok=True)
    tr=replay_active(packet,core,online,model,r45.SPEC,cfg,mode)
    old=read_npz(archives/route/f'{route}_{stratum}.npz')
    assert np.array_equal(tr['mask'],old['mask']),'LEGACY_GATE_CHANGED'
    parity=compare_trace(tr,old) if mode in ('OFF','OBSERVE_ONLY') else None
    # Evaluator is loaded only once all online recursion has completed.
    ev=r45.data(route+'_B0_Full_10','evaluator.npz')
    assert np.array_equal(ev['t'],packet['t']) and np.array_equal(ev['pose_id'],packet['pose_id'])
    score=metrics(tr['x'],tr['P'],ev['truth'],tr['used_r']|tr['used_s'])
    base=metrics(old['x'],old['P'],ev['truth'],old['mask'])
    score['guard_damped_legacy_accepted']=int(np.sum(tr['mask']&np.any(tr['beta']<1,axis=1)))
    score['guard_valid_any']=int(np.sum(tr['guard_valid_r']|tr['guard_valid_s']))
    score['legacy_rejections']=int(np.sum(~tr['mask']))
    score['heading_rmse_ratio']=score['heading_rmse_deg']/base['heading_rmse_deg'];score['xy_rmse_ratio']=score['xy_rmse_cm']/base['xy_rmse_cm']
    score['latency_total_p50_p95_p99_ms']=np.quantile(tr['latency_ms'],[.5,.95,.99]).tolist()
    score['latency_guard_p50_p95_p99_ms']=np.quantile(tr['guard_ms'],[.5,.95,.99]).tolist()
    np.savez_compressed(out/f'{route}_{mode}.npz',**tr,t=packet['t'],pose_id=packet['pose_id'])
    assert_receipt(receipt)
    dump(out/f'{route}_{mode}.json',{'status':'EXECUTED_RESEARCH_REPLAY','route':route,'stratum':stratum,'mode':mode,'config':asdict(cfg),
         'config_sha256':cfg.digest(),'metrics':score,'baseline':base,'OFF_parity':parity,'source_hashes':hashes,**receipt,
         'trace_sha256':sha(out/f'{route}_{mode}.npz'),'archive_sha256':sha(archives/route/f'{route}_{stratum}.npz'),
         'performance_adoption':'NOT_INFERRED_FROM_EXECUTION_SUCCESS','finite_profile_search':'No global feasibility proof'})
    print(json.dumps(score),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['baseline','profiles','active']);p.add_argument('--route',required=True,choices=['R2','R4','R5']);p.add_argument('--stratum',choices=STRATA,default='B_FROZEN');p.add_argument('--archives',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--mode',default='OFF',choices=['OFF','OBSERVE_ONLY','ACTIVE_R','ACTIVE_S','ACTIVE_RS','DR_ONLY','NAIVE_YAW_CLIP']);p.add_argument('--tau',type=float,default=2.);p.add_argument('--span',type=float,default=5.);p.add_argument('--limit',type=int);p.add_argument('--policy-role',default='predeclared_diagnostic');p.add_argument('--policy-lock',type=Path);a=p.parse_args()
    if a.stage=='baseline':baseline(a.route,a.archives,a.out)
    elif a.stage=='profiles':profiles(a.route,a.stratum,a.archives,a.out,a.span,a.limit)
    else:active(a.route,a.stratum,a.archives,a.out,a.mode,a.tau,a.span,a.policy_role,a.policy_lock)
