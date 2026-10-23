#!/usr/bin/env python3
"""Aggregate full-state budget v4 (P1, P2, P3, P5) and d0 feedback (P4)."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args()
src=Path(a.input);dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
pd.set_option('display.width',280);pd.set_option('display.max_columns',40);pd.set_option('display.max_rows',600)
def cat(pat):
    fs=sorted(src.rglob(pat));return pd.concat([pd.read_csv(f) for f in fs],ignore_index=True) if fs else pd.DataFrame()
D={k:cat(f'*_FB_{k}_*.csv.gz') for k in ('POS','TS','SHARE','ENTRY','INC','LAG','LAGX')}
n_case=D['POS'].case.nunique();n_seed=D['POS'].groupby('case').seed_idx.nunique()
print(f'cases={n_case} seeds_per_case={n_seed.to_dict()}')
for k,d in D.items():d.to_csv(dst/f'FB_{k}.csv.gz',index=False)
K=['case','route','bias'];A=['BASE','CIR','WIDE_NOES','PWIDE_NOES','ORACLE']

# ---------- P1 position performance over seeds
P=D['POS'];cols=['heading_rmse_deg','xy_rmse_cm','radial_rmse_cm','tangential_rmse_cm','radial_bias_cm','tangential_bias_cm','xy_nees','xy_cov95',
                 'radial_cov95','tangential_cov95','heading_nees','heading_cov95','accept']
S1=P[P.window=='stable_30_plus'].groupby(K+['arm'])[cols].agg(['mean','std']);S1.columns=[f'{c}_{s}' for c,s in S1.columns];S1=S1.reset_index()
S1.to_csv(dst/'FB_P1_STABLE.csv',index=False)
print('\n== P1 t>=30 s, mean over seeds (sd in FB_P1_STABLE.csv)\n'+P[P.window=='stable_30_plus'].groupby(K[:1]+['bias','arm'])[cols].mean().round(2).to_string())
pv=P.pivot_table(index=K+['seed_idx','window'],columns='arm',values=['heading_rmse_deg','xy_rmse_cm','radial_rmse_cm','tangential_rmse_cm'])
rows=[]
for (c,r,b,w),g in pv.groupby(level=[0,1,2,4]):
    row={'case':c,'route':r,'bias':b,'window':w,'n_seed':len(g)}
    for q in ('heading_rmse_deg','xy_rmse_cm','radial_rmse_cm','tangential_rmse_cm'):
        for arm in ('PWIDE_NOES','ORACLE','WIDE_NOES','CIR'):
            if (q,arm) not in g.columns:continue
            rt=g[(q,arm)]/g[(q,'BASE')];row[f'{q}|{arm}_over_BASE_mean']=float(rt.mean());row[f'{q}|{arm}_n_worse']=int((rt>1).sum())
            row[f'{q}|{arm}_minus_BASE_mean']=float((g[(q,arm)]-g[(q,'BASE')]).mean());row[f'{q}|{arm}_minus_BASE_sd']=float((g[(q,arm)]-g[(q,'BASE')]).std())
    rows.append(row)
PR=pd.DataFrame(rows);PR.to_csv(dst/'FB_P1_PAIRED.csv',index=False)
show=[c for c in PR.columns if 'PWIDE_NOES_over' in c or 'PWIDE_NOES_n_worse' in c]
print('\n== P1 paired PWIDE_NOES / BASE, t>=30 s\n'+PR[PR.window=='stable_30_plus'][['case','bias','n_seed']+show].round(2).to_string(index=False))
TR=P[P.arm.isin(['BASE','PWIDE_NOES','ORACLE'])].groupby(['case','bias','arm','window'])[['tangential_rmse_cm','radial_rmse_cm','heading_rmse_deg','xy_cov95']].mean().unstack('window')
TR.to_csv(dst/'FB_P1_TREND.csv');order=['w0_10','w10_30','w30_60','w60_90','w90_120','w120_180','w180_plus']
print('\n== P1 time trend of tangential RMSE (cm), mean over seeds\n'+TR['tangential_rmse_cm'][[w for w in order if w in TR['tangential_rmse_cm'].columns]].round(2).to_string())

# ---------- P2 full-state source shares (t>=30 s)
S=D['SHARE'];comp=['heading_share','radial_share','tangential_share']
S2=S.groupby(K+['arm','part'])[comp+['heading_rms','radial_rms','tangential_rms']].median().reset_index();S2.to_csv(dst/'FB_P2_SHARE_MEDIAN.csv',index=False)
for c in comp:
    print(f'\n== P2 {c} of MSE, median over seeds\n'+S2.pivot_table(index=['case','bias','arm'],columns='part',values=c).round(3)[
        ['initial','odom','gyro','range','pol','pol_c1','pol_c2','unexplained']].to_string())
# gap decomposition vs BASE in MSE units: share x total MSE
S=S.copy();S['tangential_contrib_cm2']=S.tangential_share*S.tangential_total_mse_cm2;S['radial_contrib_cm2']=S.radial_share*S.radial_total_mse_cm2
S['heading_contrib_deg2']=S.heading_share*S.heading_total_mse_deg2
G=S.pivot_table(index=K+['seed_idx','part'],columns='arm',values=['tangential_contrib_cm2','radial_contrib_cm2','heading_contrib_deg2'])
gap=[]
for q in ('tangential_contrib_cm2','radial_contrib_cm2','heading_contrib_deg2'):
    for arm in ('PWIDE_NOES','ORACLE'):
        x=(G[(q,arm)]-G[(q,'BASE')]).groupby(level=[0,1,2,4]).mean().rename('gap_mean').reset_index();x['quantity']=q;x['arm']=arm;gap.append(x)
GP=pd.concat(gap);GP.to_csv(dst/'FB_P2_GAP.csv',index=False)
print('\n== P2 tangential MSE gap PWIDE_NOES - BASE by source (cm^2, mean over seeds)\n'+
      GP[(GP.quantity=='tangential_contrib_cm2')&(GP.arm=='PWIDE_NOES')].pivot_table(index=['case','bias'],columns='part',values='gap_mean').round(2)[
          ['initial','odom','gyro','range','pol','unexplained']].to_string())

# ---------- P3 paths
E=D['ENTRY'];E3=E.groupby(K+['arm','part'])[comp].median().reset_index();E3.to_csv(dst/'FB_P3_ENTRY_MEDIAN.csv',index=False)
for c in ('tangential_share','radial_share','heading_share'):
    sub=E3[E3.part.str.startswith(('pol|','range|','initial|','gyro|','odom|'))]
    print(f'\n== P3a {c} by source|entry component, median over seeds\n'+sub.pivot_table(index=['case','bias','arm'],columns='part',values=c).round(3).to_string())
I=D['INC'];I3=I.groupby(K+['arm','part'])[['radial_share','tangential_share','radial_rms','tangential_rms']].median().reset_index();I3.to_csv(dst/'FB_P3_INC_MEDIAN.csv',index=False)
for g in ('ALL','pol'):
    sub=I3[I3.part.str.startswith(g+'|')]
    print(f'\n== P3b tangential share by increment term, source={g}\n'+sub.pivot_table(index=['case','bias','arm'],columns='part',values='tangential_share').round(3).to_string())
    print(f'\n== P3b tangential RMS (cm) by increment term, source={g}\n'+sub.pivot_table(index=['case','bias','arm'],columns='part',values='tangential_rms').round(2).to_string())

# ---------- P5 lag bins
L=D['LAG']
if len(L):
    L5=L.groupby(K+['arm','input','component','lag_bin'])[['share_of_input_part','share_of_total_mse','rms','abs_weight_frac']].median().reset_index();L5.to_csv(dst/'FB_P5_LAG_MEDIAN.csv',index=False)
    for c in ('heading','tangential'):
        sub=L5[(L5.input=='pol')&(L5.component==c)]
        print(f'\n== P5 pol residual, {c}: signed share of total MSE by lag bin (median over seeds)\n'+sub.pivot_table(index=['case','bias','arm'],columns='lag_bin',values='share_of_total_mse').round(3).to_string())
        print(f'\n== P5 pol residual, {c}: abs weight fraction by lag bin\n'+sub.pivot_table(index=['case','bias','arm'],columns='lag_bin',values='abs_weight_frac').round(3).to_string())
    X=D['LAGX'];X['diag']=X.bin_i==X.bin_j
    XS=X.groupby(K+['seed_idx','arm','input','component','diag']).cross_over_input_mse.sum().unstack('diag').rename(columns={True:'diag_sum',False:'offdiag_sum'}).reset_index()
    XS=XS.groupby(K+['arm','input','component'])[['diag_sum','offdiag_sum']].median().reset_index();XS.to_csv(dst/'FB_P5_CROSS.csv',index=False)
    print('\n== P5 diag vs off-diagonal (cross-bin) part of pol-induced MSE, median\n'+XS[XS.input=='pol'].pivot_table(index=['case','bias','arm'],columns='component',values=['diag_sum','offdiag_sum']).round(3).to_string())

# ---------- P4 d0 feedback
CU=cat('*_D0FB_CURVE.csv');PA=cat('*_D0FB_PAIRED.csv');LO=cat('*_D0FB_LOCAL.csv');TS=cat('*_D0FB_TS.csv.gz')
if len(CU):
    CU.to_csv(dst/'D0FB_CURVE.csv',index=False)
    sel=CU[CU.delta.isin([-5.,-2.,-1.,1.,2.,5.,-0.1,-0.05,0.05,0.1])]
    print('\n== P4A innovation curve around GT: kappa (1 = physics slope kept)\n'+sel.pivot_table(index=['kind','arm','delta'],columns='case',values='kappa_rel_infoweighted').round(3).to_string())
    print('\n== P4A fraction of frames with kappa_rel <= 0\n'+sel.pivot_table(index=['kind','arm','delta'],columns='case',values='frac_kappa_rel_le0').round(3).to_string())
    print('\n== P4A nearest root |delta*| of nu (deg or m) and multi-root fraction\n'+CU[CU.delta==1.0].pivot_table(index=['kind','arm'],columns='case',values=['root_abs_median','frac_multi_root']).round(3).to_string())
if len(PA):
    PA.to_csv(dst/'D0FB_PAIRED.csv',index=False);TS[TS.case=='R5_aB_m0'].to_csv(dst/'D0FB_TS_R5_aB_m0.csv.gz',index=False);LO.to_csv(dst/'D0FB_LOCAL.csv',index=False)
    st=PA[PA.window=='stable_30_plus']
    print('\n== P4B paired replay, t>=30 s heading RMSE (deg), mean over seeds\n'+st.pivot_table(index=['case','bias','arm'],columns='offset_deg',values='heading_rmse_deg').round(2).to_string())
    print('\n== P4B final 10 s heading mean (deg) by seed (R5_aB_m0)\n'+st[st.case=='R5_aB_m0'].pivot_table(index=['bias','seed_idx','arm'],columns='offset_deg',values='final10_heading_mean_deg').round(2).to_string())
    print('\n== P4B gate change fraction vs zero offset, mean over seeds\n'+st.pivot_table(index=['case','bias','arm'],columns='offset_deg',values='gate_change_frac').round(3).to_string())
    print('\n== P4B corrector output change / d0 change (PWIDE_CL, PWIDE_OB), all windows w0_10\n'+
          PA[(PA.window=='w0_10')&PA.arm.isin(['PWIDE_CL','PWIDE_OB'])].pivot_table(index=['case','bias','arm'],columns='offset_deg',values='ehat_over_d0_change').round(3).to_string())
    print('\n== P4B local kappa_rel along the prior (offset 0), median over seeds\n'+
          LO[LO.offset_deg==0].pivot_table(index=['case','bias','around','window'],columns='delta_deg',values='kappa_rel_mean').round(3).to_string())

# ---------- QA
qa={'closure_max':0.,'parity_max':0.,'kernel_max':0.,'d0fb_parity_max':0.}
for f in sorted(src.rglob('*_FB_QA_*.json')):
    q=json.loads(f.read_text())
    for v in q['closure'].values():
        for arm,d in v.items():
            qa['closure_max']=max(qa['closure_max'],d['closure'],d['closure_entry'],d['closure_increment'])
            qa['kernel_max']=max(qa['kernel_max'],d.get('kernel_vs_propagate_pol',0.),d.get('kernel_vs_propagate_range',0.))
    for v in q['parity'].values():qa['parity_max']=max(qa['parity_max'],max(v))
for f in sorted(src.rglob('*_D0FB_QA.json')):
    for v in json.loads(f.read_text())['parity'].values():qa['d0fb_parity_max']=max(qa['d0fb_parity_max'],max(v))
qa['n_fb_qa']=len(list(src.rglob('*_FB_QA_*.json')));qa['n_d0fb_qa']=len(list(src.rglob('*_D0FB_QA.json')))
(dst/'FB_QA.json').write_text(json.dumps(qa,indent=2));print('FB_AGG_PASS '+json.dumps(qa),flush=True)
