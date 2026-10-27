from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent
assert json.loads((R/'EXECUTION_RESULT.json').read_text())['status']=='TECHNICAL_PASS'
d=pd.read_csv(R/'SCORES.csv');primary=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
assert len(d)==196 and not d.duplicated(['stage','case','bias','arm']).any()
assert np.isfinite(d.select_dtypes('number').to_numpy()).all()
def reduction(before,after):
    if abs(before)<.01:return dict(f_signed=None,f_magnitude=None,sign_reversal=None,decision='NOT_IDENTIFIABLE')
    fs=1-after/before;fm=1-abs(after)/abs(before)
    return dict(f_signed=float(fs),f_magnitude=float(fm),sign_reversal=bool(before*after<0),decision='STRONG_GAP_REDUCTION' if fm>=.7 else 'PARTIAL' if fm>=.3 else 'WEAK')
gaps=[]
for stage,ab,am in [('E2','O_BB','O_MB'),('E3','BLOCK_BB','BLOCK_MB')]:
    for (case,bias),g in d[d.stage==stage].groupby(['case','bias'],sort=False):
        g=g.set_index('arm');baseline=d[(d.stage=='E1')&(d.case==case)&(d.bias==bias)].set_index('alpha')
        for metric in ['heading_bias_deg','heading_rmse_deg']:
            bb=baseline.loc[0,metric];mb=baseline.loc[1,metric];newbb=g.loc[ab,metric];newmb=g.loc[am,metric]
            gaps.append(dict(stage=stage,case=case,bias=bias,primary=case in primary,metric=metric,BB=bb,MB=mb,after_BB=newbb,after_MB=newmb,G_before=mb-bb,G_after=newmb-newbb,**reduction(mb-bb,newmb-newbb)))
gap=pd.DataFrame(gaps);gap.to_csv(R/'GAP_REDUCTIONS.csv',index=False)
dose=[]
for (case,bias),g in d[d.stage=='E1'].groupby(['case','bias'],sort=False):
    g=g.sort_values('alpha');av=abs(g.heading_bias_deg.to_numpy());std=g.heading_std_deg.to_numpy()
    dose.append(dict(case=case,bias=bias,primary=case in primary,abs_bias_nondecreasing=bool(np.all(np.diff(av)>=-1e-6)),std_nonincreasing=bool(np.all(np.diff(std)<=1e-6)),abs_bias_increase_deg=float(av[-1]-av[0]),std_change_deg=float(std[-1]-std[0]),range_ratio=float(g.range_rmse_cm.iloc[-1]/g.range_rmse_cm.iloc[0])))
pd.DataFrame(dose).to_csv(R/'DOSE_RESPONSE.csv',index=False)
gatea=[]
for (case,bias),g in d[d.stage=='E4a'].groupby(['case','bias']):
    g=g.set_index('arm')
    for metric in ['heading_rmse_deg','heading_bias_deg']:
        before=float(g.loc['BM',metric]-g.loc['BB',metric]);after=float(g.loc['BB_NEW_POL',metric]-g.loc['BB',metric]);valid=before>.01 if metric=='heading_rmse_deg' else abs(before)>.01
        ratio=after/before if valid else None
        gatea.append(dict(case=case,bias=bias,metric=metric,baseline_gap=before,addition_gap=after,reproduction_ratio=ratio,decision='NOT_IDENTIFIABLE' if ratio is None else 'APPROX_REPRODUCTION' if .7<=ratio<=1.3 else 'OVERSHOOT' if ratio>1.3 else 'LOW_REPRODUCTION'))
pd.DataFrame(gatea).to_csv(R/'GATE_SUFFICIENCY.csv',index=False)
gateb=[]
for (case,bias),g in d[d.stage=='E4b'].groupby(['case','bias']):
    g=g.set_index('arm');rmsegap=float(g.loc['RESTORE4','heading_rmse_deg']-g.loc['MB','heading_rmse_deg']);biasgap=float(g.loc['RESTORE4','heading_bias_deg']-g.loc['MB','heading_bias_deg'])
    for metric in ['heading_rmse_deg','heading_bias_deg','range_rmse_cm']:
        mb=float(g.loc['MB',metric]);drop=float(g.loc['DROP4',metric]);restore=float(g.loc['RESTORE4',metric]);nr=float(g.loc['MM_NEW_RANGE_ONLY',metric])
        gateb.append(dict(case=case,bias=bias,metric=metric,MB=mb,DROP4=drop,RESTORE4=restore,MM_NEW_RANGE_ONLY=nr,lost_effect_no_new=drop-mb,lost_effect_with_new=nr-restore,interaction=(nr-restore)-(drop-mb),heading_MSE_interaction=(nr**2-restore**2)-(drop**2-mb**2) if metric=='heading_rmse_deg' else None,restored_gap=restore-mb,return_to_MB=abs(rmsegap)<=.02 and abs(biasgap)<=.02))
