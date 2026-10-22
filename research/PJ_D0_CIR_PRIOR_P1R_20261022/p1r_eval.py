#!/usr/bin/env python3
"""P1R: can a single RF polarization update recover a large heading prior error?

Pre-registration: 00_P1R_PLAN_KO.md. Corrections over P1: prior covariance matched to the
error size, iterated (Gauss-Newton) update, per-arm calibrated R, and stage 1 (original +/-1 deg
model, extrapolation) separated from stage 2 (retrained on training routes with wide priors).
Position stays at GT; GT is used only to build priors and to score.
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
IN=REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz'
OFFS=[-8,-4,-2,-1,1,2,4,8]
FEATURES=['sF_+0','log_fp_power','fp_full']+[f'sF_{o:+d}' for o in OFFS]+[f'ds_{o:+d}' for o in OFFS]
DELTAS=[0,1,-1,2,-2,5,-5,10,-10,20,-20]
ARMS=['PRIOR_ONLY','RAW','CIR_ONLY','CIR_PLUS_D0','CIR_PLUS_D0_WIDE','D0_DIRECT','ORACLE_LOS']
GRID=np.arange(-30,31,dtype=float)
WIDE_MAX=20.;WIDE_REP=3;R_FIX=0.01;IEKF_IT=30
MODES=[(sm,rm,up) for sm in ('MATCH','FIX3') for rm in ('CAL','FIX') for up in ('IEKF','EKF')]
PRIMARY='SMATCH_RCAL_IEKF';LEGACY='SFIX3_RFIX_EKF'
LEGACY_QA={'LOCAL':{'R2':.9895594576244415,'R4':.9690172511858363,'R5':.9866996964612953},
           'GTREF':{'R2':.9880157018709935,'R4':.9690106002806752,'R5':.9858921711457884}}
SEED={'R2':11,'R4':12,'R5':13}

def mname(sm,rm,up):return f'S{sm}_R{rm}_{up}'
def rmse(v):v=np.asarray(v,float);return float(np.sqrt(np.mean(v*v)))
def mkm():
    return HistGradientBoostingRegressor(max_iter=160,learning_rate=.055,max_leaf_nodes=17,max_depth=5,
             min_samples_leaf=20,l2_regularization=1.,random_state=20261022)

class Grid:
    """Cubic Hermite interpolation of s(offset) using exact nodal values and analytic slopes."""
    def __init__(self,S,G):
        assert S.shape==G.shape and S.shape[1]==len(GRID);self.S=S;self.G=G
    def at(self,rows,x):
        x=np.clip(np.asarray(x,float),GRID[0],GRID[-1])
        k=np.clip(np.floor(x-GRID[0]).astype(int),0,len(GRID)-2);t=x-GRID[k]
        y0=self.S[rows,k];y1=self.S[rows,k+1];m0=self.G[rows,k];m1=self.G[rows,k+1]
        t2=t*t;t3=t2*t
        s=(2*t3-3*t2+1)*y0+(t3-2*t2+t)*m0+(-2*t3+3*t2)*y1+(t3-t2)*m1
        g=(6*t2-6*t)*y0+(3*t2-4*t+1)*m0+(-6*t2+6*t)*y1+(3*t2-2*t)*m1
        return s,g
    def node(self,rows,off):
        j=int(np.where(GRID==off)[0][0]);return self.S[rows,j],self.G[rows,j]

def load_grid(D,gdir):
    S=np.full((len(D),len(GRID)),np.nan);G=np.full_like(S,np.nan)
    files=sorted(Path(gdir).rglob('GRID_*.npz'));assert len(files)==14,[str(f) for f in files]
    pos={(c,p):i for i,(c,p) in enumerate(zip(D.case,D.pose_id))}
    for f in files:
        case=f.stem[5:].rsplit('_',1)[0];z=np.load(f)
        cols=np.searchsorted(GRID,z['offsets']);assert np.all(GRID[cols]==z['offsets'])
        rows=np.array([pos[(case,int(p))] for p in z['pose_id']])
        S[np.ix_(rows,cols)]=z['s'];G[np.ix_(rows,cols)]=z['g_deg']
    assert np.isfinite(S).all() and np.isfinite(G).all(),'GRID_INCOMPLETE'
    return Grid(S,G)

def prepare():
    D=pd.read_csv(IN).sort_values(['case','pose_id']).reset_index(drop=True)
    for o in OFFS:D[f'ds_{o:+d}']=D[f'sF_{o:+d}']-D['sF_+0']
    D['e_true']=D['sF_+0']-D['sL_+0']
    assert set(D.route)=={'R2','R4','R5'}
    return D

def feats(df,med):return df[FEATURES].replace([np.inf,-np.inf],np.nan).fillna(med).reset_index(drop=True)

def fit_cir(tr):
    med=tr[FEATURES].replace([np.inf,-np.inf],np.nan).median().fillna(0)
    return mkm().fit(feats(tr,med),tr.e_true.to_numpy()),med

def narrow_rows(tr,a):
    """Original P1 protocol: d0 from the stored +/-1 deg GT LUT, two copies of each row."""
    x=pd.concat([a,a],ignore_index=True)
    x['d0']=np.r_[tr['sF_+0'].to_numpy()-tr['sMGTp1_+0'].to_numpy(),tr['sF_+0'].to_numpy()-tr['sMGTm1_+0'].to_numpy()]
    return x,np.tile(tr.e_true.to_numpy(),2)

def wide_rows(tr,a,grid,rng):
    rows=np.tile(tr.index.to_numpy(),WIDE_REP);dl=rng.uniform(-WIDE_MAX,WIDE_MAX,len(rows))
    s,_=grid.at(rows,dl)
    x=pd.concat([a]*WIDE_REP,ignore_index=True);x['d0']=np.tile(tr['sF_+0'].to_numpy(),WIDE_REP)-s
    return x,np.tile(tr.e_true.to_numpy(),WIDE_REP)

def fit_d0(tr,grid,kind,rng):
    med=tr[FEATURES].replace([np.inf,-np.inf],np.nan).median().fillna(0);a=feats(tr,med)
    x,y=narrow_rows(tr,a) if kind=='NARROW' else wide_rows(tr,a,grid,rng)
    return mkm().fit(x,y),med

def calib_R(tr,grid,held):
    """Leave-one-route-out inside the two training routes; never touches the held route."""
    res={'RAW':[],'CIR_ONLY':[],'CIR_PLUS_D0':[],'CIR_PLUS_D0_WIDE':[]}
    for r in sorted(set(tr.route)):
        A=tr[tr.route!=r];B=tr[tr.route==r]
        res['RAW'].append(B.e_true.to_numpy())
        m,med=fit_cir(A);res['CIR_ONLY'].append(m.predict(feats(B,med))-B.e_true.to_numpy())
        rng=np.random.default_rng(SEED[held]*100+int(r[1:]))
        for arm,kind in (('CIR_PLUS_D0','NARROW'),('CIR_PLUS_D0_WIDE','WIDE')):
            m,med=fit_d0(A,grid,kind,rng);bb=feats(B,med)
            x,y=narrow_rows(B,bb) if kind=='NARROW' else wide_rows(B,bb,grid,rng)
            res[arm].append(m.predict(x)-y)
    R={k:float(np.mean(np.concatenate(v)**2)) for k,v in res.items()}
    R['ORACLE_LOS']=R['CIR_ONLY'];R['D0_DIRECT']=R_FIX;R['PRIOR_ONLY']=R_FIX
    return R

def update(grid,rows,x0,zc,sig,R,mode,gfix=None):
    """Scalar heading update in GT-offset coordinates. Returns posterior offset, P+, K, flags."""
    s0,g0=grid.at(rows,np.full(len(rows),x0))
    if gfix is not None:g0=gfix
    if mode=='EKF':
        K=sig*sig*g0/(sig*sig*g0*g0+R);x=x0+K*(zc-s0);P=(1-K*g0)*sig*sig
        return x,P,K,np.zeros(len(rows),bool),np.ones(len(rows),bool)
    x=np.full(len(rows),float(x0));conv=np.zeros(len(rows),bool)
    def cost(v):return (v-x0)**2/(sig*sig)+(zc-grid.at(rows,v)[0])**2/R
    for _ in range(IEKF_IT):
        si,Hi=grid.at(rows,x);K=sig*sig*Hi/(sig*sig*Hi*Hi+R)
        xn=np.clip(x0+K*(zc-si-Hi*(x0-x)),GRID[0],GRID[-1])
        # Gauss-Newton step with halving line search on the MAP cost (keeps the iterate from oscillating).
        J0=cost(x)
        for _h in range(6):
            bad=cost(xn)>J0+1e-12
            if not bad.any():break
            xn=np.where(bad,x+.5*(xn-x),xn)
        conv=np.abs(xn-x)<1e-4;x=xn
        if conv.all():break
    _,Hf=grid.at(rows,x);K=sig*sig*Hf/(sig*sig*Hf*Hf+R);P=(1-K*Hf)*sig*sig
    return x,P,K,np.abs(x)>=GRID[-1]-1e-9,conv

def interp_qa(grid,te,rows):
    sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'));import v_replay as V
    model=V.SourceFFD();out={}
    sub=np.arange(0,len(te),3)
    for off in (-12.5,-7.5,-2.5,2.5,7.5,12.5):
        ex=np.empty(len(sub))
        for cname,ix in pd.Series(np.arange(len(sub)),index=te.case.to_numpy()[sub]).groupby(level=0):
            ii=ix.to_numpy();case=next(c for c in V.MANIFEST['cases'] if c['id']==cname)
            poses=pd.DataFrame(json.loads((V.ROOT/case['samples_path']).read_text())).set_index('pose_id')
            co=poses.loc[te.pose_id.to_numpy()[sub[ii]],['x','y','yaw_body_deg']].to_numpy(float)
            co[:,2]=np.deg2rad(co[:,2]+off);hs=[]
            for i in range(0,len(co),32):hs.append(model.batch(co[i:i+32],case,gradient=True)[0][:,1])
            ex[ii]=np.concatenate(hs)
        s,_=grid.at(rows[sub],np.full(len(sub),off))
        out[str(off)]={'max_abs':float(np.max(np.abs(s-ex))),'rms':rmse(s-ex),'n':int(len(sub))}
        print(f'INTERP_QA off={off:+.1f} max={out[str(off)]["max_abs"]:.3g} rms={out[str(off)]["rms"]:.3g}',flush=True)
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--held',required=True,choices=['R2','R4','R5'])
    p.add_argument('--grid',required=True);p.add_argument('--out',required=True)
    p.add_argument('--skip-interp-qa',action='store_true');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    D=prepare();grid=load_grid(D,a.grid)
    for off,col in ((0,'sMGT_+0'),(1,'sMGTp1_+0'),(-1,'sMGTm1_+0')):
        dev=float(np.max(np.abs(grid.node(np.arange(len(D)),off)[0]-D[col].to_numpy())))
        assert dev<2e-5,('GRID_LUT_MISMATCH',off,dev)
    trm=D.route!=a.held;tr=D[trm];rows_te=np.where(~trm)[0];te=D[~trm].reset_index(drop=True)
    qa={'held':a.held,'train_n':int(trm.sum()),'test_n':len(te),'git_sha':os.environ.get('GITHUB_SHA','local'),
        'grid_lut_qa_max':{},'primary_mode':PRIMARY,'wide_prior':f'U(-{WIDE_MAX},{WIDE_MAX}) x{WIDE_REP}, training routes only',
        'position_prior':'GT fixed','recursive':False}
    for off,col in ((0,'sMGT_+0'),(1,'sMGTp1_+0'),(-1,'sMGTm1_+0')):
        qa['grid_lut_qa_max'][str(off)]=float(np.max(np.abs(grid.node(rows_te,off)[0]-te[col].to_numpy())))
    cir,medc=fit_cir(tr);cir_pred=cir.predict(feats(te,medc))
    rng=np.random.default_rng(SEED[a.held])
    nar,medn=fit_d0(tr,grid,'NARROW',rng);wid,medw=fit_d0(tr,grid,'WIDE',rng)
    Bn=feats(te,medn);Bw=feats(te,medw)
    R=calib_R(tr,grid,a.held);qa['R_cal']=R;print('R_CAL',json.dumps(R),flush=True)
    z=te['sF_+0'].to_numpy();sL=te['sL_+0'].to_numpy();es=te.e_true.to_numpy()
    gg=(te['sMGTp1_+0']-te['sMGTm1_+0']).to_numpy()/2
    met=[];cases=[];pk=[];nu0={}
    for delta in DELTAS:
        s0,_=grid.node(rows_te,delta)
        Xn=Bn.copy();Xn['d0']=z-s0;Xw=Bw.copy();Xw['d0']=z-s0
        ehat={'PRIOR_ONLY':z-s0,'RAW':np.zeros(len(te)),'CIR_ONLY':cir_pred,'CIR_PLUS_D0':nar.predict(Xn),
              'CIR_PLUS_D0_WIDE':wid.predict(Xw),'D0_DIRECT':z-s0,'ORACLE_LOS':es}
        nu0[delta]={k:z-v-s0 for k,v in ehat.items()}
        for sm,rm,up in MODES:
            mode=mname(sm,rm,up);sig=max(abs(delta),1.) if sm=='MATCH' else 3.
            for arm in ARMS:
                zc=z-ehat[arm];Rv=R[arm] if rm=='CAL' else R_FIX
                if arm=='PRIOR_ONLY':
                    x=np.full(len(te),float(delta));P=np.full(len(te),sig*sig);K=np.zeros(len(te))
                    clip=np.zeros(len(te),bool);conv=np.ones(len(te),bool)
                else:
                    x,P,K,clip,conv=update(grid,rows_te,float(delta),zc,sig,Rv,up)
                ab=np.abs(x);nees=x*x/np.maximum(P,1e-12)
                met.append({'route':a.held,'delta':delta,'abs_delta':abs(delta),'mode':mode,'sigma_mode':sm,
                    'R_mode':rm,'update':up,'arm':arm,'n':len(te),'sigma_psi':sig,'R':Rv,
                    'heading_rmse_deg':rmse(x),'heading_mae_deg':float(ab.mean()),'heading_signed_bias_deg':float(x.mean()),
                    'heading_q95_abs_deg':float(np.quantile(ab,.95)),'heading_q99_abs_deg':float(np.quantile(ab,.99)),
                    'heading_max_abs_deg':float(ab.max()),
                    'heading_improved_frac':float(np.mean(ab<abs(delta))) if delta else np.nan,
                    'nees_mean':float(nees.mean()),'nees_median':float(np.median(nees)),
                    'cover95':float(np.mean(ab<=1.96*np.sqrt(np.maximum(P,0)))),
                    'post_sigma_rms':float(np.sqrt(np.mean(np.maximum(P,0)))),
                    'los_rmse':rmse(zc-sL),'k_eps_rms_deg':rmse(K*(zc-sL)),
                    'clip_frac':float(clip.mean()),'nonconv_frac':float(1-conv.mean())})
                if mode==PRIMARY:
                    for cname,ix in te.groupby('case').groups.items():
                        ii=np.asarray(list(ix));sub=x[ii]
                        cases.append({'route':a.held,'case':cname,'delta':delta,'arm':arm,'heading_rmse_deg':rmse(sub),
                                      'heading_q95_abs_deg':float(np.quantile(np.abs(sub),.95)),
                                      'nees_mean':float(nees[ii].mean())})
                    if arm in ('CIR_ONLY','CIR_PLUS_D0','CIR_PLUS_D0_WIDE','ORACLE_LOS','RAW'):
                        pk.append(pd.DataFrame({'route':a.held,'case':te.case,'pose_id':te.pose_id,'delta':delta,'arm':arm,
                            'sF':z,'sL':sL,'h_prior':s0,'e_hat':ehat[arm],'d0':z-s0,'K':K,'P_post':P,'post_error_deg':x}))
        # GT-reference gain legacy path (QA only)
        if abs(delta)==1:
            for arm in ('CIR_PLUS_D0',):
                x,_,_,_,_=update(grid,rows_te,float(delta),z-ehat[arm],3.,R_FIX,'EKF',gfix=gg)
                met.append({'route':a.held,'delta':delta,'abs_delta':1,'mode':'GTREF_LEGACY','arm':arm,'n':len(te),
                            'heading_rmse_deg':rmse(x)})
        print(f'P1R_DELTA_DONE {a.held} {delta:+d}',flush=True)
    mm=pd.DataFrame(met)
    for mode,g in mm.groupby('mode'):
        if mode=='GTREF_LEGACY':continue
        base=g[g.arm=='PRIOR_ONLY'].set_index('delta').heading_rmse_deg
        mm.loc[g.index,'ratio_to_prior']=[r/base[d] if d else np.nan for r,d in zip(g.heading_rmse_deg,g.delta)]
    for key,mode in (('LOCAL',LEGACY),('GTREF','GTREF_LEGACY')):
        v=float(mm[(mm['mode']==mode)&(mm.arm=='CIR_PLUS_D0')&(mm.delta.isin([1,-1]))].heading_rmse_deg.mean())
        qa[f'legacy_{key}']=v;qa[f'legacy_{key}_diff']=abs(v-LEGACY_QA[key][a.held])
        if not (key=='LOCAL' and os.environ.get('P1R_SMOKE')):
            assert qa[f'legacy_{key}_diff']<1e-6,('LEGACY_MISMATCH',key,v)
    d0d=mm[(mm.arm=='D0_DIRECT')&(mm['mode']!='GTREF_LEGACY')]
    assert np.allclose(d0d.heading_rmse_deg,d0d.abs_delta,atol=1e-8),'D0_DIRECT_NOT_IDENTITY'
    gain=[]
    for ad in (1,2,5,10,20):
        o=nu0[ad]['ORACLE_LOS']-nu0[-ad]['ORACLE_LOS']
        for arm in ARMS:
            u=nu0[ad][arm]-nu0[-ad][arm];gain.append({'route':a.held,'abs_delta':ad,'arm':arm,'G':float(u@o/(o@o))})
    if not a.skip_interp_qa:qa['interp_qa']=interp_qa(grid,te,rows_te)
    mm.to_csv(out/f'{a.held}_P1R_METRICS.csv',index=False)
    pd.DataFrame(cases).to_csv(out/f'{a.held}_P1R_CASE.csv',index=False)
    pd.DataFrame(gain).to_csv(out/f'{a.held}_P1R_GAIN.csv',index=False)
    pd.concat(pk,ignore_index=True).to_csv(out/f'{a.held}_P1R_PACKET.csv.gz',index=False,compression='gzip')
    (out/f'{a.held}_P1R_QA.json').write_text(json.dumps(qa,indent=2))
    show=mm[(mm['mode']==PRIMARY)&(mm.arm.isin(['PRIOR_ONLY','RAW','CIR_ONLY','CIR_PLUS_D0','CIR_PLUS_D0_WIDE','ORACLE_LOS']))]
    print(show.pivot_table(index='delta',columns='arm',values='heading_rmse_deg').round(3).to_string(),flush=True)
    print(f'P1R_DONE {a.held} {json.dumps({k:v for k,v in qa.items() if k!="interp_qa"})}',flush=True)

if __name__=='__main__':main()
