"""Independent replay verification and predeclared hypothesis decisions."""
from pathlib import Path
import os,sys,json
sys.dont_write_bytecode=True
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import numpy as np
import pandas as pd
import diagnostics as D
R=Path(__file__).resolve().parent
CHECK=[]
def ck(name,a,b,tol=1e-10):
    err=float(np.max(abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float))));CHECK.append(dict(name=name,error=err,tol=tol,passed=err<=tol));assert err<=tol,(name,err)
def ratios(g,base,limit):return (1-abs(g)/abs(base),1-g/base) if abs(base)>limit else (np.nan,np.nan)
def main():
    analysis_inputs=[Path(__file__),R/'DECISION_CLARIFICATION.md',R.parent/'component_azimuth/B_SCORES.csv']; analysis_lock=[dict(path=str(p.resolve()),sha256=D.sha(p)) for p in analysis_inputs]; D.dump('ANALYSIS_INPUT_LOCK.json',dict(files=analysis_lock)); result=json.loads((R/'REPLAY_RESULT.json').read_text());assert result['status']=='TECHNICAL_PASS';scores=pd.read_csv(R/'REPLAY_SCORES.csv');posts=pd.read_csv(R/'REPLAY_PASS_SCORES.csv');extra=[]
    for stage in ['CONTROL','INTERVENTIONS','T1_EST']:
        for p in sorted((R/stage).glob('*.npz')):
            z=dict(np.load(p));ref,cid,bias,b,m,t,gt,ur,ut,d,r,hgt,raw,c,acc,eb,em=D.data(R.parent/'e1_e4/E1'/p.name);ps=D.pass_masks(cid,bias,t);union=np.logical_or.reduce([win for _,win in ps]);a=np.array(D.CASES[cid]['anchor']);specs=json.loads(str(z['specs_json']))
            ck('time',z['t_s'],t,1e-10);ck('pose',z['pose_id'],ref['pose_id'],0);ck('truth',z['truth_scoring_only'],gt,0)
            for j,s in enumerate(specs):
                arm=s['name'];kind=s['kind'];x=z['x'][:,j];prior=z['prior'][:,j];P=z['P'][:,j];Pp=z['Pprior'][:,j];H=z['H'][:,j];K=z['K'][:,j];nu=z['nu'][:,j];rr=z['R'][:,j];mu=z['mu'][:,j]
                ck('AB',z['acc'][:,j],acc,0);ck('R',rr,ref['R'][:,b],0);ck('mu_s',mu[:,1],ref['mu'][:,b,1],0)
                hp=H@Pp;cov=hp@H.transpose(0,2,1)+rr;cov=(cov+cov.transpose(0,2,1))*.5;expectedK=np.linalg.solve(cov,hp).transpose(0,2,1);ck('optimal_joint_gain',K,expectedK,1e-12)
                dx=np.einsum('nij,nj->ni',K,nu)*acc[:,None];ee=x-prior-dx;ee[:,2]=D.wrap(ee[:,2]);ck('posterior_update',ee,0,1e-12);A=np.eye(4)[None]-K@H;expectedP=A@Pp@A.transpose(0,2,1)+K@rr@K.transpose(0,2,1);expectedP=(expectedP+expectedP.transpose(0,2,1))*.5;expectedP[~acc]=Pp[~acc];ck('Joseph',P,expectedP,1e-12)
                for mat in [P,Pp]:ck('symmetric',mat,mat.transpose(0,2,1),1e-12);assert np.linalg.eigvalsh(mat).min()>=-1e-12
                hr=np.sqrt(np.sum((prior[:,:2]-a[:2])**2,axis=1)+(a[2]-D.CASES[cid]['robot_z_m'])**2)+D.OFFSET;ck('range_model',z['h'][:,j,0],hr,1e-12);ck('raw_measurement',nu[:,0]+z['h'][:,j,0]+mu[:,0],raw)
                if stage=='CONTROL':
                    jr=b if kind in ['BB','RECON_BB'] else m
                    for key in ['x','P','prior','Pprior','h','H','K','mu','R','nu']:ck('control_'+arm+'_'+key,z[key][:,j],ref[key][:,jr])
                else:
                    if kind in ['NEAR_ONLY','FAR_ONLY','FAR_EST']:
                        ds=np.linalg.norm(prior[:,:2]-a[:2],axis=1) if kind=='FAR_EST' else d;yes=ds<s['D'] if kind=='NEAR_ONLY' else ds>=s['D'];expected=ref['mu'][:,b,0]+c*yes;ck('distance_intervention',mu[acc,0],expected[acc],1e-12)
                    elif kind=='ORACLE0':
                        ck('oracle_zero',raw[union&acc]-mu[union&acc,0],hgt[union&acc],1e-12);bg=b if s['background']=='BB' else m;ck('oracle_outside',mu[~union,0],ref['mu'][~union,bg,0],1e-12)
                    elif kind.startswith('C_'):
                        ck('outside_MB',mu[~union,0],ref['mu'][~union,m,0],1e-12)
                        for passrow,win in ps:
                            sel=win&acc;original=c[sel];got=mu[sel,0]-ref['mu'][sel,b,0]
                            if kind=='C_MEAN0':ck('mean_removed',got,original-original.mean(),1e-12)
                            elif kind=='C_MEANONLY':ck('mean_only',got,np.full(len(got),original.mean()),1e-12)
                            elif kind=='C_FLIP':ck('flip',got,-original,1e-12)
                            else:
                                ck('perm_distribution',np.sort(got),np.sort(original),1e-12);expected=np.random.default_rng(np.random.SeedSequence([s['seed'],int(passrow.pass_id)])).permutation(original);ck('perm_seed',got,expected,1e-12)
                err=x-gt;err[:,2]=D.wrap(err[:,2]);sel=t>=30;hd=np.rad2deg(err[sel,2]);rang=np.sqrt(np.sum((x[:,:2]-a[:2])**2,axis=1)+(a[2]-D.CASES[cid]['robot_z_m'])**2)-r;met=dict(heading_rmse_deg=np.sqrt(np.mean(hd**2)),heading_bias_deg=hd.mean(),xy_rmse_m=np.sqrt(np.mean(np.sum(err[sel,:2]**2,axis=1))),range_rmse_cm=100*np.sqrt(np.mean(rang[sel]**2)))
                row=scores[(scores.case==cid)&(scores.bias==bias)&(scores.arm==arm)].iloc[0]
                for key,val in met.items():ck('score_'+key,val,row[key])
                et=np.einsum('ni,ni->n',ut,err[:,:2]);pmetrics=D.tangent_pass(t,et,ps,0.)
                for pp in pmetrics:
                    rrpost=posts[(posts.case==cid)&(posts.bias==bias)&(posts.arm==arm)&(posts.pass_id==pp['pass_id'])].iloc[0]
                    if pp['valid']:ck('post_delta',pp['delta_et_cm'],rrpost.delta_et_cm)
    old=pd.read_csv(R.parent/'component_azimuth/B_SCORES.csv');old=old[old.alpha==1].copy();comparison=[]
    for cid,bias in scores[['case','bias']].drop_duplicates().itertuples(index=False):
        current=scores[(scores.case==cid)&(scores.bias==bias)].set_index('arm');previous=old[(old.case==cid)&(old.bias==bias)].set_index('arm')
        for key in ['heading_rmse_deg','heading_bias_deg','range_rmse_cm','xy_rmse_m']:ck('historical_full_baseline',current.loc['OFF_MB',key],previous.loc['FULL_1',key])
        for label,source,arm in [('global_constant',previous,'CONST_1'),('global_zero_mean',previous,'VAR_1'),('full',previous,'FULL_1'),('pass_mean_only_with_MB_outside',current,'C_MEANONLY'),('pass_mean_removed_with_MB_outside',current,'C_MEAN0')]:
            row=source.loc[arm];comparison.append(dict(case=cid,bias=bias,definition=label,heading_rmse_deg=row.heading_rmse_deg,heading_bias_deg=row.heading_bias_deg,range_rmse_cm=row.range_rmse_cm,xy_rmse_m=row.xy_rmse_m))
    pd.DataFrame(comparison).to_csv(R/'T3_GLOBAL_COMPONENT_COMPARISON.csv',index=False)
    # Decision metrics: compare every intervention to matching BB, preserve seed-level results.
    for (cid,bias),g in scores.groupby(['case','bias']):
        q=g.set_index('arm');bb=q.loc['OFF_BB'];mb=q.loc['OFF_MB'];p0=posts[(posts.case==cid)&(posts.bias==bias)&(posts.pass_id==1)].set_index('arm');bg=mb.heading_bias_deg-bb.heading_bias_deg;rg=mb.heading_rmse_deg-bb.heading_rmse_deg;tg=p0.loc['OFF_MB'].delta_et_cm-p0.loc['OFF_BB'].delta_et_cm;rangeimp=bb.range_rmse_cm-mb.range_rmse_cm
        for row in g.itertuples():
            arm=row.arm;gb=row.heading_bias_deg-bb.heading_bias_deg;gr=row.heading_rmse_deg-bb.heading_rmse_deg;gt=p0.loc[arm].delta_et_cm-p0.loc['OFF_BB'].delta_et_cm;fb,fs=ratios(gb,bg,.01);fr,_=ratios(gr,rg,.01);ft,_=ratios(gt,tg,.1)
            extra.append(dict(case=cid,bias=bias,arm=arm,heading_bias_gap_deg=gb,MB_heading_bias_gap_deg=bg,f_bias_magnitude=fb,f_bias_signed=fs,heading_rmse_gap_deg=gr,f_rmse_magnitude=fr,delta_et_gap_cm=gt,MB_delta_et_gap_cm=tg,f_tangent_magnitude=ft,range_retention=(bb.range_rmse_cm-row.range_rmse_cm)/rangeimp if rangeimp>1e-12 else np.nan,bias_flip=bool(gb*bg<0) if abs(bg)>.01 else None,tangent_flip=bool(gt*tg<0) if abs(tg)>.1 else None,absolute_delta_et_flip=bool(p0.loc[arm].delta_et_cm*p0.loc['OFF_MB'].delta_et_cm<0)))
    gaps=pd.DataFrame(extra);gaps.to_csv(R/'GAP_METRICS.csv',index=False);perm=gaps[gaps.arm.str.startswith('C_PERM_')];summ=[]
    for key,g in perm.groupby(['case','bias']):
        for metric in ['f_bias_magnitude','f_rmse_magnitude','f_tangent_magnitude','heading_bias_gap_deg','delta_et_gap_cm']:
            v=g[metric].dropna();summ.append(dict(case=key[0],bias=key[1],metric=metric,n=len(v),mean=v.mean(),median=v.median(),p10=v.quantile(.1),p90=v.quantile(.9),minimum=v.min(),maximum=v.max(),n_ge_half=int((v>=.5).sum())))
    perm.to_csv(R/'T3_PERM_SEEDS.csv',index=False);pd.DataFrame(summ).to_csv(R/'T3_PERM_SUMMARY.csv',index=False)
    hypotheses=[];bins=pd.read_csv(R/'D1_RANGE_ERR_BY_BIN.csv');forcing=pd.read_csv(R/'D3_FORCING.csv');t1=pd.read_csv(R/'T1_EST_GATE_DECISIONS.csv')
    for cid,bias in scores[['case','bias']].drop_duplicates().itertuples(index=False):
        q=scores[(scores.case==cid)&(scores.bias==bias)].set_index('arm');gg=gaps[(gaps.case==cid)&(gaps.bias==bias)].set_index('arm');near=bins[(bins.case==cid)&(bins.bias==bias)&(bins.scope=='all')&(bins.bin=='near')].set_index('arm');ff=forcing[(forcing.case==cid)&(forcing.bias==bias)&(forcing.pass_id==1)&(forcing.frame=='GT')&(forcing.segment=='expanded')&(forcing.direction=='tangent')].iloc[0]
        def add(h,stage,valid,support,metric,value,threshold,note=''):
            hypotheses.append(dict(hypothesis=h,stage=stage,case=cid,bias=bias,primary=cid in D.PRIMARY,result=('SUPPORT' if support else 'NOT_SUPPORT') if valid else 'NA',metric=metric,value=value,threshold=threshold,note=note))
        add('W1','D1',True,abs(near.loc['MB'].mean_er_m)>abs(near.loc['BB'].mean_er_m),'near_abs_mean_MB_minus_BB_m',abs(near.loc['MB'].mean_er_m)-abs(near.loc['BB'].mean_er_m),0,'descriptive')
        tv=np.isfinite(ff.tau_BB_s) and np.isfinite(ff.tau_MB_s);add('W2','D3',tv,abs(ff.F_MB_cm)>2*abs(ff.F_BB_cm) and ff.tau_MB_s>2*ff.tau_BB_s,'F_ratio',abs(ff.F_MB_cm/ff.F_BB_cm) if abs(ff.F_BB_cm)>1e-12 else np.nan,2,f'tau_BB={ff.tau_BB_s};tau_MB={ff.tau_MB_s};descriptive')
        for dist in [1.,1.5,2.5]:
            ne=gg.loc[f'NEAR_ONLY_{dist:.1f}'];fa=gg.loc[f'FAR_ONLY_{dist:.1f}'];valid=abs(ne.MB_heading_bias_gap_deg)>.01 and np.isfinite(fa.range_retention);nr=ne.heading_bias_gap_deg/ne.MB_heading_bias_gap_deg if valid else np.nan;fr=abs(fa.heading_bias_gap_deg/fa.MB_heading_bias_gap_deg) if valid else np.nan
            add('W1',f'T1_D{dist}',valid,nr>=.7 and fr<=.3 and fa.range_retention>=.7,'near_signed_reproduction',nr,.7,f'far_abs_reproduction={fr};range_retention={fa.range_retention}')
        br=q.loc['OFF_BB'].heading_rmse_deg;orr=q.loc['ORACLE0_BB'].heading_rmse_deg;add('W3','T2',True,orr>br*1.1,'oracle_BB_RMSE_over_BB',orr/br,1.1,'operational evidence consistent with compensation, not unique mechanism')
        f0=gg.loc['ORACLE0_MB'].f_bias_magnitude;add('W1_W2_DIRECTION','T2',np.isfinite(f0),f0>=.7 and orr<=br,'oracle_MB_gap_removed',f0,.7,'combined pattern only')
        pe=perm[(perm.case==cid)&(perm.bias==bias)].f_bias_magnitude;med=pe.median();add('W2','T3_PERM',pe.notna().sum()==20,med>=.5,'median_seed_bias_gap_reduction',med,.5,'20 fixed seeds; distribution also reported')
        fl=gg.loc['C_FLIP'];valid=abs(fl.MB_heading_bias_gap_deg)>.01 and abs(fl.MB_delta_et_gap_cm)>.1 and np.isfinite(fl.delta_et_gap_cm);add('W4_AUX','T3_FLIP_GAP',valid,bool(fl.bias_flip and fl.tangent_flip),'both_effect_signs_reversed',int(bool(fl.bias_flip and fl.tangent_flip)),1,'relative to BB; not proof of unique geometric correlates')
        pfirst=posts[(posts.case==cid)&(posts.bias==bias)&(posts.pass_id==1)].set_index('arm'); mb_dt=pfirst.loc['OFF_MB'].delta_et_cm; flip_dt=pfirst.loc['C_FLIP'].delta_et_cm; lit_valid=abs(fl.MB_heading_bias_gap_deg)>.01 and abs(mb_dt)>.1 and np.isfinite(flip_dt); add('W4','T3_FLIP_LITERAL',lit_valid,bool(fl.bias_flip and mb_dt*flip_dt<0),'absolute_delta_and_heading_effect_reversed',int(bool(fl.bias_flip and mb_dt*flip_dt<0)),1,'original D2 delta=post-pre; heading movement relative to BB')
        add('W5','D0',True,False,'max_Rrr_difference',0,0,'R-change explanation rejected; state-dependent gain changes remain')
    hh=pd.DataFrame(hypotheses);hh.to_csv(R/'HYPOTHESIS_DECISIONS.csv',index=False);agg=[]
    for (h,stage),g in hh[hh.primary].groupby(['hypothesis','stage']):
        yes=[];na=[]
        for c in D.PRIMARY:
            v=g[g.case==c].result;yes.append(len(v)==2 and (v=='SUPPORT').all());na.append(len(v)!=2 or (v=='NA').any())
        count=sum(yes);unknown=sum(na);result='SUPPORT' if count>=2 else 'NA' if count+unknown>=2 else 'NOT_SUPPORT';agg.append(dict(hypothesis=h,stage=stage,support_cases=count,NA_cases=unknown,total_cases=3,result=result))
    pd.DataFrame(agg).to_csv(R/'HYPOTHESIS_SUMMARY.csv',index=False)
    for lock in ['INPUT_LOCK.json','REPLAY_INPUT_LOCK.json','ANALYSIS_INPUT_LOCK.json']:
        for item in json.loads((R/lock).read_text())['files']:assert D.sha(item['path'])==item['sha256']
    D.dump('VERIFY_CHECKS.json',dict(status='PASS',checks=CHECK,seed_count=20,score_rows=len(scores),hashes_unchanged=True));print(pd.DataFrame(agg).to_string(index=False));print('checks',len(CHECK))
if __name__=='__main__':main()


