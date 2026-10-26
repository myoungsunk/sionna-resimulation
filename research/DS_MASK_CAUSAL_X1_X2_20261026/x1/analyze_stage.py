from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parent
assert json.loads((ROOT/'EXECUTION_RESULT.json').read_text())['status']=='TECHNICAL_PASS'
s = pd.read_csv(ROOT/'X1_SCORES.csv')
arms = ['BB','MB','BM','MM','MM_NEW_RANGE_ONLY']
palette=dict(zip(arms,['#374151','#27689b','#b68c20','#c66c36','#9b5277']))
styles=dict(zip(arms,['-','--',':','-.','-']))
metrics = ['heading_rmse_deg','range_err_rmse_cm','bias_rmse_dps','xy_rmse_m']
rows=[]
for (case,bias), g in s.groupby(['case','bias'], sort=False):
    g=g.set_index('arm')
    for a in arms:
        row=dict(case=case,bias=bias,arm=a,route=g.loc[a,'route'])
        for m in metrics:
            row[m]=g.loc[a,m]
            row[m+'_ratio_BB']=g.loc[a,m]/g.loc['BB',m]
            row[m+'_delta_BB']=g.loc[a,m]-g.loc['BB',m]
        rows.append(row)
p=pd.DataFrame(rows)
p.to_csv(ROOT/'X1_PAIRED_COMPARISONS.csv', index=False)
summary=[]
for a,g in p.groupby('arm',sort=False):
    row=dict(arm=a,conditions=len(g))
    for m in metrics:
        row[m+'_median_ratio_BB']=float(g[m+'_ratio_BB'].median())
        row[m+'_median_delta_BB']=float(g[m+'_delta_BB'].median())
        row[m+'_improved_n']=int((g[m+'_delta_BB']<0).sum())
        row[m+'_worse_gt10pct_n']=int((g[m+'_ratio_BB']>1.1).sum())
    summary.append(row)
pd.DataFrame(summary).to_csv(ROOT/'X1_SUMMARY.csv',index=False)
p.groupby(['route','bias','arm'],sort=False)[[m+'_ratio_BB' for m in metrics]].median().to_csv(ROOT/'X1_ROUTE_SUMMARY.csv')
contr=[]
for (case,bias),g in s.groupby(['case','bias'],sort=False):
    g=g.set_index('arm'); row=dict(case=case,bias=bias)
    for m in metrics:
        for dst,src in [('MB','BB'),('BM','BB'),('MM','MB'),('MM','BM'),('MM_NEW_RANGE_ONLY','MM')]:
            row[f'{m}__{dst}_minus_{src}']=float(g.loc[dst,m]-g.loc[src,m])
        row[m+'__MSE_interaction']=float(g.loc['MM',m]**2-g.loc['MB',m]**2-g.loc['BM',m]**2+g.loc['BB',m]**2)
    contr.append(row)
pd.DataFrame(contr).to_csv(ROOT/'X1_CONTRASTS.csv',index=False)
figdir=ROOT/'figures';figdir.mkdir(exist_ok=True)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':170})
fig,axs=plt.subplots(1,2,figsize=(13,6),layout='constrained')
for ax,m,title in zip(axs,metrics[:2],['Heading RMSE / BB','Anchor-distance error RMSE / BB']):
    tab=p.assign(condition=p.case+' / '+p.bias).pivot(index='condition',columns='arm',values=m+'_ratio_BB')[arms[1:]]
    values=tab.to_numpy();im=ax.imshow(np.log2(values),cmap=LinearSegmentedColormap.from_list('effect',['#709ec0','#fafafa','#d99869']),vmin=-1.5,vmax=1.5,aspect='auto')
    ax.set_yticks(range(len(tab)),tab.index);ax.set_xticks(range(4),['MB','BM','MM','MM range-only\non new accepts']);ax.set_title(title)
    for i in range(len(tab)):
        for j in range(4):ax.text(j,i,f'{values[i,j]:.2f}',ha='center',va='center',fontsize=8,color='black')
fig.suptitle('Frozen-mask nonlinear replay | lower ratio is better | score t >= 30 s')
fig.colorbar(im,ax=axs,label='log2(ratio): blue improves, orange worsens',shrink=.7)
fig.savefig(figdir/'01_paired_ratios.png');plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
for ax,m,title in zip(axs,metrics[:2],['Heading RMSE (deg)','Anchor-distance error RMSE (cm)']):
    for (case,bias),g in p.groupby(['case','bias']):
        g=g.set_index('arm').loc[arms]
        ax.plot(range(5),g[m],alpha=.45,marker='o',ms=3,lw=1,color='#5c6b78')
    ax.set_xticks(range(5),['BB','MB','BM','MM','MM range-only']);ax.set_ylabel(title);ax.grid(alpha=.2)
fig.suptitle('Each line is one paired condition (14 total); no independent-scene inference')
fig.savefig(figdir/'02_absolute_metrics.png');plt.close(fig)
# Representative chosen explicitly: largest MM/BB heading RMSE ratio.
rep=p[p.arm=='MM'].sort_values('heading_rmse_deg_ratio_BB',ascending=False).iloc[0]
pack=pd.read_csv(ROOT/'X1_PACKETS.csv.gz');pack=pack[(pack.case==rep.case)&(pack.bias==rep.bias)]
fig,axs=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
for arm in arms:
    g=pack[pack.arm==arm]
    axs[0].plot(g.t_s,g.heading_error_deg,label=arm,lw=1,color=palette[arm],ls=styles[arm])
    axs[1].plot(g.t_s,g.bias_estimate_dps,label=arm,lw=1,color=palette[arm],ls=styles[arm])
g=pack[pack.arm=='MM'];new=g[g.new_accept]
axs[2].scatter(new.t_s,new.nu_s,s=8,color='#27689b',label='newly accepted: polarization innovation')
axs[0].set_ylabel('Heading error (deg)');axs[1].set_ylabel('Gyro bias estimate (deg/s)');axs[2].set_ylabel('MM polarization innovation');axs[2].set_xlabel('Time (s)')
for ax in axs:ax.axvline(30,color='grey',ls='--');ax.grid(alpha=.2)
axs[0].legend(ncol=3,fontsize=8);axs[2].legend(fontsize=8)
fig.suptitle(f'Diagnostic example: {rep.case} / {rep.bias}\nSelected by largest MM/BB heading RMSE ratio; not a representative population estimate')
fig.savefig(figdir/'03_diagnostic_timeline.png');plt.close(fig)
(ROOT/'ANALYSIS_SUMMARY.json').write_text(json.dumps(dict(arms=summary,representative=dict(case=rep.case,bias=rep.bias),note='Descriptive paired comparisons only; no new training or significance tests.'),indent=2),encoding='utf-8')
print(pd.DataFrame(summary).to_string(index=False))
