#!/usr/bin/env python3
"""Verification 1: decompose the refined polarization observation error on ladder-1 trajectories.

total = z_s - ehat(d0_prior) - mu - h_s(GT) = c1 + c2 + c3
  c1 = e - ehat(d0_GT) - mu      corrector residual at the true state
  c2 = ehat(d0_GT) - ehat(d0_prior)  state-error induced (WIDE only)
  c3 = s_LoS - h_s(GT)           LUT mismatch
Arms L_BASE, L_CIR, L_WIDE (all R = POWER V_s). Offline analysis only: GT and s_LoS are read
for decomposition and scoring; no filter is re-run.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import p2_replay as R2
from p2_replay import V

ARMS=['L_BASE','L_CIR','L_WIDE']
BLOCK=10.

def wbias(g,x,R,m):
    """Linearised weighted bias: sum g x / R / sum g^2 / R over mask m (degrees, x in s-units)."""
    if m.sum()<5:return float('nan')
    w=1./R[m];return float(np.sum(g[m]*x[m]*w)/np.sum(g[m]**2*w))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--models',required=True)
    ap.add_argument('--series',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    pack=joblib.load(a.models);assert pack['held']==Hr and Hr not in pack['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    pk=pk[pk.case==a.case].sort_values('pose_id')
    ser=pd.read_csv(a.series)
    model=V.SourceFFD();rows=[];blocks=[];summ=[];strata=[]
    for bias in ('B0','L2'):
        stem=f'{a.case}_full_{bias}'
        old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only'];n=len(t)
        d=obs[(obs.case==a.case)&(obs.channel=='full')].set_index('pose_id').loc[ids]
        zs=d['s_fp'].to_numpy(float)
        P=pk.set_index('pose_id').loc[ids];sL=P['sL_+0'].to_numpy();e=P['sF_+0'].to_numpy()-sL
        fpsh=P['fp_shift_tap'].to_numpy(float)
        features,_=R2.full_features(pk,ids);assert np.max(np.abs(features['sF_+0'].to_numpy()-zs))<1e-9
        mu0,R0=V.base_params(param,a.case,'full',ids,'POWER_DIAG');mus=mu0[:,1];Vs=R0[:,1,1]
        hgt=np.concatenate([model.batch(truth[i:i+32,:3],case,gradient=True)[0][:,1] for i in range(0,n,32)])
        d0gt=zs-hgt
        bw=R2.m_inputs(features,pack['medians']['WIDE']).copy();bw['d0']=d0gt
        eh_gt_w=pack['models']['WIDE'].predict(bw)
        eh_cir=pack['models']['CIR_ONLY'].predict(R2.m_inputs(features,pack['medians']['CIR_ONLY']))
        st=ser[(ser.bias==bias)&(ser.channel=='full')].sort_values('k');assert len(st)==n and np.allclose(st.t_s.to_numpy(),t)
        c3=sL-hgt;blk=np.floor(t/BLOCK).astype(int)
        for arm in ARMS:
            acc=st[f'{arm}__acc'].to_numpy(bool);g=st[f'{arm}__gpsi'].to_numpy(float)
            herr=st[f'{arm}__heading_err_deg'].to_numpy(float);hpe=st[f'{arm}__heading_prior_err_deg'].to_numpy(float)
            d0p=st[f'{arm}__d0'].to_numpy(float);ehp=st[f'{arm}__ehat'].to_numpy(float)
            if arm=='L_BASE':
                assert np.allclose(ehp,0.);c1=e-mus;c2=np.zeros(n);mu_used=mus
            elif arm=='L_CIR':
                assert np.max(np.abs(ehp-eh_cir))<1e-9;c1=e-eh_cir;c2=np.zeros(n);mu_used=np.zeros(n)
            else:
                c1=e-eh_gt_w;c2=eh_gt_w-ehp;mu_used=np.zeros(n)
            tot=zs-ehp-mu_used-hgt
            assert np.max(np.abs(tot-(c1+c2+c3)))<1e-9
            state=d0p-d0gt                    # = h(GT) - h(prior)
            st_head=-g*hpe;st_pos=state-st_head
            rows.append(pd.DataFrame({'case':a.case,'route':Hr,'bias':bias,'arm':arm,'k':np.arange(n),'t_s':t,
                'acc':acc,'g':g,'R':Vs,'c1':c1,'c2':c2,'c3':c3,'total':tot,'heading_err':herr,'heading_prior_err':hpe,
                'd0_prior':d0p,'d0_gt':d0gt,'state_d0':state,'state_d0_heading':st_head,'state_d0_other':st_pos,
                'ehat_prior':ehp,'fp_shift_tap':fpsh}))
            for b in np.unique(blk):
                m=blk==b;ma=m&acc
                blocks.append({'case':a.case,'route':Hr,'bias':bias,'arm':arm,'block':int(b),'t0':float(b*BLOCK),'n':int(m.sum()),
                    'acc_frac':float(acc[m].mean()),'heading_err_mean':float(herr[m].mean()),'heading_prior_err_mean':float(hpe[m].mean()),
                    'c1_mean':float(c1[m].mean()),'c2_mean':float(c2[m].mean()),'c3_mean':float(c3[m].mean()),
                    'c1_acc_mean':float(c1[ma].mean()) if ma.any() else np.nan,'c2_acc_mean':float(c2[ma].mean()) if ma.any() else np.nan,
                    'd0_prior_mean':float(d0p[m].mean()),'state_d0_mean':float(state[m].mean()),
                    'state_d0_heading_mean':float(st_head[m].mean()),'state_d0_other_mean':float(st_pos[m].mean()),
                    'fp_shift_nonzero_frac':float(np.mean(fpsh[m]!=0)),
                    'wb_total':wbias(g,tot,Vs,ma),'wb_c1':wbias(g,c1,Vs,ma),'wb_c2':wbias(g,c2,Vs,ma),'wb_c3':wbias(g,c3,Vs,ma)})
            for win,(t0,t1) in (('all',(0,np.inf)),('stable_30_plus',(30,np.inf)),('early_0_10',(0,10))):
                m=(t>=t0)&(t<t1);ma=m&acc
                summ.append({'case':a.case,'route':Hr,'bias':bias,'arm':arm,'window':win,'n':int(m.sum()),'acc_frac':float(acc[m].mean()),
                    'heading_err_mean':float(herr[m].mean()),'heading_err_rmse':float(np.sqrt(np.mean(herr[m]**2))),
                    'heading_prior_err_mean':float(hpe[m].mean()),
                    **{f'{c}_mean':float(v[m].mean()) for c,v in (('c1',c1),('c2',c2),('c3',c3),('total',tot))},
                    **{f'{c}_acc_mean':float(v[ma].mean()) for c,v in (('c1',c1),('c2',c2),('c3',c3),('total',tot))},
                    **{f'{c}_rms':float(np.sqrt(np.mean(v[m]**2))) for c,v in (('c1',c1),('c2',c2),('c3',c3),('total',tot))},
                    'state_d0_heading_rms':float(np.sqrt(np.mean(st_head[m]**2))),'state_d0_other_rms':float(np.sqrt(np.mean(st_pos[m]**2))),
                    'wb_total':wbias(g,tot,Vs,ma),'wb_c1':wbias(g,c1,Vs,ma),'wb_c2':wbias(g,c2,Vs,ma),'wb_c3':wbias(g,c3,Vs,ma)})
            for lab,m in (('fp_shift=0',fpsh==0),('fp_shift!=0',fpsh!=0),('|fp_shift|>=2',np.abs(fpsh)>=2)):
                strata.append({'case':a.case,'route':Hr,'bias':bias,'arm':arm,'stratum':lab,'frac':float(m.mean()),
                    'c1_mean':float(c1[m].mean()) if m.any() else np.nan,'c1_rms':float(np.sqrt(np.mean(c1[m]**2))) if m.any() else np.nan,
                    'c2_mean':float(c2[m].mean()) if m.any() else np.nan})
        print(f'V1_DONE {stem}',flush=True)
    pd.concat(rows,ignore_index=True).to_csv(out/f'{a.case}_V1_PACKETS.csv.gz',index=False,compression='gzip')
    pd.DataFrame(blocks).to_csv(out/f'{a.case}_V1_BLOCKS.csv',index=False)
    pd.DataFrame(summ).to_csv(out/f'{a.case}_V1_SUMMARY.csv',index=False)
    pd.DataFrame(strata).to_csv(out/f'{a.case}_V1_STRATA.csv',index=False)
    print('V1_CASE_PASS',a.case,flush=True)

if __name__=='__main__':main()