pd.DataFrame(gateb).to_csv(R/'GATE_FACTORIAL.csv',index=False)
figdir=R/'figures';figdir.mkdir(exist_ok=True)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':170})
fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
for col,case in enumerate(primary):
    for bias,color,marker in [('B0','#27689b','o'),('L2','#c66c36','^')]:
        g=d[(d.stage=='E1')&(d.case==case)&(d.bias==bias)].sort_values('alpha')
        axes[0,col].plot(g.alpha,abs(g.heading_bias_deg),color=color,marker=marker,label=bias)
        axes[1,col].plot(g.alpha,g.heading_std_deg,color=color,marker=marker,label=bias)
    axes[0,col].set_title(case);axes[0,col].set_ylabel('|Heading bias| (deg)');axes[1,col].set_ylabel('Heading population std (deg)');axes[1,col].set_xlabel('Range correction alpha')
    for ax in axes[:,col]:ax.grid(alpha=.2);ax.legend();ax.set_xticks([0,.25,.5,.75,1])
fig.suptitle('E1 dose response | primary routes | paired B0/L2, not independent samples');fig.savefig(figdir/'01_dose_response.png');plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
for ax,stage,title in zip(axes,['E2','E3'],['E2: constant polarization oracle','E3: block direct range psi/bg update']):
    g=gap[(gap.stage==stage)&gap.primary&(gap.metric=='heading_bias_deg')].copy();labels=g.case+' / '+g.bias;x=np.arange(len(g))
    ax.bar(x-.18,g.G_before,width=.36,color='#7a8591',label='Before: MB - BB');ax.bar(x+.18,g.G_after,width=.36,color='#27689b',label='After intervention: MB - BB')
    ax.set_xticks(x,[a.replace(' / ','\n') for a in labels],rotation=30,ha='right');ax.axhline(0,color='#374151',lw=.8);ax.set_ylabel('Signed bias gap (deg)');ax.set_title(title);ax.legend(fontsize=8)
fig.suptitle('Gap contraction and sign reversal must be distinguished');fig.savefig(figdir/'02_gap_interventions.png');plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
for ax,stage,arms,title in [(axes[0],'E4a',['BB','BB_NEW_POL','BM'],'R5_aA: add new polarization only'),(axes[1],'E4b',['MB','DROP4','RESTORE4','MM_NEW_RANGE_ONLY'],'R2_aB: new range x lost-packet factorial')]:
    for bias,color,marker in [('B0','#27689b','o'),('L2','#c66c36','^')]:
        g=d[(d.stage==stage)&(d.bias==bias)].set_index('arm').loc[arms];ax.plot(range(len(arms)),g.heading_rmse_deg,color=color,marker=marker,label=bias)
    ax.set_xticks(range(len(arms)),[a.replace('MM_NEW_RANGE_ONLY','NEW_R + DROP4') for a in arms],rotation=15);ax.set_ylabel('Heading RMSE (deg)');ax.set_title(title);ax.grid(alpha=.2);ax.legend()
fig.savefig(figdir/'03_gate_interventions.png');plt.close(fig)
d.groupby(['stage','route','bias'],sort=False)[['heading_rmse_deg','heading_bias_deg']].count().to_csv(R/'ROW_COUNTS.csv')
(R/'ANALYSIS_SUMMARY.json').write_text(json.dumps(dict(dose_primary=[r for r in dose if r['primary']],gate_sufficiency=gatea,gate_factorial=gateb),indent=2),encoding='utf8')
print('Primary dose response:');print(pd.DataFrame(dose).query('primary').to_string(index=False))
print('Primary gap reduction:');print(gap[gap.primary][['stage','case','bias','metric','G_before','G_after','f_magnitude','sign_reversal','decision']].to_string(index=False))
print('E4a:');print(pd.DataFrame(gatea).to_string(index=False));print('E4b:');print(pd.DataFrame(gateb).to_string(index=False))
