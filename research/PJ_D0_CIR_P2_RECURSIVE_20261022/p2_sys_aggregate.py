#!/usr/bin/env python3
"""Aggregate the system-level verification (stages 1-3). Magnitudes only, no pass/fail thresholds."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args()
src=Path(a.input);dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
pd.set_option('display.width',280);pd.set_option('display.max_columns',40);pd.set_option('display.max_rows',800)
def cat(pat):
    fs=sorted(src.rglob(pat));return pd.concat([pd.read_csv(f) for f in fs],ignore_index=True) if fs else pd.DataFrame()
mc=pd.read_csv(Path(__file__).resolve().parent/'results_eb2_mc/MC_ALL.csv')
pv=mc.pivot_table(index=['case','bias','seed_idx'],columns='arm',values='stable_30_plus_heading_rmse_deg')
MCR=(pv.PWIDE_NOES/pv.BASE).groupby(level=[0,1]).mean().rename('mc_heading_ratio_pwide_base').reset_index()
qa={}
# ---------------- stage 1
s1={k:cat(f'SYS_{k}.csv') for k in ('V1KER','V1PRED','V1BAND','V2','V2P','V4','V6','V7','GAMMA_PARAMS','QA')}
if len(s1['V1KER']):
    for k,d in s1.items():d.to_csv(dst/f'SYS_{k}.csv',index=False)
    print('== V1 explained kernel energy (median over evaluation times), modulated vs unmodulated basis\n'+
          s1['V1KER'].groupby('arm')[['EF_shared_shape_modulated','EF_shared_shape_unmodulated','EF_modulated_median','EF_unmodulated_median','EF_modulated_p10','EF_unmodulated_p10']].median().round(3).to_string())
    c=[x for x in s1['V1PRED'].columns if x.startswith('R2_')]
    print('\n== V1 R^2 of predictors of the pol heading component c(t), median over case x bias\n'+s1['V1PRED'].groupby('arm')[c].median().round(3).to_string())
    print('\n== V1 band shares: eps through the true kernel vs u = g eps / R through the fitted modulated kernel (route median)\n'+
          s1['V1BAND'].pivot_table(index=['arm','route'],columns='band',values=['share_eps_through_W','share_u_through_fitted_a'],aggfunc='median').round(3).to_string())
    V2=s1['V2'];cols=[x for x in V2.columns if x.startswith(('realized','expected'))]
    print('\n== V2 pol-only (true positions) GLS vs WLS vs the EKF pol component, crossfit Gamma, route median\n'+
          V2[V2.gamma_source=='crossfit'].groupby(['arm','window_s','route'])[cols].median().round(3).to_string())
    P2=s1['V2P'];base=P2[P2.variant=='base'][['case','bias','arm','heading_rmse_deg','tangential_rmse_cm','heading_nees']].rename(
        columns={'heading_rmse_deg':'h0','tangential_rmse_cm':'t0','heading_nees':'n0'})
    P2=P2.merge(base,on=['case','bias','arm']);P2['heading_ratio_to_base']=P2.heading_rmse_deg/P2.h0;P2['tangential_ratio_to_base']=P2.tangential_rmse_cm/P2.t0
    P2.to_csv(dst/'SYS_V2P_RATIO.csv',index=False)
    for q in ('heading_ratio_to_base','tangential_ratio_to_base','heading_nees'):
        print(f'\n== V2\' {q} (case rows, B0 / L2 averaged), crossfit\n'+P2[P2.gamma_source=='crossfit'].pivot_table(index=['arm','case'],columns='variant',values=q,aggfunc='mean').round(3).to_string())
    print('\n== V2\' crossfit vs insample agreement (heading ratio to base)\n'+P2[P2.variant!='base'].pivot_table(index=['arm','variant'],columns='gamma_source',values='heading_ratio_to_base',aggfunc='median').round(3).to_string())
    V4=s1['V4'];print('\n== V4 excitation by case (median over 60 s windows)\n'+V4.groupby(['case','arm'])[['g_abs_median','g_sd','g_sign_changes','eta_info_retention','corr_slow_eps_vs_g']].median().round(3).to_string())
    print('\n== V6 mount 0 vs 45 deg (R2_aA, B0)\n'+s1['V6'].round(3).to_string(index=False))
    print('\n== V7 revisit pairs\n'+s1['V7'].round(3).to_string(index=False))
    Q=s1['QA'];qa['stage1']={k:float(Q[Q.check==k].value.max()) for k in Q.check.unique()}
    j=sorted(src.rglob('SYS_QA.json'))
    if j:qa['stage1_json']=json.loads(j[0].read_text())
# ---------------- stage 2
N=cat('*_NOPOL_*.csv')
if len(N):
    N.to_csv(dst/'NOPOL_ALL.csv',index=False);st=N[N.window=='stable_30_plus']
    print('\n== V3 t>=30 s, mean over seeds\n'+st.groupby(['case','bias','arm'])[['heading_rmse_deg','xy_rmse_cm','tangential_rmse_cm','heading_nees','xy_cov95','accept']].mean().round(3).to_string())
    pw=st.pivot_table(index=['case','bias','seed_idx'],columns='arm',values=['heading_rmse_deg','xy_rmse_cm'])
    rows=[]
    for (c,b),g in pw.groupby(level=[0,1]):
        r={'case':c,'bias':b,'n_seed':len(g)}
        for q in ('heading_rmse_deg','xy_rmse_cm'):
            for arm in [x for x in g[q].columns if x!='NOPOL']:
                rt=g[(q,arm)]/g[(q,'NOPOL')];r[f'{q}|{arm}/NOPOL']=float(rt.mean());r[f'{q}|{arm}_worse_than_NOPOL']=int((rt>1).sum())
        rows.append(r)
    NR=pd.DataFrame(rows);NR.to_csv(dst/'NOPOL_RATIO.csv',index=False)
    print('\n== V3 ratio to NOPOL (mean over seeds) and number of seeds worse than NOPOL\n'+NR[['case','bias','n_seed']+[x for x in NR.columns if 'heading' in x]].round(2).to_string(index=False))
    qa['stage2_parity_max']=max([max(v) for f in src.rglob('*_NOPOL_QA_*.json') for v in json.loads(f.read_text())['parity'].values()],default=np.nan)
# ---------------- stage 3
I=cat('*_INNERLORO.csv')
if len(I):
    I.to_csv(dst/'INNERLORO_ALL.csv',index=False);c=[x for x in I.columns if x.endswith('_rms_deg')]+['packet_rms','slow30_rms','mean']
    print('\n== V5/X1 heading-equivalent bias by scope and arm (median over cases)\n'+I.groupby(['held','scope','arm'])[c].median().round(3).to_string())
    inner=I[I.scope=='inner_loro'].pivot_table(index=['held','case'],columns='arm',values='bpsi_60s_rms_deg')
    rr=(inner.PD0/inner.BASE).groupby(level=0).median().rename('inner_bpsi60_ratio_PD0_BASE').reset_index()
    rr['inner_bpsi60_ratio_PA2_BASE']=(inner.PA2/inner.BASE).groupby(level=0).median().to_numpy()
    MCR['held']=MCR.case.str[:2];C1=MCR.merge(rr,on='held',how='left');C1.to_csv(dst/'C1_INNER_VS_HELD.csv',index=False)
    print('\n== C1 inner (training-route-only) b_psi ratio vs held recursion ratio\n'+C1.round(3).to_string(index=False))
    hv=I[I.scope=='held'].pivot_table(index='case',columns='arm',values='bpsi_60s_rms_deg')
    if {'DEPLOYED_PD0','BASE_OOF'}<=set(hv.columns):
        hv['deployed_over_base']=hv.DEPLOYED_PD0/hv.BASE_OOF;hv=hv.merge(MCR[MCR.bias=='B0'].set_index('case')[['mc_heading_ratio_pwide_base']],left_index=True,right_index=True)
        hv.to_csv(dst/'HELD_BPSI_VS_RECURSION.csv');print('\n== held-route b_psi(60 s) vs recursion ratio\n'+hv.round(3).to_string())
        if len(hv)>3:qa['spearman_held_bpsi_ratio_vs_recursion']=float(spearmanr(hv.deployed_over_base,hv.mc_heading_ratio_pwide_base)[0])
    qa['stage3']={f.stem:json.loads(f.read_text()) for f in sorted(src.rglob('*_INNERLORO_QA.json'))}
(dst/'SYS_AGG_QA.json').write_text(json.dumps(qa,indent=2,default=float));print('SYS_AGG_DONE '+json.dumps(qa,default=float),flush=True)
