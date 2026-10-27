"""Frozen-mask range-mean interventions; no retraining or R/Q change."""
from pathlib import Path
import os,sys,json,importlib.util,traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
spec=importlib.util.spec_from_file_location('frozen_e','D:/SLAM_bot/DS_NONLINEAR_E1_E4_20261027_01a1775b/run_experiments.py');E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E);S=E.S;S.ROOT=ROOT;E.ROOT=ROOT;os.environ['PJ_OUT']=str(ROOT/'runtime');sys.path.insert(0,str(S.PKG))
import v_replay as V
E.V=V;S.V=V
import numpy as np
import pandas as pd
import diagnostics as D

def plans():
    gate=[dict(name='OFF_BB',kind='BB',alpha=0),dict(name='OFF_MB',kind='MB',alpha=1),dict(name='ORACLE_BB',kind='RECON_BB',alpha=0),dict(name='ORACLE_MB',kind='RECON_MB',alpha=1)]
    test=[dict(name=f'{k}_{d:.1f}',kind=k,D=d,alpha=None) for d in [1.,1.5,2.5] for k in ['NEAR_ONLY','FAR_ONLY']]
    test += [dict(name='ORACLE0_'+bg,kind='ORACLE0',background=bg,alpha=None) for bg in ['BB','MB']]
    test += [dict(name=k,kind=k,alpha=None) for k in ['C_MEAN0','C_MEANONLY','C_FLIP']]
    test += [dict(name=f'C_PERM_{seed}',kind='C_PERM',seed=seed,alpha=None) for seed in range(2026102700,2026102720)]
    return gate,test

def corrected_means(inp,ref,case,bias,specs):
    b=list(ref['names']).index('A0');m=list(ref['names']).index('A1');ab=ref['acc'][:,b];muB=ref['mu'][:,b,0];muM=ref['mu'][:,m,0];c=muM-muB;t=np.round(inp['t'],8);truth=inp['truth'];a=np.array(case['anchor']);d=np.linalg.norm(truth[:,:2]-a[:2],axis=1);hgt=np.sqrt(d*d+(a[2]-case['robot_z_m'])**2)+D.OFFSET;ps=D.pass_masks(case['id'],bias,t);union=np.logical_or.reduce([v for _,v in ps]);out=np.empty((len(t),len(specs)))
    for j,s in enumerate(specs):
        kind=s['kind'];bg='BB' if kind in ['BB','RECON_BB','NEAR_ONLY','FAR_ONLY','FAR_EST'] else 'MB';bg=s.get('background',bg);out[:,j]=muB if bg=='BB' else muM
        if kind in ['NEAR_ONLY','FAR_ONLY']:
            yes=(d<s['D']) if kind=='NEAR_ONLY' else (d>=s['D']);yes &= ab;out[yes,j]=muM[yes]
        elif kind=='ORACLE0':out[union&ab,j]=(inp['z'][:,0]-hgt)[union&ab]
        elif kind.startswith('RECON'):
            original=muB if kind=='RECON_BB' else muM;e=inp['z'][:,0]-original-hgt;out[union&ab,j]=(inp['z'][:,0]-(hgt+e))[union&ab]
        elif kind.startswith('C_'):
            for p,mask in ps:
                yes=mask&ab;v=c[yes];mean=v.mean()
                if kind=='C_MEAN0':v=v-mean
                elif kind=='C_MEANONLY':v=np.full(len(v),mean)
                elif kind=='C_FLIP':v=-v
                elif kind=='C_PERM':v=np.random.default_rng(np.random.SeedSequence([s['seed'],int(p.pass_id)])).permutation(v)
                out[yes,j]=muB[yes]+v
    return out,ab,d,hgt

