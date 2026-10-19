"""Train-only conditional density, temporal moments and action-risk comparisons."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score,brier_score_loss

def temporal_fit(df,mu,C):
    e=df[['e_r','e_s']].to_numpy()-mu
    u=np.linalg.solve(np.linalg.cholesky(C),e[...,None])[...,0]
    pairs={1:[],2:[]}
    for _,ix in df.groupby('case').indices.items():
        ix=np.asarray(ix);ix=ix[np.argsort(df.iloc[ix].pose_id.to_numpy())]
        ids=df.iloc[ix].pose_id.to_numpy()
        for lag in [1,2]:
            valid=ids[lag:]-ids[:-lag]==lag
            if np.any(valid):pairs[lag].append((u[ix[:-lag][valid]],u[ix[lag:][valid]]))
    rho=[]
    for lag in [1,2]:
        a=np.concatenate([p[0] for p in pairs[lag]]);b=np.concatenate([p[1] for p in pairs[lag]])
        a=a-a.mean(0);b=b-b.mean(0)
        rho.append((a*b).mean(0)/np.maximum(np.sqrt((a*a).mean(0)*(b*b).mean(0)),1e-12))
    r1,r2=rho
    aa=np.clip(np.divide(r2,r1,out=np.zeros(2),where=r1>.02),.05,.995)
    ff=np.clip(r1/aa,.05,.95)
    return {'a_ref':float(np.median(aa)),'f':float(np.median(ff)),'dt_ref':.2,'rho1_whitened':r1.tolist(),'rho2_whitened':r2.tolist(),'axis_a':aa.tolist(),'axis_f':ff.tolist(),'fit':'outer-training only; pooled moments of contiguous pose ids, not independent RF repetitions'}

def step_loss(H,e,mu,C):
    P=np.diag([.01,.01,np.radians(5.)**2,np.radians(.1)**2])
    S=H@P@H.transpose(0,2,1)+C
    K=np.linalg.solve(S,H@P).transpose(0,2,1)
    v=e-mu;dx=np.einsum('nij,nj->ni',K,v)
    return dx[:,2]**2

def train_all(rt,allq,Hdict):
    n4=rt['n4'];features=rt['features'];groups=rt['groups']
    full=allq[allq.channel=='full'].reset_index(drop=True)
    los=allq[allq.channel=='los'].set_index(['case','pose_id'])
    pol={};configs=[];density=[];risk_metrics=[]
    R0=np.diag([n4.R0_R,n4.R0_S])
    for held,tr,te in n4.feature_splits(np,full):
        train=full.loc[tr].reset_index(drop=True);test=allq[allq.route==held].reset_index(drop=True)
        w=n4.site_weights(np,pd,train)
        mu,C,mi=n4.fit_model(np,train,test,w,'POWER_BIN_JOINT',groups)
        mt,Ct,_=n4.fit_model(np,train,train,w,'POWER_BIN_JOINT',groups)
        mr,Cr,_=n4.fit_model(np,train,test,w,'SIMPLE_G4',groups)
        mrt,Crt,_=n4.fit_model(np,train,train,w,'SIMPLE_G4',groups)
        tp=temporal_fit(train,mt,Ct);tpr=temporal_fit(train,mrt,Crt)
        keys=list(zip(train.case,train.pose_id));lt=los.loc[keys].reset_index()
        dr=train.range_m.to_numpy()-lt.range_m.to_numpy();ds=train.s_fp.to_numpy()-lt.s_fp.to_numpy()
        labels=((abs(dr)>=.15)|(abs(ds)>=.1)).astype(int)
        risktrain=pd.concat([train,lt],ignore_index=True)
        rc=RandomForestClassifier(n_estimators=96,max_depth=6,min_samples_leaf=30,random_state=20261019,n_jobs=2)
        rc.fit(risktrain[features],np.r_[labels,np.zeros(len(labels),int)])
        risk=rc.predict_proba(test[features])[:,list(rc.classes_).index(1)]
        HH=np.array([Hdict[c][int(i)] for c,i in keys]);ee=train[['e_r','e_s']].to_numpy()
        target=(step_loss(HH,ee,mt,Ct)<step_loss(HH,ee,np.zeros_like(ee),np.broadcast_to(R0,(len(train),2,2)))).astype(int)
        uc=RandomForestClassifier(n_estimators=96,max_depth=6,min_samples_leaf=30,random_state=20261020,n_jobs=2)
        uc.fit(train[features],target)
        utility=uc.predict_proba(test[features])[:,list(uc.classes_).index(1)] if len(uc.classes_)>1 else np.full(len(test),uc.classes_[0])
        event=float(np.quantile(train.detector_s_span,.90))
        cfg={'held_route':held,'n_train_full':len(train),'train_routes':sorted(train.route.unique()),'POWER':mi,'temporal':tp,'temporal_rich':tpr,'event_q90':event,'risk_model':'NEW_RF96_DEPTH6; not historical P4 model','utility_model':'NEW common-prior training utility, not future/GT runtime inputs'}
        configs.append(cfg);print('FOLD_FIT',cfg,flush=True)
        for (cid,ch),ix in test.groupby(['case','channel']).indices.items():
            ix=np.asarray(ix);ix=ix[np.argsort(test.iloc[ix].pose_id.to_numpy())];q=test.iloc[ix]
            pol[(cid,ch)]={'q':q,'mu':mu[ix],'R':C[ix],'mu_rich':mr[ix],'R_rich':Cr[ix],'risk':risk[ix],'utility':utility[ix]}
            e=q[['e_r','e_s']].to_numpy()
            for name,mm,CC in [('POWER',mu[ix],C[ix]),('RICH',mr[ix],Cr[ix])]:
                rr=e-mm;ww=np.linalg.solve(np.linalg.cholesky(CC),rr[...,None])[...,0]
                for j,var in enumerate(['range','s']):
                    density.append({'case':cid,'channel':ch,'model':name,'field':var,'n':len(q),'residual_mean':float(rr[:,j].mean()),'residual_rmse':float(np.sqrt(np.mean(rr[:,j]**2))),'whitened_second_moment':float(np.mean(ww[:,j]**2)),'lag1':float(np.corrcoef(ww[:-1,j],ww[1:,j])[0,1])})
            if ch=='full':
                lq=los.loc[list(zip(q.case,q.pose_id))]
                yy=((abs(q.range_m.to_numpy()-lq.range_m.to_numpy())>=.15)|(abs(q.s_fp.to_numpy()-lq.s_fp.to_numpy())>=.1)).astype(int)
            else:yy=np.zeros(len(q),int)
            risk_metrics.append({'case':cid,'channel':ch,'n':len(q),'auc':float(roc_auc_score(yy,risk[ix])) if len(set(yy))>1 else None,'brier':float(brier_score_loss(yy,risk[ix])),'positive_fraction':float(yy.mean())})
    return pol,configs,density,risk_metrics
