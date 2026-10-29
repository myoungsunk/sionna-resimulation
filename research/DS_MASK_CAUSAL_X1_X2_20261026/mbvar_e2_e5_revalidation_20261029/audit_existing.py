#!/usr/bin/env python3
"""Read-only correction/reaggregation of original run 40820579727.
Does not overwrite the historical verdict. Strict E4 manipulation eligibility is
post-hoc sensitivity analysis, not a silently changed preregistration.
"""
import argparse, hashlib, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

def cat(root,pattern):return pd.concat([pd.read_csv(p) for p in sorted(root.glob(pattern))],ignore_index=True)
def main(root,out):
    out.mkdir(parents=True,exist_ok=True)
    A=cat(root,'A_SCORES_*.csv');AS=cat(root,'A_SUMMARY_*.csv')
    C=AS[(AS['set']=='S_base')&(AS.window=='all')].groupby(['case','arm','comp'])[['mr_dh2_HPH','mr_He2_HPH','ell_share','E_2He_ell']].median().reset_index()
    C.to_csv(out/'C0_HE_AND_NONLINEARITY.csv',index=False)
    A[A.case=='R5_aB_m0'].to_csv(out/'R5B_ALL_SEEDS.csv',index=False)
    # E1 sx contains only 1..9. Merge seed0 explicitly instead of describing 9 as 10.
    E1=cat(root,'E1_*_s0.csv');sx=cat(root,'E1_*_sx.csv');E1=pd.concat([E1,sx],ignore_index=True)
    assert not E1.duplicated(['case','arm','seed','treat','m','rep']).any()
    b=E1[E1.treat=='BASE'][['case','arm','seed','head_rmse','xy_rmse_cm']].rename(columns={'head_rmse':'base_head','xy_rmse_cm':'base_xy'})
    E1=E1.merge(b,on=['case','arm','seed'],validate='many_to_one')
    E1['delta_head']=E1.head_rmse-E1.base_head;E1['delta_xy']=E1.xy_rmse_cm-E1.base_xy
    e=E1[(E1.treat!='BASE')&E1.m.isin([4,8])].groupby(['case','arm','seed','treat','m'])[['delta_head','delta_xy']].mean().reset_index()
    q=e.groupby(['case','arm','treat','m']).agg(n_seed=('seed','nunique'),delta_head_median=('delta_head','median'),delta_xy_median=('delta_xy','median'),n_head_improve=('delta_head',lambda x:int((x<0).sum()))).reset_index()
    q.to_csv(out/'E1_PAIRED_ALL10.csv',index=False)
    # Empty-est NA group drop: pair within same case/arm/seed.
    E=cat(root,'E23_*.csv');E['est']=E.est.fillna('NOT_APPLICABLE')
    b=E[E.family=='BASE'][['case','arm','seed','head_rmse','xy_rmse_cm']].rename(columns={'head_rmse':'base_head','xy_rmse_cm':'base_xy'})
    E=E.merge(b,on=['case','arm','seed'],validate='many_to_one');E['delta_head']=E.head_rmse-E.base_head;E['delta_xy']=E.xy_rmse_cm-E.base_xy
    q=E[E.family!='BASE'].groupby(['case','arm','family','treat','est'],dropna=False).agg(n_seed=('seed','nunique'),delta_head_median=('delta_head','median'),delta_xy_median=('delta_xy','median'),n_head_improve=('delta_head',lambda x:int((x<0).sum()))).reset_index()
    q.to_csv(out/'E23_REAGGREGATED_NO_NA_DROP.csv',index=False)
    assert len(q[q.family=='E2'])==24
    E4=cat(root,'E4_*_s*.csv');perm=E4[E4.treat=='PERM'].copy()
    perm['bad_original']=perm.chk_lag1_s_dm>=.1
    perm['bad_abs_s']=abs(perm.chk_lag1_s_dm)>=.1
    perm['bad_abs_both']=(abs(perm.chk_lag1_s_dm)>=.1)|(abs(perm.chk_lag1_r_dm)>=.1)
    uq=perm.drop_duplicates(['case','seed','treat','L_s','rep'])
    manipulation=dict(rows_including_arms_and_masks=len(perm),unique_permutations=len(uq),original_bad_rows=int(perm.bad_original.sum()),abs_s_bad_rows=int(perm.bad_abs_s.sum()),abs_both_bad_rows=int(perm.bad_abs_both.sum()),original_bad_unique=int(uq.bad_original.sum()),abs_s_bad_unique=int(uq.bad_abs_s.sum()),abs_both_bad_unique=int(uq.bad_abs_both.sum()))
    (out/'E4_MANIPULATION_COUNTS.json').write_text(json.dumps(manipulation,indent=2))
    allrows=[]
    for rule in ['ORIGINAL_S_LT_01','ABS_BOTH_LT_01']:
        ok=(E4.treat!='PERM')|((E4.chk_lag1_s_dm<.1) if rule.startswith('ORIGINAL') else ((abs(E4.chk_lag1_s_dm)<.1)&(abs(E4.chk_lag1_r_dm)<.1)))
        d=E4[ok&(E4['mask']=='fixed')]
        med=d.groupby(['case','arm','seed','treat','L_s']).median(numeric_only=True).reset_index()
        for (c,a,s),g in med.groupby(['case','arm','seed']):
            i=g[g.treat=='ID'].iloc[0];pp=g[g.treat=='PERM']
            if not len(pp):continue
            p=pp.iloc[0];c1=abs(p.s_cross_share)<=.1
            c2=(abs(np.log(p.head_z_rms))<abs(np.log(i.head_z_rms)))&(abs(np.log(p.s_mr_dh2_HPH))<abs(np.log(i.s_mr_dh2_HPH)))
            c3=(p.head_rmse<i.head_rmse)&(p.xy_rmse_cm<i.xy_rmse_cm)
            allrows.append(dict(rule=rule,case=c,arm=a,seed=s,c1=c1,c2=c2,c3=c3,all123=c1&c2&c3,id_head=i.head_rmse,perm_head=p.head_rmse,id_xy=i.xy_rmse_cm,perm_xy=p.xy_rmse_cm,id_cross=i.s_cross_share,perm_cross=p.s_cross_share))
    j=pd.DataFrame(allrows);j.to_csv(out/'E4_STRICT_MANIP_PAIRED.csv',index=False)
    j.groupby(['rule','case','arm']).agg(n_seed=('seed','nunique'),n_all123=('all123','sum'),n_c1=('c1','sum'),n_c2=('c2','sum'),n_c3=('c3','sum'),id_head=('id_head','median'),perm_head=('perm_head','median'),id_xy=('id_xy','median'),perm_xy=('perm_xy','median')).to_csv(out/'E4_STRICT_MANIP_SUMMARY.csv')
    original=pd.read_csv(root/'JUDGE_E4_CRITERIA.csv').sort_values(['case','arm','seed']).reset_index(drop=True)
    ours=j[j.rule=='ORIGINAL_S_LT_01'].sort_values(['case','arm','seed']).reset_index(drop=True)
    assert np.array_equal(original.all123.to_numpy(),ours.all123.to_numpy())
    dump=dict(original_run=40820579727,source_ref='422b6c0',utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),command=sys.argv,notes=['No EKF rerun in this script','Original E4 criteria reproduced; absolute-both is post-hoc sensitivity','E1 seed0 explicitly combined with sx seeds1..9','E2 empty-est group loss fixed'],inputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in root.glob('*.csv')},outputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.glob('*') if f.is_file()})
    (out/'MANIFEST_REAGGREGATION.json').write_text(json.dumps(dump,indent=2))
    print(json.dumps(manipulation,indent=2));print('E2 rows retained:',len(q[q.family=='E2']))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();main(Path(a.input),Path(a.out))
