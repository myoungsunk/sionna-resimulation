"""Post-run evaluation and independent stored-trace checks; no replay."""
from pathlib import Path
import os,sys,json,hashlib
sys.dont_write_bytecode=True
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
SRC=Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2')
cases={c['id']:c for c in json.loads((SRC/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases']}
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
passes=pd.read_csv(ROOT.parent/'pass_rs_azimuth/P2_PASSES_GT.csv')
CHECK=[]
def check(label,a,b,tol=1e-10):
    err=float(np.max(np.abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float))))
    CHECK.append(dict(name=label,max_abs=err,tolerance=tol,passed=err<=tol));assert err<=tol,(label,err)
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def metrics(z,j,c,sel):
    gt=z['truth_scoring_only'];x=z['x'][:,j];P=z['P'][:,j];a=np.array(c['anchor'])[:2];height=c['anchor'][2]-c['robot_z_m']
    radial=gt[:,:2]-a;d=np.linalg.norm(radial,axis=1);ur=radial/d[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]])
    err=x-gt;err[:,2]=wrap(err[:,2]);et=np.einsum('ni,ni->n',ut,err[:,:2]);er=np.einsum('ni,ni->n',ur,err[:,:2]);beta=wrap(np.arctan2(x[:,1]-a[1],x[:,0]-a[0])-np.arctan2(radial[:,1],radial[:,0]));re=np.sqrt(np.sum((x[:,:2]-a)**2,axis=1)+height**2)-np.sqrt(d*d+height**2)
    s=sel;psi=np.rad2deg(err[:,2]);r=dict(n=int(s.sum()),heading_rmse_deg=float(np.sqrt(np.mean(psi[s]**2))),heading_bias_deg=float(np.mean(psi[s])),heading_nees=float(np.mean(err[s,2]**2/P[s,2,2])),range_rmse_cm=float(100*np.sqrt(np.mean(re[s]**2))),xy_rmse_m=float(np.sqrt(np.mean(np.sum(err[s,:2]**2,axis=1)))),mean_abs_et_cm=float(100*np.mean(abs(et[s]))),et_bias_cm=float(100*np.mean(et[s])),mean_abs_beta_deg=float(np.rad2deg(np.mean(abs(beta[s])))),beta_bias_deg=float(np.rad2deg(np.mean(beta[s]))))
    return r

