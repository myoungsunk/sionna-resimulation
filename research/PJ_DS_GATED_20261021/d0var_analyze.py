import pandas as pd, numpy as np
S=pd.read_csv('results_d0var/D0V_SCORES.csv'); key=['case','bias','channel']
P=pd.read_csv('results_hpath/HP_SCORES.csv'); q=S[(S.channel=='full')&S.arm.isin(['BASE','MU_R_EXDS'])].merge(P,on=['case','bias','arm'])
print('QA vs previous runs', (q.heading_rmse_deg_x-q.heading_rmse_deg_y).abs().max())
def tab(ref, chn='full'):
    b=S[(S.arm==ref)&(S.channel==chn)].set_index(key); out=[]
    for arm,g in S[S.channel==chn].groupby('arm',sort=False):
        g=g.set_index(key); h=g.heading_rmse_deg/b.heading_rmse_deg; r=g.range_err_rmse_cm/b.range_err_rmse_cm; rd=g.radial_rmse_cm/b.radial_rmse_cm; xy=g.xy_rmse_cm/b.xy_rmse_cm
        out.append({'arm':arm,'heading':h.median(),'h_b':int((h<1).sum()),'h_w10':int((h>1.1).sum()),'h_worst':h.max(),'range':r.median(),'r_b':int((r<1).sum()),'r_w10':int((r>1.1).sum()),
                    'radial':rd.median(),'xy':xy.median(),'nees':g.heading_nees.median(),'h95':g.heading95.median(),'s_infl':g.frac_s_inflated.median(),'s_gate':g.frac_s_gated.median(),'r_infl':g.frac_r_inflated.median(),
                    'meas_s95':g.meas_s95.median(),'meas_r95':g.meas_r95.median(),'pol_used_es_rms':g.pol_used_es_rms.median()})
    return pd.DataFrame(out)
pd.set_option('display.width',250)
T=tab('BASE'); print(T.round(3).to_string()); T.to_csv('results_d0var/D0V_VS_BASE.csv',index=False)
L=tab('BASE','los'); print('LOS'); print(L[['arm','heading','h_w10','range','r_w10','s_gate','s_infl','r_infl']].round(3).to_string()); L.to_csv('results_d0var/D0V_LOS_VS_BASE.csv',index=False)
for arm in ['B_GATE5','C_INFL_R','BC_INFL_R_GATE5','MU_R+BC_INFL_R_GATE5','MU_R+C_INFL_R','MU_R+B_GATE5']:
    b=S[(S.arm=='BASE')&(S.channel=='full')].set_index(['case','bias']); g=S[(S.arm==arm)&(S.channel=='full')].set_index(['case','bias'])
    print(arm,'heading',(g.heading_rmse_deg/b.heading_rmse_deg).round(2).to_dict()); print('   range',(g.range_err_rmse_cm/b.range_err_rmse_cm).round(2).to_dict())
print(S[(S.channel=='full')&(S.arm=='BASE')][['case','bias','heading_rmse_deg','range_err_rmse_cm','heading_nees']].round(3).to_string())