def replay(case,bias,inp,ref,model,specs):
    means,ab,dgt,hgt=corrected_means(inp,ref,case,bias,specs);n=len(inp['t']);J=len(specs);x=np.tile(np.r_[inp['x0'],0.],(J,1));P=np.tile(np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]),(J,1,1));out={k:np.empty((n,J)+sh) for k,sh in {'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'h':(2,),'H':(2,4),'K':(4,2),'mu':(2,),'R':(2,2),'nu':(2,)}.items()};out['acc']=np.tile(ab[:,None],(1,J))
    for k in range(n):
        if k%128==0:S.stopcheck()
        if k:
            ctrl=inp['controls']
            for j in range(J):x[j],P[j]=V.predict_one(x[j],P[j],float(ctrl['ds_odom'][k]),float(ctrl['dtheta_gyro'][k]),float(ctrl['dt_s'][k]))
        h,H=model.batch(x,case);mu=np.tile(inp['mu'][k],(J,1));mu[:,0]=means[k];rr=np.tile(inp['R'][k],(J,1,1));z=np.tile(inp['z'][k],(J,1))
        for j,s in enumerate(specs):
            if s['kind']=='FAR_EST' and ab[k]:mu[j,0]=inp['pred'][k] if np.linalg.norm(x[j,:2]-np.array(case['anchor'])[:2])>=s['D'] else inp['mu'][k,0]
        for key,v in [('prior',x),('Pprior',P),('h',h),('H',H),('mu',mu),('R',rr),('nu',z-h-mu)]:out[key][k]=v
        x,P,K=E.update(x,P,z,h,H,mu,rr,np.full(J,int(ab[k])));out['x'][k]=x;out['P'][k]=P;out['K'][k]=K
    for key in out:assert np.isfinite(out[key]).all(),key
    for key in ['P','Pprior']:assert np.max(abs(out[key]-out[key].swapaxes(-1,-2)))<=1e-12 and np.linalg.eigvalsh(out[key]).min()>=-1e-12
    S.check('fixed_mask',out['acc'],np.tile(ab[:,None],(1,J)),0);S.check('R_unchanged',out['R'],np.tile(inp['R'][:,None],(1,J,1,1)),0);S.check('mu_pol_unchanged',out['mu'][:,:,1],np.tile(inp['mu'][:,None,1],(1,J)),0)
    for j in range(J):
        target=inp['z'][:,0]-out['mu'][:,j,0]-hgt
        S.check('measurement_error_identity',out['nu'][:,j,0]+out['h'][:,j,0]-hgt,target,1e-10)
    return out

def pass_scores(case,bias,inp,out,specs):
    t=np.round(inp['t'],8);gt=inp['truth'];rad=gt[:,:2]-np.array(case['anchor'])[:2];rad/=np.linalg.norm(rad,axis=1)[:,None];ut=np.column_stack([-rad[:,1],rad[:,0]]);ps=D.pass_masks(case['id'],bias,t);rows=[]
    for j,s in enumerate(specs):
        et=np.einsum('ni,ni->n',ut,out['x'][:,j,:2]-gt[:,:2]);rows.extend(dict(case=case['id'],bias=bias,arm=s['name'],**p) for p in D.tangent_pass(t,et,ps,0.))
    return rows

def main():
    assert json.loads((ROOT/'D_RESULT.json').read_text())['status']=='PASS';locked=json.loads((ROOT/'INPUT_LOCK.json').read_text())['files']+[dict(path=str(Path(__file__).resolve()),sha256=S.sha(__file__))]
    for r in locked:assert S.sha(r['path'])==r['sha256'],r['path']
    S.write('REPLAY_INPUT_LOCK.json',dict(files=locked,utc=S.now(),command=sys.argv));model=V.SourceFFD();feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz');cache=[]
    for case in V.MANIFEST['cases']:
        for bias in ['B0','L2']:
            file=ROOT.parent/'e1_e4/E1'/f'{case["id"]}_{bias}.npz'
            if not file.exists():continue
            inp=S.load_case(case,bias,feat,par,mr,hg);ref=dict(np.load(file));S.check('time',inp['t'],ref['t_s'],0);S.check('pose',inp['ids'],ref['pose_id'],0);cache.append((case,bias,inp,ref))
    assert len(cache)==14;score=[];posts=[];gate,test=plans()
    for stage,specs in [('CONTROL',gate),('INTERVENTIONS',test)]:
        for case,bias,inp,ref in cache:
            S.event('START',stage_name=stage,case=case['id'],bias=bias,arms=len(specs));out=replay(case,bias,inp,ref,model,specs)
            if stage=='CONTROL':
                for j,s in enumerate(specs):
                    jr=list(ref['names']).index('A0' if s['alpha']==0 else 'A1')
                    for key in ['x','P','prior','Pprior','h','H','K','mu','R','nu','acc']:S.check(case['id']+bias+s['name']+key,out[key][:,j],ref[key][:,jr],1e-10)
            score.extend(E.score(stage,case,bias,inp,out,specs,0));posts.extend(pass_scores(case,bias,inp,out,specs));pd.DataFrame(score).to_csv(ROOT/'REPLAY_SCORES.csv',index=False);pd.DataFrame(posts).to_csv(ROOT/'REPLAY_PASS_SCORES.csv',index=False);S.write('REPLAY_CHECKS.json',S.checks);S.event('CASE_PASS',stage_name=stage,case=case['id'],bias=bias)
        S.write(stage+'_GATE.json',dict(status='PASS',conditions=14,arms=len(specs)))
    sc=pd.DataFrame(score);eligible=[];criteria=[]
    for dist in [1.,1.5,2.5]:
        passed=0
        for cid in D.PRIMARY:
            paired=[]
            for bias in ['B0','L2']:
                df=sc[(sc.case==cid)&(sc.bias==bias)].set_index('arm');b=df.loc['OFF_BB'];m=df.loc['OFF_MB'];ne=df.loc[f'NEAR_ONLY_{dist:.1f}'];fa=df.loc[f'FAR_ONLY_{dist:.1f}'];gap=m.heading_bias_deg-b.heading_bias_deg;den=b.range_rmse_cm-m.range_rmse_cm;valid=abs(gap)>.01 and den>1e-12
                nr=(ne.heading_bias_deg-b.heading_bias_deg)/gap if valid else np.nan;fr=abs((fa.heading_bias_deg-b.heading_bias_deg)/gap) if valid else np.nan;ret=(b.range_rmse_cm-fa.range_rmse_cm)/den if valid else np.nan;yes=valid and nr>=.7 and fr<=.3 and ret>=.7;paired.append(yes);criteria.append(dict(case=cid,bias=bias,D=dist,near_signed_reproduction=nr,far_abs_reproduction=fr,range_retention=ret,pass_goal=yes,valid=valid))
            passed+=all(paired)
        if passed>=2:eligible.append(dist)
    pd.DataFrame(criteria).to_csv(ROOT/'T1_EST_GATE_DECISIONS.csv',index=False);S.write('T1_EST_GATE.json',dict(eligible_D=eligible,rule='same D primary paired cases >=2'))
    if eligible:
        specs=[dict(name=f'FAR_EST_{d:.1f}',kind='FAR_EST',D=d,alpha=None) for d in eligible]
        for case,bias,inp,ref in cache:
            S.event('START',stage_name='T1_EST',case=case['id'],bias=bias);out=replay(case,bias,inp,ref,model,specs);score.extend(E.score('T1_EST',case,bias,inp,out,specs,0));posts.extend(pass_scores(case,bias,inp,out,specs));pd.DataFrame(score).to_csv(ROOT/'REPLAY_SCORES.csv',index=False);pd.DataFrame(posts).to_csv(ROOT/'REPLAY_PASS_SCORES.csv',index=False)
    sc=pd.DataFrame(score)
    for label,mask in [('T1',sc.arm.str.startswith(('NEAR_ONLY','FAR_ONLY','FAR_EST','OFF_'))),('T2',sc.arm.str.startswith(('ORACLE','OFF_'))),('T3',sc.arm.str.startswith(('C_','OFF_')))]:sc[mask].to_csv(ROOT/f'{label}_SCORES.csv',index=False)
    S.write('REPLAY_CHECKS.json',S.checks)
    for r in locked:assert S.sha(r['path'])==r['sha256'],r['path']
    S.write('REPLAY_RESULT.json',dict(status='TECHNICAL_PASS',conditions=14,trajectories=len(sc),T1_est_D=eligible,T4='NOT_RUN_R_IDENTICAL',inputs_unchanged=True,utc=S.now()))
if __name__=='__main__':
    try:main()
    except BaseException as e:S.write('REPLAY_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
