#!/usr/bin/env python3
"""Time-correlation impact profile (14_TIME_CORRELATION_PROFILE_PLAN_KO.md). Offline on v3 arrays.

Q1 band decomposition of residuals propagated through the saved kernels, Q2 believed vs diagonal vs
realized polarization/range variance (R-scale factor x correlation factor), Q3 ACF in time vs travelled
distance and segment correlation time vs speed, Q4 normalized-innovation whiteness and gate rejection runs,
Q5 effective kernel length vs correlation time. No filter is re-run.
"""
from __future__ import annotations
import argparse, glob, math
from pathlib import Path
import numpy as np
import pandas as pd

ARMS=['BASE','CIR','WIDE_NOES','PWIDE_NOES','ORACLE']
DEG=180/math.pi

def ma(x,t,win):
    dt=float(np.median(np.diff(t)));w=max(1,int(round(win/dt)))
    return pd.Series(x).rolling(w,center=True,min_periods=1).mean().to_numpy()

def bands(x,t):
    c=np.full_like(x,x.mean());s30=ma(x,t,30.);s3=ma(x,t,3.)
    return {'const':c,'slow_gt30s':s30-c,'mid_3_30s':s3-s30,'fast_lt3s':x-s3}

def acf(x,L):
    x=np.asarray(x,float);x=x-x.mean();n=len(x);v=float(np.dot(x,x)/n)
    if v<=0 or n<4:return np.full(L,np.nan)
    L=min(L,n-1);return np.array([np.dot(x[:n-l],x[l:])/(n*v) for l in range(1,L+1)])

def e_fold(r,step):
    i=np.where(r<1/np.e)[0];return float((i[0]+1)*step) if len(i) else float(len(r)*step)

def ljung_box(u,L=10):
    u=u[np.isfinite(u)];n=len(u)
    if n<3*L:return np.nan,np.nan
    r=acf(u,L);Q=float(n*(n+2)*np.sum(r**2/(n-np.arange(1,L+1))))
    return Q,r[0]

def runs(mask):
    out=[];c=0
    for v in mask:
        if v:c+=1
        elif c:out.append(c);c=0
    if c:out.append(c)
    return np.array(out)

