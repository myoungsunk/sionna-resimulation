from pathlib import Path
import os,sys,json,hashlib,datetime
sys.dont_write_bytecode=True
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parent;BASE=R.parent
SRC=Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2')
MP=SRC/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json';CASES={c['id']:c for c in json.loads(MP.read_text())['cases']}
PASSES=pd.read_csv(BASE/'pass_rs_azimuth/P2_PASSES_GT.csv');PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0'];OFFSET=-.5315983906250129
CHECK=[]
def dump(name,x):(R/name).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(n,a,b,tol=1e-10):
    err=float(np.max(abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float))));CHECK.append(dict(name=n,max_abs=err,tol=tol,passed=err<=tol));assert err<=tol,(n,err)
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def data(path):
    z=dict(np.load(path));cid,bias=path.stem.rsplit('_',1);b=list(z['names']).index('A0');m=list(z['names']).index('A1');case=CASES[cid];a=np.array(case['anchor']);gt=z['truth_scoring_only'];t=np.round(z['t_s'],8);rad=gt[:,:2]-a[:2];d=np.linalg.norm(rad,axis=1);ur=rad/d[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]]);r=np.sqrt(d*d+(a[2]-case['robot_z_m'])**2);hgt=r+OFFSET;raw=z['nu'][:,b,0]+z['h'][:,b,0]+z['mu'][:,b,0];c=z['mu'][:,m,0]-z['mu'][:,b,0];acc=z['acc'][:,b];eb=raw-z['mu'][:,b,0]-hgt;em=raw-z['mu'][:,m,0]-hgt
    return z,cid,bias,b,m,t,gt,ur,ut,d,r,hgt,raw,c,acc,eb,em

def pass_masks(cid,bias,t):
    out=[];count=np.zeros(len(t),int)
    for p in PASSES[(PASSES.case==cid)&(PASSES.bias==bias)].itertuples():
        mask=(t>=max(t[0],round(p.start_s-10,8)))&(t<=min(t[-1],round(p.end_s+10,8)));count+=mask;out.append((p,mask))
    assert count.max()<=1,('OVERLAPPING_EXPANDED_WINDOWS',cid,bias)
    return out

def tangent_pass(t,et,ps,initial_gap):
    out=[]
    for p,win in ps:
        pre=(t>=p.pre_start_s)&(t<p.pre_end_s);post=(t>p.post_start_s)&(t<=p.post_end_s);preok=bool(p.valid_pre);init=False
        if p.pre_length_s<5:
            preok=abs(initial_gap)<.001;init=preok;pm=float(et[0]) if preok else np.nan
        else:pm=float(et[pre].mean()) if pre.any() and preok else np.nan
        po=float(et[post].mean()) if p.valid_post and post.any() else np.nan
        out.append(dict(pass_id=p.pass_id,pre_cm=pm*100,post_cm=po*100,delta_et_cm=(po-pm)*100,pre_length_s=p.pre_length_s,post_length_s=p.post_length_s,pre_n=int(pre.sum()),post_n=int(post.sum()),pre_from_init=init,init_overlap=p.init_overlap,valid=bool(preok and p.valid_post),post_valid=bool(p.valid_post)))
    return out

def stats(e,c,r,d,mask):
    v=e[mask];cv=c[mask];lat=np.divide(e*r,d,out=np.full(len(e),np.nan),where=d>1e-8)[mask]
    return dict(n=int(mask.sum()),mean_er_m=float(np.mean(v)) if len(v) else np.nan,rms_er_m=float(np.sqrt(np.mean(v*v))) if len(v) else np.nan,mean_c_m=float(np.mean(cv)) if len(v) else np.nan,rms_c_m=float(np.sqrt(np.mean(cv*cv))) if len(v) else np.nan,mean_elat_m=float(np.nanmean(lat)) if len(v) else np.nan,rms_elat_m=float(np.sqrt(np.nanmean(lat*lat))) if len(v) else np.nan)