def main():
    rows=[];posts=[];activity=[]
    for method in ['M1','M2']:
        assert json.loads((ROOT/f'{method}_EXECUTION_RESULT.json').read_text())['status']=='TECHNICAL_PASS'
        score=pd.read_csv(ROOT/f'{method}_SCORES.csv')
        for stage in [method+'_OFF',method+'_SWEEP']:
            for path in sorted((ROOT/stage).glob('*.npz')):
                cid,bias=path.stem.rsplit('_',1);c=cases[cid];z=dict(np.load(path));ref=dict(np.load(ROOT.parent/'e1_e4/E1'/path.name));t=np.round(z['t_s'],8);gt=z['truth_scoring_only'];a=np.array(c['anchor'])[:2];specs=json.loads(str(z['specs_json']));n=len(t)
                check('truth/'+path.name,z['truth_scoring_only'],ref['truth_scoring_only'],0);check('ids/'+path.name,z['pose_id'],ref['pose_id'],0)
                for j,name in enumerate(z['names']):
                    variant,arm=str(name).split('_');jr=list(ref['names']).index('A0' if arm=='BB' else 'A1');ab=ref['acc'][:,jr];acc=z['acc'][:,j];check('AB/'+name,acc,ab,0)
                    for key in ['mu','R']:
                        target=ref[key][:,jr].copy()
                        if key=='R' and method=='M1' and variant=='M1-e':target[:,0,0]*=z['range_R_scale'][:,j]
                        check('frozen_'+key+'/'+name,z[key][:,j],target,1e-12)
                    x=z['x'][:,j];pr=z['prior'][:,j];pp=z['Pprior'][:,j];H=z['H'][:,j];R=z['R'][:,j];K=z['K'][:,j];nu=z['nu'][:,j];P=z['P'][:,j]
                    rad=pr[:,:2]-a;dist=np.linalg.norm(rad,axis=1);ur=rad/dist[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]])
                    hp=H@pp;cov=hp@H.transpose(0,2,1)+R;cov=.5*(cov+cov.transpose(0,2,1));raw=np.linalg.solve(cov,hp).transpose(0,2,1)
                    expect=raw.copy();check('own_distance/'+name,dist,z['d_est'][:,j],1e-12)
                    if method=='M1':
                        s=specs[j];lam=np.where(dist<s['D'],s['lam'],1.);scale=np.where(dist<s['D'],s['rscale'],1.)
                        check('lambda/'+name,lam,z['lambda_effective'][:,j],0);check('R_scale/'+name,scale,z['range_R_scale'][:,j],0)
                        expect[:,:2,0]-=(1-lam)[:,None]*ut*np.einsum('ni,ni->n',ut,raw[:,:2,0])[:,None]
                        active=(lam<1)|(scale>1)
                    else:
                        kap=specs[j]['kappa'];actual=(x[:,:2]-pr[:,:2]);prefix=np.vstack([np.zeros(2),np.cumsum(actual,axis=0)])
                        info=np.einsum('ni,nj->nij',H[:,0,:2],H[:,0,:2])/R[:,0,0,None,None]*acc[:,None,None];ci=np.concatenate([np.zeros((1,2,2)),np.cumsum(info,axis=0)])
                        left=np.searchsorted(t,np.round(t-10,8),side='right');I=ci[np.arange(n)+1]-ci[left];sp=np.einsum('ni,ni->n',ut,prefix[np.arange(n)]-prefix[left]);ev=np.linalg.eigvalsh(I);valid=(t-t[0]>=10)&(ev[:,0]>np.maximum(1e-12,ev[:,1]*1e-10));sigma=np.full(n,np.inf);sigma[valid]=np.sqrt(np.einsum('ni,ni->n',ut[valid],np.linalg.solve(I[valid],ut[valid,:,None])[:,:,0]));gamma=np.ones(n);delta=np.einsum('ni,ni->n',ut,np.einsum('nij,nj->ni',raw,nu)[:,:2]);feasible=np.ones(n,bool)
                        if kap:
                            for k in np.flatnonzero(valid&acc):
                                b=kap*sigma[k];v=sp[k];dv=delta[k]
                                if abs(v+dv)<=b or abs(dv)<1e-15:continue
                                roots=sorted([(-b-v)/dv,(b-v)/dv]);lo=max(0.,roots[0]);hi=min(1.,roots[1])
                                if lo<=hi:gamma[k]=hi
                                else:feasible[k]=False;gamma[k]=float(abs(v+dv)<abs(v))
                        check('rolling_S/'+name,sp,z['S_prev_m'][:,j],1e-9);check('valid/'+name,valid,z['info_valid'][:,j],0)
                        check('sigma/'+name,sigma[valid],z['sigma_t_m'][valid,j],1e-10);check('gamma/'+name,gamma,z['gamma'][:,j],1e-8)
                        expect[:,:2,:]-=(1-z['gamma'][:,j])[:,None,None]*ut[:,:,None]*np.einsum('ni,nij->nj',ut,raw[:,:2,:])[:,None,:]
                        active=z['gamma'][:,j]<1-1e-12
                    check('gain/'+name,K,expect,1e-12)
                    dx=np.einsum('nij,nj->ni',K,nu)*acc[:,None];ex=x-pr-dx;ex[:,2]=wrap(ex[:,2]);check('update/'+name,ex,0,1e-12)
                    A=np.eye(4)[None]-K@H;PJ=A@pp@A.transpose(0,2,1)+K@R@K.transpose(0,2,1);PJ=.5*(PJ+PJ.transpose(0,2,1));PJ[~acc]=pp[~acc];check('Joseph/'+name,P,PJ,1e-12)
                    for key in ['P','Pprior']:
                        mat=z[key][:,j];check('symmetry/'+name,mat,mat.transpose(0,2,1),1e-12);assert np.linalg.eigvalsh(mat).min()>=-1e-12
                    if stage.endswith('OFF'):
                        for key in ['x','P','prior','Pprior','h','H','K','mu','R','nu']:check('OFF_'+key+'/'+name,z[key][:,j],ref[key][:,jr])
                    r=metrics(z,j,c,t>=30);rr=score[(score.case==cid)&(score.bias==bias)&(score.arm==name)].iloc[0]
                    for key in ['heading_rmse_deg','heading_bias_deg','heading_nees','range_rmse_cm','xy_rmse_m']:check('score_'+key+'/'+name,r[key],rr[key])
                    common=dict(method=method,case=cid,bias=bias,variant=variant,arm=arm)
                    rows.append(dict(**common,**r));activity.append(dict(**common,n_accepted=int(acc.sum()),active_accepted=int((active&acc).sum()),active_scoring=int((active&acc&(t>=30)).sum()),infeasible_accepted=int((~z['feasible'][:,j]&acc).sum()) if method=='M2' else 0))
                    for p in passes[(passes.case==cid)&(passes.bias==bias)].itertuples():
                        mask=(t>round(p.post_start_s,8))&(t<=round(p.post_end_s,8));prm=metrics(z,j,c,mask) if p.valid_post else {}
                        posts.append(dict(**common,pass_id=p.pass_id,valid_post=p.valid_post,post_length_s=p.post_length_s,post_n=int(mask.sum()),**prm))
    allscore=pd.DataFrame(rows);post=pd.DataFrame(posts);act=pd.DataFrame(activity);allscore.to_csv(ROOT/'ALL_METRICS.csv',index=False);post.to_csv(ROOT/'ALL_PASS_METRICS.csv',index=False);act.to_csv(ROOT/'ACTIVATION.csv',index=False)
    decisions=[];groups=[]
    for method in ['M1','M2']:
        ss=allscore[allscore.method==method];ps=post[post.method==method];off=method+'-0'
        for variant in sorted(set(ss.variant)-{off}):
            for cid,bias in ss[['case','bias']].drop_duplicates().itertuples(index=False):
                def get(v,a):return ss[(ss.case==cid)&(ss.bias==bias)&(ss.variant==v)&(ss.arm==a)].iloc[0]
                bb,mb,nb,nm=get(off,'BB'),get(off,'MB'),get(variant,'BB'),get(variant,'MB');gap=mb.heading_rmse_deg-bb.heading_rmse_deg;den=bb.range_rmse_cm-mb.range_rmse_cm;retain=(bb.range_rmse_cm-nm.range_rmse_cm)/den if den>1e-12 else np.nan
                for p in passes[(passes.case==cid)&(passes.bias==bias)].itertuples():
                    p0=ps[(ps.case==cid)&(ps.bias==bias)&(ps.variant==off)&(ps.arm=='MB')&(ps.pass_id==p.pass_id)].iloc[0];pn=ps[(ps.case==cid)&(ps.bias==bias)&(ps.variant==variant)&(ps.arm=='MB')&(ps.pass_id==p.pass_id)].iloc[0]
                    c1=nm.heading_rmse_deg<=bb.heading_rmse_deg or (gap>0 and nm.heading_rmse_deg<=mb.heading_rmse_deg-.5*gap);c2=retain>=.8;c3=bool(p.valid_post and pn.mean_abs_et_cm<p0.mean_abs_et_cm and pn.mean_abs_beta_deg<p0.mean_abs_beta_deg);c4=nm.xy_rmse_m<=1.1*mb.xy_rmse_m and nm.heading_nees<=1.1*mb.heading_nees;c5=nb.heading_rmse_deg<=1.1*bb.heading_rmse_deg
                    decisions.append(dict(method=method,variant=variant,case=cid,bias=bias,pass_id=p.pass_id,primary=cid in PRIMARY and p.pass_id==1,criterion1=c1,criterion2=c2,criterion3=c3,criterion4=c4,criterion5=c5,pass_all=c1 and c2 and c3 and c4 and c5,range_retention=retain,post_abs_et_off_cm=p0.get('mean_abs_et_cm',np.nan),post_abs_et_new_cm=pn.get('mean_abs_et_cm',np.nan),post_abs_beta_off_deg=p0.get('mean_abs_beta_deg',np.nan),post_abs_beta_new_deg=pn.get('mean_abs_beta_deg',np.nan),valid_post=p.valid_post,R4_nonworsening=nb.heading_rmse_deg<=bb.heading_rmse_deg and nm.heading_rmse_deg<=mb.heading_rmse_deg))
            dd=pd.DataFrame(decisions);d=dd[(dd.variant==variant)&dd.primary];counts=sum(d[d.case==c].pass_all.all() and len(d[d.case==c])==2 for c in PRIMARY);r4=d[d.case=='R4_aA_m0'].R4_nonworsening.all();groups.append(dict(method=method,variant=variant,primary_case_pass_count=int(counts),R4_nonworsening=bool(r4),result='GO' if counts>=2 and r4 else 'NO_GO'))
    dd=pd.DataFrame(decisions)
    for method in ['M1','M2']:
        dd[(dd.method==method)&dd.primary].to_csv(ROOT/f'{method}_DECISIONS.csv',index=False);dd[(dd.method==method)&~dd.primary].to_csv(ROOT/f'{method}_ROBUSTNESS.csv',index=False)
    pd.DataFrame(groups).to_csv(ROOT/'METHOD_DECISIONS.csv',index=False)
    locked={}
    for lock in ['INPUT_LOCK.json','PRE_AGGREGATION_LOCK.json','M1_INPUT_LOCK.json','M2_INPUT_LOCK.json']:
        obj=json.loads((ROOT/lock).read_text());files=obj.get('files',[])
        for r in files:
            p=Path(r['path']);digest=hashlib.sha256(p.read_bytes()).hexdigest();assert digest==r['sha256'],p;locked[str(p)]=digest
    (ROOT/'ANALYSIS_CHECKS.json').write_text(json.dumps(dict(status='PASS',checks=CHECK,input_hash_count=len(locked)),indent=2),encoding='utf-8')
    print(pd.DataFrame(groups).to_string(index=False));print('validated',len(CHECK),'checks',len(locked),'input hashes')
if __name__=='__main__':main()

