#!/usr/bin/env python3
"""Read-only audit of archived EKF runs; no new ray tracing or performance tuning.
The saved S2/S3 traces are inputs, not a claim of a fresh nonlinear replay.
All computed output and selected input bytes are retained under --out.
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, hashlib, io, json, math, os, platform, sys, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

REPO='myoungsunk/sionna-resimulation'
PIN='d70360a4cac98de47c3365244a08112bf6414e28'
BASE='research/MBVAR_PRR_001_20261103'
GATE=9.210340371976184
C95=3.841458820694124

def digest(b): return hashlib.sha256(b).hexdigest()
def wrap(x): return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def dump(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def load_npz(p):
    with np.load(p,allow_pickle=False) as d: return dict(d)
def table(p,rows):
    pd.DataFrame(rows).to_csv(p,index=False,float_format='%.15g')

def acquire(out):
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    def get(url,auth=False):
        s=requests.Session();s.mount('https://',HTTPAdapter(max_retries=Retry(total=4,backoff_factor=.5,status_forcelist=[429,500,502,503,504])))
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN']} if auth else {}
        r=s.get(url,headers=headers,timeout=180);r.raise_for_status();return r.content
    inputs=out/'inputs';inputs.mkdir(parents=True,exist_ok=True)
    rows=[]
    def fetch(path,kind,required=True):
        target=inputs/path;target.parent.mkdir(parents=True,exist_ok=True)
        try:
            b=get(f'https://raw.githubusercontent.com/{REPO}/{PIN}/{path}')
            expected=None
            if b.startswith(b'version https://git-lfs.github.com/spec/v1'):
                text=b.decode();expected=text.split('oid sha256:')[1].split()[0]
                size=int(text.split('size ')[1].split()[0])
                b=get(f'https://media.githubusercontent.com/media/{REPO}/{PIN}/{path}')
                assert len(b)==size and digest(b)==expected,('LFS_HASH_FAIL',path)
            target.write_bytes(b)
            return dict(path=path,kind=kind,sha256=digest(b),bytes=len(b),lfs_sha256=expected,status='OK')
        except Exception as e:
            if required: raise
            return dict(path=path,kind=kind,status='UNAVAILABLE',error=str(e))
    sources=['S1/online.py','S1/score.py','S3/foreground.py','S3/history.py','S3/cold_reference.py','S3/run_stage.py','S3/RULES.json','S3/test_s3.py','S2/recovery.py','S2/endpoints.py','S2/IMPLEMENTATION_RULES.json','S3/audit/FINAL_CLAIM_MATRIX.csv','S3/audit/CLAIM_SUPPORT_S3.csv','S1/MATERIALIZED_INPUTS.json']
    tasks=[(BASE+'/'+s,'source',True) for s in sources]
    tasks += [('research/EKF4_RANGE_S_STAGED_20261014/core.py','source',True)]
    for stage in ('S2','S3'):
        for name in ('SCORES_PER_SEED.csv','RECOVERY_COUNTS.csv','EVENTS.json','RUN_MANIFEST.json','ARTIFACT_HASHES.json'):
            tasks.append((BASE+f'/{stage}/runs/EVAL_001/{name}','stage_metadata',name not in ['RECOVERY_COUNTS.csv','ARTIFACT_HASHES.json']))
    for route in ('R4','R5'):
        for seed in (10,14,20):
            for stage,arms in [('S2',['A','B','C_P','D_P']),('S3',['A','B','C_CP','D_CP'])]:
                for arm in arms:
                    name=f'{route}_aB_m0_B0_Full_{seed}_{arm}'+('_main' if stage=='S3' else '')
                    prefix=BASE+f'/{stage}/runs/EVAL_001/'
                    tasks.append((prefix+name+'.npz','trace',True))
                    if stage=='S3' and arm in ('C_CP','D_CP'):
                        tasks.extend([(prefix+name+'_EVENTS.json','events',True),(prefix+name+'_RETROSPECTIVE.npz','retrospective',False)])
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        for r in pool.map(lambda x:fetch(*x),tasks):
            rows.append(r);print('FETCH',r['status'],r['path'],flush=True)
    artifacts={'R4-TRACE.zip':12243228864,'R5-TRACE.zip':12243741168,'C0A.zip':13300457029}
    for name,aid in artifacts.items():
        b=get(f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip',True)
        (inputs/name).write_bytes(b);rows.append(dict(path=name,kind='original_actions_artifact',artifact_id=aid,sha256=digest(b),bytes=len(b),status='OK'))
    dump(out/'INPUT_MANIFEST.json',dict(source_commit=PIN,inputs=rows))
    return inputs

def transition(x,ds,gy,dt):
    a=gy-x[3]*dt
    if abs(a)<1e-4:
        c=1-a*a/24+a**4/1920-a**6/322560
        dc=-a/12+a**3/480-a**5/53760
    else:
        u=a/2;c=math.sin(u)/u;dc=(u*math.cos(u)-math.sin(u))/(2*u*u)
    phi=x[2]+a/2;u=np.array([math.cos(phi),math.sin(phi)]);up=np.array([-u[1],u[0]])
    d=ds*c*u;v=ds*(dc*u+c*up/2)
    y=x.copy();y[:2]+=d;y[2]=wrap(x[2]+a)
    F=np.eye(4);F[:2,2]=[-d[1],d[0]];F[:2,3]=-dt*v;F[2,3]=-dt
    G=np.zeros((4,3));G[:2,0]=c*u;G[:2,1]=v;G[2,1]=1;G[3,2]=1
    Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    return y,F,G@Q@G.T

def artifact_truth(inputs,route):
    with zipfile.ZipFile(inputs/f'{route}-TRACE.zip') as z:
        name=next(n for n in z.namelist() if n.endswith(f'{route}_aB_m0_full_B0_TRACE.npz'))
        with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as t:return dict(t)

def audit_recursion(inputs,out):
    summary=[];events_out=[];scores=[];step_rows=[];checks=[]
    for route in ('R4','R5'):
      truth=artifact_truth(inputs,route)
      for seed in (10,14,20):
        for stage,arms in [('S2',['A','B','C_P','D_P']),('S3',['A','B','C_CP','D_CP'])]:
          folder=inputs/BASE/stage/'runs/EVAL_001'
          def stem(arm):return f'{route}_aB_m0_B0_Full_{seed}_{arm}'+('_main' if stage=='S3' else '')
          traces={a:load_npz(folder/(stem(a)+'.npz')) for a in arms};a=traces['A'];n=len(a['x'])
          t=a['t'] if 't' in a else truth['t_s']
          assert n==len(truth['t_s']) and np.allclose(t,truth['t_s'],atol=1e-10,rtol=0)
          # Controls inferred from unmodified A prior/previous posterior; used only for a cross-arm recurrence audit.
          # This is not a substitute for archived IMU/odometry in a new causal experiment.
          controls=np.zeros((n,3));max_lateral=0.
          for k in range(1,n):
              xp=a['prior'][k];prev=a['x'][k-1];dt=float(t[k]-t[k-1]);angle=float(wrap(xp[2]-prev[2]))
              c=float(np.sinc(angle/(2*np.pi)));u=np.array([math.cos(prev[2]+angle/2),math.sin(prev[2]+angle/2)])
              delta=xp[:2]-prev[:2];ds=float(delta@u/c);gy=angle+prev[3]*dt
              max_lateral=max(max_lateral,abs(float(delta@np.array([-u[1],u[0]]))))
              controls[k]=[ds,gy,dt]
          table(out/f'CONTROLS_RECONSTRUCTED_{stage}_{route}_{seed}.csv',[dict(index=k,t_s=t[k],ds=controls[k,0],gy=controls[k,1],dt=controls[k,2]) for k in range(n)])
          for arm,tr in traces.items():
              assert len(tr['x'])==n
              ev=[]
              if stage=='S3' and arm in ('C_CP','D_CP'):ev=json.loads((folder/(stem(arm)+'_EVENTS.json')).read_text())
              adopted={int(e['index']) for e in ev if e['disposition']=='ACCEPT'}
              maxs=dict(pred_x=0.,pred_P=0.,S=0.,K=0.,update_x=0.,update_P=0.,NIS=0.,z_parity=0.,mu_parity=0.)
              changed_x=0;changed_P=0;own_not_baseline=0;mask_diff=int(np.count_nonzero(tr['mask']!=a['mask']))
              for k in range(n):
                  xp=tr['prior'][k];pp=tr['Pprior'][k];H=tr['H'][k];R=tr['Reff'][k];nu=tr['nu'][k];yes=bool(tr['mask'][k])
                  S=H@pp@H.T+R;K=np.linalg.solve(S,H@pp).T if yes else np.zeros((4,2))
                  post=xp+K@nu;post[2]=wrap(post[2]);A=np.eye(4)-K@H;P=A@pp@A.T+K@R@K.T
                  local=dict(S=float(np.max(abs(S-tr['S'][k]))),K=float(np.max(abs(K-tr['K'][k]))),update_x=float(np.max(abs(post-tr['x'][k]))),update_P=float(np.max(abs(P-tr['P'][k]))),NIS=abs(float(nu@np.linalg.solve(S,nu))-float(tr['nis'][k])))
                  z=nu+tr['h'][k]+tr['mu'][k];za=a['nu'][k]+a['h'][k]+a['mu'][k]
                  local['z_parity']=float(np.max(abs(z-za)));local['mu_parity']=float(np.max(abs(tr['mu'][k]-a['mu'][k])))
                  pred_diff=None;stale_diff=None
                  if k and k not in adopted:
                      yp,F,Q=transition(tr['x'][k-1],*controls[k]);pred=F@tr['P'][k-1]@F.T+Q
                      if stage=='S2':pred=pred+tr['delta_P'][k]
                      local['pred_x']=float(np.max(abs(yp-xp)));local['pred_P']=float(np.max(abs(pred-pp)))
                      pred_diff=local['pred_x'];stale_diff=float(np.max(abs(xp-a['prior'][k])))
                      if stale_diff>1e-8 and pred_diff<1e-8:own_not_baseline+=1
                  for key,value in local.items():maxs[key]=max(maxs[key],value)
                  changed_x+=int(np.max(abs(tr['x'][k]-a['x'][k]))>1e-10)
                  changed_P+=int(np.max(abs(tr['P'][k]-a['P'][k]))>1e-10)
                  e=float(wrap(tr['x'][k,2]-truth['truth_scoring_only'][k,2]));sigma=math.sqrt(tr['P'][k,2,2])
                  step_rows.append(dict(stage=stage,route=route,seed=seed,arm=arm,index=k,t_s=t[k],heading_error_deg=math.degrees(e),heading_sigma_deg=math.degrees(sigma),heading_nees=e*e/sigma**2,mask=yes,weight=float(tr['weight'][k]),is_adoption=k in adopted,prior_mean_residual=pred_diff,baseline_prior_difference=stale_diff))
              ok=all(v<1e-8 for key,v in maxs.items() if key!='NIS') and maxs['NIS']<1e-7 and max_lateral<1e-8
              summary.append(dict(stage=stage,route=route,seed=seed,arm=arm,n=n,pass_arithmetic=ok,adoptions=len(adopted),mask_diff_from_A=mask_diff,changed_state_steps=changed_x,changed_covariance_steps=changed_P,own_prior_not_stale_baseline_steps=own_not_baseline,max_control_lateral=max_lateral,**maxs))
              e=wrap(tr['x'][:,2]-truth['truth_scoring_only'][:,2]);selected=t>=30;Ppsi=tr['P'][:,2,2]
              scores.append(dict(stage=stage,route=route,seed=seed,arm=arm,n_post30=int(selected.sum()),heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[selected]**2)))),heading95=float(np.mean(e[selected]**2/Ppsi[selected]<=C95)),heading_nees=float(np.mean(e[selected]**2/Ppsi[selected])),xy_rmse_m=float(np.sqrt(np.mean(np.sum((tr['x'][selected,:2]-truth['truth_scoring_only'][selected,:2])**2,axis=1)))),adoptions=len(adopted)))
              if ev:
                retpath=folder/(stem(arm)+'_RETROSPECTIVE.npz');retro=load_npz(retpath) if retpath.exists() else None
                for event in ev:
                  k=int(event['index']);cp=event['checkpoint'];first=float(event['first']);last_equal=None;contiguous=None;changed_count=len(event['historical_indices'])
                  if event['disposition']=='ACCEPT':
                    assert retro is not None
                    ids=np.where(retro['created_index']==k)[0];assert len(ids)>0
                    contiguous=np.array_equal(retro['sample_index'][ids],np.arange(cp+1,k+1))
                    last=ids[-1];last_equal=max(float(np.max(abs(retro['x'][last]-tr['x'][k]))),float(np.max(abs(retro['P'][last]-tr['P'][k]))))
                    assert contiguous and last_equal<1e-10
                  state=event.get('checkpoint_state');cperr=None
                  if state and cp is not None:
                    gtindex=max(0,int(cp));cperr=math.degrees(float(wrap(np.asarray(state['x'])[2]-truth['truth_scoring_only'][gtindex,2])))
                  follow=min(n-1,k+1)
                  events_out.append(dict(stage=stage,route=route,seed=seed,arm=arm,index=k,time_s=float(t[k]),episode_first_s=first,checkpoint_index=cp,checkpoint_time_s=float(t[cp]) if cp is not None and cp>=0 else None,checkpoint_heading_error_deg=cperr,retained_post_checkpoint_history_s=float(t[k]-first),changed_indices=changed_count,disposition=event['disposition'],cold_max_abs=event.get('cold_max_abs'),retrospective_contiguous=contiguous,retrospective_emitted_difference=last_equal,heading_difference_vs_A_at_adoption_deg=math.degrees(float(wrap(tr['x'][k,2]-a['x'][k,2]))),next_prior_difference_vs_A_deg=math.degrees(float(wrap(tr['prior'][follow,2]-a['prior'][follow,2])))))
          # Identical A/B implementations across stages must have identical saved results.
          if stage=='S3':
            for arm in ('A','B'):
              s2=load_npz(inputs/BASE/'S2/runs/EVAL_001'/f'{route}_aB_m0_B0_Full_{seed}_{arm}.npz')
              checks.append(dict(route=route,seed=seed,arm=arm,x_max=float(np.max(abs(s2['x']-traces[arm]['x']))),P_max=float(np.max(abs(s2['P']-traces[arm]['P'])))))
    table(out/'RECURSION_ARITHMETIC_CHECKS.csv',summary);table(out/'S3_ADOPTION_HISTORY.csv',events_out);table(out/'RECOMPUTED_SCORES.csv',scores);table(out/'EVERY_SAVED_STEP.csv',step_rows);table(out/'S2_S3_COMMON_ARMS_PARITY.csv',checks)
    # Verify downloaded trace bytes against the original published per-stage manifest.
    hashes=[]
    for stage in ('S2','S3'):
        d=inputs/BASE/stage/'runs/EVAL_001';p=d/'ARTIFACT_HASHES.json'
        if p.exists():
          manifest=json.loads(p.read_text())
          for q in d.glob('*.npz'):
            if q.name in manifest:hashes.append(dict(stage=stage,file=q.name,passed=digest(q.read_bytes())==manifest[q.name]))
    table(out/'ORIGINAL_PUBLISHED_HASH_CHECKS.csv',hashes)
    return dict(traces=len(summary),all_arithmetic_pass=all(x['pass_arithmetic'] for x in summary),steps=len(step_rows),events=len(events_out),adopted=sum(x['disposition']=='ACCEPT' for x in events_out),all_published_hashes_match=all(x['passed'] for x in hashes),published_hash_checks=len(hashes),max_common_arm_x=max(x['x_max'] for x in checks),max_common_arm_P=max(x['P_max'] for x in checks),limits=['Controls independently reconstructed from stored A prior/posterior; not original sensor-file replay.','Nonlinear SourceFFD model not executed; stored h/H consistency with actual antenna model not independently proved.','Cold replay equality is an existing event receipt; new checks verify matrix arithmetic, own-state propagation and adoption from saved arrays.'])

def roots(o,R):
    a=math.copysign(math.sqrt(o.marginal_nis_r),o.r_nu);b=math.copysign(math.sqrt(o.marginal_nis_s),o.s_nu);n=o.joint_nis
    sr=o.r_nu**2/o.marginal_nis_r;ss=o.s_nu**2/o.marginal_nis_s
    dis=(a*b)**2-n*(a*a+b*b-n);assert dis>-1e-8
    result=[]
    for rho in [(a*b+math.sqrt(max(0,dis)))/n,(a*b-math.sqrt(max(0,dis)))/n]:
      if abs(rho)>=1:continue
      S=np.array([[sr,rho*math.sqrt(sr*ss)],[rho*math.sqrt(sr*ss),ss]])
      if np.linalg.eigvalsh(S-R).min()>-1e-8 and not any(np.max(abs(S-v))<1e-13 for v in result):result.append(S)
    assert result
    return result

def audit_c1(inputs,out):
    with zipfile.ZipFile(inputs/'C0A.zip') as z:
      path=next(p for p in z.namelist() if p.endswith('C0A_AGGREGATE_TAP_DECOMPOSITION.csv'))
      rf=pd.read_csv(io.BytesIO(z.read(path))).set_index(['route','pose_id'])
    rows=[];affected=[];baseline_max=0.;n_ambiguous=0
    for route in ('R4','R5'):
      tr=artifact_truth(inputs,route);j=list(tr['arms']).index('POWER1')
      with zipfile.ZipFile(inputs/f'{route}-TRACE.zip') as z:
        name=next(p for p in z.namelist() if p.endswith(f'{route}_aB_m0_full_B0_UPDATE_ORIGINS.csv.gz'))
        ori=pd.read_csv(io.BytesIO(z.read(name)),compression='gzip');ori=ori[ori.model=='POWER1']
      for o in ori.itertuples(index=False):
        k=int(round(o.t_s/.2));nu=np.array([o.r_nu,o.s_nu]);kp=np.radians(np.array([o.range_to_yaw_deg,o.s_to_yaw_deg])/nu)
        accepted=bool(o.joint_accept);p_saved=float(tr['cov'][k,j,2,2]);Sroots=roots(o,tr['R'][k,j]);n_ambiguous+=len(Sroots)>1
        epost=float(wrap(tr['state'][k,j,2]-tr['truth_scoring_only'][k,2]));eprior=epost-(kp@nu if accepted else 0.)
        f=rf.loc[(route,k)];arms={'FF':(0.,0.),'FL':(0.,-f.physical_e_mp),'LF':(-f.delta_range_m,0.),'LL':(-f.delta_range_m,-f.physical_e_mp),'FP_s':(0.,-f.tap_selection_component),'FP_rs':(-f.delta_range_m,-f.tap_selection_component)}
        for r,S in enumerate(Sroots):
          shrink=float(kp@S@kp);p_prior=p_saved+(shrink if accepted else 0.);p_accept=p_prior-shrink
          assert p_accept>0
          for arm,change in arms.items():
            nnu=nu+np.array(change);nis=float(nnu@np.linalg.solve(S,nnu));yes=nis<=GATE;err=float(wrap(eprior+(kp@nnu if yes else 0.)))
            oldvar=p_saved if yes else p_prior
            newvar=p_accept if yes else p_prior
            if arm=='FF':baseline_max=max(baseline_max,abs(newvar-p_saved));assert yes==accepted
            row=dict(route=route,pose_id=k,t_s=o.t_s,arm=arm,S_root=r,n_roots=len(Sroots),base_accepted=accepted,cf_accepted=yes,cf_nis=nis,heading_error_deg=math.degrees(err),old_sigma_deg=math.degrees(math.sqrt(oldvar)),correct_sigma_deg=math.degrees(math.sqrt(newvar)),old_NEES=err*err/oldvar,correct_NEES=err*err/newvar,old_covered95=err*err/oldvar<=C95,correct_covered95=err*err/newvar<=C95,variance_inflation_factor=oldvar/newvar)
            rows.append(row)
            if not accepted and yes:affected.append(row)
    table(out/'C1_CORRECTED_ALL_ROOTS.csv',rows);table(out/'C1_REJECT_TO_ACCEPT_COVARIANCE_BUG.csv',affected)
    unique=pd.DataFrame(rows).query('S_root==0');summaries=[]
    for (route,arm),g in unique.groupby(['route','arm']):
        summaries.append(dict(route=route,arm=arm,n=len(g),affected=int((~g.base_accepted & g.cf_accepted).sum()),old_coverage95=float(g.old_covered95.mean()),correct_coverage95=float(g.correct_covered95.mean()),old_mean_NEES=float(g.old_NEES.mean()),correct_mean_NEES=float(g.correct_NEES.mean()),max_variance_inflation_factor=float(g.variance_inflation_factor.max())))
    table(out/'C1_COVARIANCE_CORRECTION_SUMMARY.csv',summaries)
    return dict(confirmed_bug='When baseline rejected and counterfactual accepted, old code assigns the saved Ppost=Pprior instead of Pprior-K S K^T.',changed_root_arm_rows=len(affected),affected_unique_time_arm=len({(r['route'],r['pose_id'],r['arm']) for r in affected}),affected_unique_times=len({(r['route'],r['pose_id']) for r in affected}),ambiguous_S_times=n_ambiguous,baseline_variance_parity_max=baseline_max,heading_estimate_changed=False,claim_limit='Partial yaw projection only. Full 4D nonlinear counterfactual replay is still not performed.')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--offline',action='store_true');ap.add_argument('--c1-only',action='store_true');args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    inputs=out/'inputs' if args.offline else acquire(out)
    qa=dict(source_commit=PIN,classification='NONINDEPENDENT_REAUDIT_NOT_NEW_CAUSAL_C2',python=sys.version,numpy=np.__version__,pandas=pd.__version__,platform=platform.platform())
    qa['C1']=audit_c1(inputs,out)
    if not args.c1_only:qa['S2_S3']=audit_recursion(inputs,out)
    dump(out/'QA.json',qa)
    dump(out/'OUTPUT_SHA256.json',{str(p.relative_to(out)):digest(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='OUTPUT_SHA256.json'})
    print(json.dumps(qa,ensure_ascii=False,indent=2),flush=True)
    if not args.c1_only and not qa['S2_S3']['all_arithmetic_pass']:raise SystemExit('AUDIT_MISMATCH_REQUIRES_INVESTIGATION')
if __name__=='__main__':main()