def acf(e,acc,win,t):
    ii=np.flatnonzero(win);v=e[ii];ok=acc[ii];mean=v[ok].mean();v=v-mean;var=np.mean(v[ok]**2)
    if var<1e-24:return np.nan,'ZERO_VARIANCE'
    dt=float(np.median(np.diff(t)));check('regular_dt',np.diff(t),np.full(len(t)-1,dt),1e-8)
    for lag in range(1,len(ii)//2+1):
        sel=ok[:-lag]&ok[lag:]
        if sel.sum()<10:continue
        corr=np.mean(v[:-lag][sel]*v[lag:][sel])/var
        if corr<=.5:return lag*dt,'OBSERVED'
    return np.nan,'RIGHT_CENSORED'
def main():
    files=[MP,R/'PROTOCOL.md',Path(__file__),BASE/'pass_rs_azimuth/P2_PASSES_GT.csv']+sorted((BASE/'e1_e4/E1').glob('*.npz'))
    old=json.loads((BASE/'azimuth_methods/M1_INPUT_LOCK.json').read_text())['files']
    for item in old:assert sha(item['path'])==item['sha256']
    records={str(Path(item['path']).resolve()):item for item in old}
    for p in files:records[str(p.resolve())]=dict(path=str(p.resolve()),sha256=sha(p))
    dump('INPUT_LOCK.json',dict(baseline='2ee731336fc2b37ffcd67f96a07bdaf3dccc2898',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=list(records.values())))
    inventory=[];cache=[]
    for path in sorted((BASE/'e1_e4/E1').glob('*.npz')):
        vals=data(path);z,cid,bias,b,m,t,gt,ur,ut,d,r,hgt,raw,c,acc,eb,em=vals;cache.append(vals)
        check(cid+bias+'mask',acc,z['acc'][:,m],0);check(cid+bias+'raw',raw,z['nu'][:,m,0]+z['h'][:,m,0]+z['mu'][:,m,0]);check(cid+bias+'error_relation',em[acc],eb[acc]-c[acc]);check(cid+bias+'frozen_R',z['R'][:,b],z['R'][:,m],0);check(cid+bias+'frozen_pol_mean',z['mu'][:,b,1],z['mu'][:,m,1],0)
        inventory.append(pd.DataFrame(dict(case=cid,bias=bias,k=np.arange(len(t)),pose_id=z['pose_id'],t_s=t,accepted=acc,mu_B=z['mu'][:,b,0],mu_M=z['mu'][:,m,0],Rrr_B=z['R'][:,b,0,0],Rrr_M=z['R'][:,m,0,0],c_m=np.where(acc,c,np.nan),er_BB_m=np.where(acc,eb,np.nan),er_MB_m=np.where(acc,em,np.nan),d_gt_m=d,h_gt_m=hgt)))
    pd.concat(inventory).to_csv(R/'D0_STRUCTURE.csv',index=False);dump('D0_GATE.json',dict(status='PASS',conditions=len(cache),R_difference=0,T4='SKIP_R_IDENTICAL',max_error_relation=max(q['max_abs'] for q in CHECK if 'error_relation' in q['name'])))
    bins=[];passtats=[];tans=[];force=[];reg=[];series=[]
    edges=[0,.5,1,1.5,2,3,4,6,8,np.inf]
    for vals in cache:
        z,cid,bias,b,m,t,gt,ur,ut,d,r,hgt,raw,c,acc,eb,em=vals;ps=pass_masks(cid,bias,t);etb=np.einsum('ni,ni->n',ut,z['x'][:,b,:2]-gt[:,:2]);etm=np.einsum('ni,ni->n',ut,z['x'][:,m,:2]-gt[:,:2]);initgap=etm[0]-etb[0]
        for arm,j,e,et in [('BB',b,eb,etb),('MB',m,em,etm)]:
            for scope,ss in [('all',np.ones(len(t),bool)),('scoring',t>=30)]:
                for lo,hi in zip(edges[:-1],edges[1:]):bins.append(dict(case=cid,bias=bias,arm=arm,scope=scope,bin=f'[{lo},{hi})',**stats(e,c,r,d,acc&ss&(d>=lo)&(d<hi))))
                bins.append(dict(case=cid,bias=bias,arm=arm,scope=scope,bin='near',**stats(e,c,r,d,acc&ss&(d<1.5))))
            for p,win in ps:passtats.append(dict(case=cid,bias=bias,arm=arm,pass_id=p.pass_id,**stats(e,c,r,d,acc&(t>=p.start_s)&(t<=p.end_s))))
            tans.extend(dict(case=cid,bias=bias,arm=arm,**rr) for rr in tangent_pass(t,et,ps,initgap))
        kb=z['K'][:,b,:2,0];km=z['K'][:,m,:2,0];vb=kb*z['nu'][:,b,0,None]*acc[:,None];vm=km*z['nu'][:,m,0,None]*acc[:,None];terms=[-km*c[:,None]*acc[:,None],(km-kb)*z['nu'][:,b,0,None]*acc[:,None],-km*(z['h'][:,m,0]-z['h'][:,b,0])[:,None]*acc[:,None]];check(cid+bias+'D3_XY',vm-vb,sum(terms))
        prb=z['prior'][:,b,:2]-np.array(CASES[cid]['anchor'])[:2];prb/=np.linalg.norm(prb,axis=1)[:,None];ptb=np.column_stack([-prb[:,1],prb[:,0]]);prm=z['prior'][:,m,:2]-np.array(CASES[cid]['anchor'])[:2];prm/=np.linalg.norm(prm,axis=1)[:,None];ptm=np.column_stack([-prm[:,1],prm[:,0]])
        for p,win in ps:
            taub,stb=acf(eb,acc,win,t);taum,stm=acf(em,acc,win,t)
            for seg,sel in [('expanded',win),('pre',win&(t<p.start_s)),('during',win&(t>=p.start_s)&(t<=p.end_s)),('post',win&(t>p.end_s)),('outside',~win)]:
                for frame,ar,at in [('GT',ur,ut),('BB_PRIOR_COMMON',prb,ptb)]:
                    for direction,axis in [('tangent',at),('radial',ar)]:
                        sums=[float(np.einsum('ni,ni->n',axis,v)[sel].sum()) for v in [vb,vm]+terms];fb,fm,fc,fg,fh=sums;check(cid+bias+str(p.pass_id)+seg+frame+direction+'_sum',fm-fb,fc+fg+fh)
                        ratio=abs(fh/fc) if abs(fc)>1e-12 else np.nan
                        force.append(dict(case=cid,bias=bias,pass_id=p.pass_id,segment=seg,frame=frame,direction=direction,n=int((acc&sel).sum()),F_BB_cm=fb*100,F_MB_cm=fm*100,gap_cm=(fm-fb)*100,correction_cm=fc*100,gain_difference_cm=fg*100,prediction_difference_cm=fh*100,sign_relation='OPPOSITE' if fc*fh<0 else 'SAME' if fc*fh>0 else 'ZERO',prediction_to_correction_abs=ratio,opposite_similar=bool(fc*fh<0 and .5<=ratio<=2),tau_BB_s=taub,tau_MB_s=taum,tau_BB_status=stb,tau_MB_status=stm,own_prior_F_BB_cm=float(np.einsum('ni,ni->n',ptb if direction=='tangent' else prb,vb)[sel].sum()*100),own_prior_F_MB_cm=float(np.einsum('ni,ni->n',ptm if direction=='tangent' else prm,vm)[sel].sum()*100)))
        beta=np.arctan2(-ur[:,1],-ur[:,0]);psi=gt[:,2];vel=np.gradient(gt[:,1],t);zig=np.where(abs(vel)<1e-8,0,np.sign(vel));names=['sin_psi','cos_psi','sin_psi_beta','cos_psi_beta','world_y_m','d_gt_m','zigzag_sign'];X=np.column_stack([np.sin(psi),np.cos(psi),np.sin(psi-beta),np.cos(psi-beta),gt[:,1],d,zig])
        for grp,sel in [('near',acc&(d<1.5)),('far',acc&(d>=1.5))]:
            xx=X[sel];yy=c[sel];mean=xx.mean(axis=0);sd=xx.std(axis=0);active=sd>1e-12;xx=np.column_stack([np.ones(len(xx)),(xx[:,active]-mean[active])/sd[active]]);coef,_,rank,sv=np.linalg.lstsq(xx,yy,rcond=None);pred=xx@coef;den=np.sum((yy-yy.mean())**2);r2=1-np.sum((yy-pred)**2)/den if den>1e-24 else np.nan;full=np.zeros(7);full[active]=coef[1:]/sd[active];inter=coef[0]-mean@full
            for name,value in zip(['intercept']+names,[inter]+list(full)):reg.append(dict(case=cid,bias=bias,group=grp,n=int(sel.sum()),pass_blocks=len(ps),feature=name,coefficient=value,R2=r2,rank=int(rank),columns=xx.shape[1],condition=float(sv[0]/sv[-1]) if sv[-1]>1e-15 else np.inf,CI='NOT_COMPUTED',interpretation='DESCRIPTIVE_ONLY'))
        series.append(pd.DataFrame(dict(case=cid,bias=bias,t_s=t,d_gt_m=d,accepted=acc,c_m=np.where(acc,c,np.nan),er_BB_m=np.where(acc,eb,np.nan),er_MB_m=np.where(acc,em,np.nan),Ft_BB_cm=np.einsum('ni,ni->n',ut,vb)*100,Ft_MB_cm=np.einsum('ni,ni->n',ut,vm)*100)))
    for fname,rows in [('D1_RANGE_ERR_BY_BIN.csv',bins),('D1_RANGE_ERR_BY_PASS.csv',passtats),('D2_ABS_TANGENT_BY_PASS.csv',tans),('D3_FORCING.csv',force),('D4_C_REGRESSION.csv',reg)]:pd.DataFrame(rows).to_csv(R/fname,index=False)
    consist=[]
    for kind,rows,field in [('D1',passtats,'mean_er_m'),('D2',tans,'delta_et_cm')]:
        for key,g in pd.DataFrame(rows).groupby(['case','bias','arm']):
            v=g[field].dropna();pos=int((v>0).sum());neg=int((v<0).sum());consist.append(dict(kind=kind,case=key[0],bias=key[1],arm=key[2],n_pass=len(v),sign_consistency=max(pos,neg)/(pos+neg) if pos+neg else np.nan,single_pass=len(v)==1))
    pd.DataFrame(consist).to_csv(R/'D_SIGN_CONSISTENCY.csv',index=False);pd.concat(series).to_csv(R/'D3_SERIES.csv.gz',index=False)
    for item in records.values():assert sha(item['path'])==item['sha256']
    dump('D_CHECKS.json',dict(status='PASS',checks=CHECK));dump('D_RESULT.json',dict(status='PASS',conditions=14,T4='NOT_RUN_R_IDENTICAL'));print('D0-D4 PASS',len(CHECK),'checks',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:
        import traceback
        dump('D_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