def analyse(f):
    Z=np.load(f);stem=Path(f).name.replace('_EB3_ARRAYS.npz','');case,_,bias=stem.rsplit('_',2)
    t=Z['t'];truth=Z['truth'];ev=Z['ev'];m=t>=30;dt=float(np.median(np.diff(t)))
    sdist=np.r_[0,np.cumsum(np.hypot(np.diff(truth[:,0]),np.diff(truth[:,1])))];speed=np.gradient(sdist,t)
    rows={k:[] for k in ('BAND','VAR','ACF','SEG','WHITE','KLEN')}
    for nm in ARMS:
        eps=Z[f'{nm}__eps'];Wp=Z[f'{nm}__Wpol'].astype(float);Wr=Z[f'{nm}__Wrng'].astype(float);R=Z[f'{nm}__R'];acc=Z[f'{nm}__acc'].astype(bool)
        dp=Z[f'{nm}__dp'];Pp=Z[f'{nm}__Pp'];Pm=Z[f'{nm}__P'];H=Z[f'{nm}__H'];hm=Z[f'{nm}__hm'] if f'{nm}__hm' in Z.files else None
        base={'case':case,'route':case[:2],'bias':bias,'arm':nm}
        for ch,x,W,Rk in (('pol',eps[:,1],Wp,R[:,1,1]),('range',eps[:,0],Wr,R[:,0,0])):
            c=W@x;head=dp[ev,2]
            # Q1 bands
            B=bands(x,t);tot2=float(np.mean(c**2))
            for bn,xb in B.items():
                cb=W@xb;rows['BAND'].append({**base,'channel':ch,'band':bn,'rms_input':float(np.sqrt(np.mean(xb[m]**2))),
                    'rms_heading_deg':DEG*float(np.sqrt(np.mean(cb**2))),'share_of_channel_mse':float(np.mean(cb*c)/tot2) if tot2>0 else np.nan,
                    'share_of_heading_mse':float(np.mean(cb*head)/np.mean(head**2))})
            # Q2 believed / diagonal / realized
            bel=float(np.mean((W**2)@Rk));dia=float(np.mean((W**2)@(x**2)));rea=tot2
            rows['VAR'].append({**base,'channel':ch,'believed_var_deg2':DEG**2*bel,'diag_realized_var_deg2':DEG**2*dia,'realized_mse_deg2':DEG**2*rea,
                'R_scale_factor':dia/bel if bel>0 else np.nan,'correlation_factor':rea/dia if dia>0 else np.nan,'total_overconfidence':rea/bel if bel>0 else np.nan,
                'heading_mse_deg2':DEG**2*float(np.mean(head**2)),'P_post_mean_deg2':DEG**2*float(np.mean(Pp[ev,2,2])),
                'nees_at_ev':float(np.mean(head**2/Pp[ev,2,2]))})
            # Q5 kernel length vs correlation time
            r=acf(x[m],400);tau_e=e_fold(r,dt);neg=np.where(r<=0)[0];l0=int(neg[0]) if len(neg) else len(r);tau_int=dt*(0.5+float(np.sum(r[:l0])))
            Leff=np.array([(np.abs(w).sum()**2)/max(np.sum(w**2),1e-300) for w in W])*dt
            rows['KLEN'].append({**base,'channel':ch,'tau_e_s':tau_e,'tau_int_s':tau_int,'kernel_Leff_s_median':float(np.median(Leff)),
                                 'Leff_over_tau_int':float(np.median(Leff)/tau_int) if tau_int>0 else np.nan,'one_plus_2sum_rho':1+2*float(np.sum(r[:l0]))})
            # Q3 ACF in time vs distance
            sg=np.arange(sdist[m][0],sdist[m][-1],0.02);xs=np.interp(sg,sdist[m],x[m]);rd=acf(xs,400)
            rows['ACF'].append({**base,'channel':ch,'rho_t_0p5s':float(r[max(0,int(round(.5/dt))-1)]),'rho_t_2s':float(r[max(0,int(round(2/dt))-1)]),
                'rho_t_10s':float(r[min(len(r)-1,int(round(10/dt))-1)]),'tau_e_time_s':tau_e,'tau_e_dist_m':e_fold(rd,0.02),
                'rho_d_0p1m':float(rd[4]),'rho_d_0p5m':float(rd[24]),'rho_d_2m':float(rd[99]) if len(rd)>99 else np.nan,
                'speed_median_mps':float(np.median(speed[m])),'speed_cv':float(np.std(speed[m])/max(np.mean(speed[m]),1e-9)),
                'stopped_frac':float(np.mean(speed[m]<0.01))})
            seg=np.floor((t-30)/30).astype(int)
            for sgi in np.unique(seg[m]):
                mk=m&(seg==sgi)
                if mk.sum()<40:continue
                rs=acf(x[mk],60);rows['SEG'].append({**base,'channel':ch,'segment':int(sgi),'tau_e_s':e_fold(rs,dt),'speed_mps':float(np.mean(speed[mk])),
                                                     'rms':float(np.sqrt(np.mean(x[mk]**2))),'mean':float(np.mean(x[mk]))})
        # Q4 whiteness of the normalized polarization innovation and gate runs
        mu=Z[f'{nm}__mu'];ehat=Z[f'{nm}__ehat'];z=Z['z']
        hpri=Z['hgt']+np.einsum('kij,kj->ki',H,Z[f'{nm}__dm'])-Z[f'{nm}__r_meas']   # = h(x_prior), from r_meas = h(GT) - h(prior) + H dm
        nu_s=z[:,1]-ehat-mu[:,1]-hpri[:,1];S=np.einsum('kj,kjl,kl->k',H[:,1,:],Pm,H[:,1,:])+R[:,1,1];u=nu_s/np.sqrt(S)
        Q_all,r1_all=ljung_box(u[m]);Q_acc,r1_acc=ljung_box(np.where(acc,u,np.nan)[m])
        rr=runs(~acc[m]);p=float(np.mean(~acc[m]))
        rows['WHITE'].append({**base,'u_rms':float(np.sqrt(np.mean(u[m]**2))),'u_rho1':r1_all,'LjungBox_Q10':Q_all,'chi2_10_99pct':23.21,
            'u_rho1_accepted':r1_acc,'reject_frac':p,'reject_run_mean':float(rr.mean()) if len(rr) else 0.,'reject_run_mean_if_independent':1/(1-p) if p<1 else np.nan,
            'reject_run_max':int(rr.max()) if len(rr) else 0})
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    fs=sorted(glob.glob(str(Path(a.input)/'**'/'*_EB3_ARRAYS.npz'),recursive=True));assert len(fs)==14,len(fs)
    dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True);acc={}
    for f in fs:
        for k,v in analyse(f).items():acc.setdefault(k,[]).extend(v)
    pd.set_option('display.width',260);pd.set_option('display.max_columns',40);pd.set_option('display.max_rows',400)
    D={k:pd.DataFrame(v) for k,v in acc.items()}
    for k,d in D.items():d.to_csv(dst/f'TCORR_{k}.csv',index=False)
    print('== Q1 share of channel heading MSE by residual time band (route median)\n'+D['BAND'].pivot_table(index=['channel','arm','route'],columns='band',values='share_of_channel_mse',aggfunc='median').round(3).to_string())
    print('\n== Q2 believed vs realized (route median)\n'+D['VAR'].groupby(['channel','arm','route'])[['believed_var_deg2','diag_realized_var_deg2','realized_mse_deg2','R_scale_factor','correlation_factor','total_overconfidence','nees_at_ev']].median().round(3).to_string())
    print('\n== Q3 ACF time vs distance (median)\n'+D['ACF'].groupby(['channel','arm'])[['rho_t_0p5s','rho_t_2s','rho_t_10s','tau_e_time_s','tau_e_dist_m','rho_d_0p1m','rho_d_0p5m','rho_d_2m','speed_median_mps','speed_cv','stopped_frac']].median().round(3).to_string())
    sg=D['SEG'];out=[]
    for (ch,arm),g in sg.groupby(['channel','arm']):
        ok=g.speed_mps>0.005;out.append({'channel':ch,'arm':arm,'n_seg':int(ok.sum()),'corr_tau_vs_inv_speed':float(np.corrcoef(g.tau_e_s[ok],1/g.speed_mps[ok])[0,1]) if ok.sum()>3 else np.nan})
    print('\n== Q3 segment correlation time vs 1/speed\n'+pd.DataFrame(out).round(3).to_string(index=False))
    print('\n== Q4 innovation whiteness and gate runs (median)\n'+D['WHITE'].groupby(['arm','route'])[['u_rms','u_rho1','LjungBox_Q10','u_rho1_accepted','reject_frac','reject_run_mean','reject_run_mean_if_independent','reject_run_max']].median().round(3).to_string())
    print('\n== Q5 kernel length vs correlation time (median)\n'+D['KLEN'].groupby(['channel','arm'])[['tau_e_s','tau_int_s','kernel_Leff_s_median','Leff_over_tau_int','one_plus_2sum_rho']].median().round(3).to_string())
    print('TCORR_ALL_PASS',flush=True)

if __name__=='__main__':main()
