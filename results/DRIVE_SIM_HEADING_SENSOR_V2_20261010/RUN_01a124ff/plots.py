from pathlib import Path
import json,sys
import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
J=Path('/job');OUT=J/'ANALYSIS';cv=pd.read_csv(J/'RELIABILITY/METRICS.csv');fig,axes=plt.subplots(1,3,figsize=(12,4))
for ax,r in zip(axes,['R2','R4','R5']):
 for m in ['distance','D','DP','DPK']:
  row=cv[(cv.route==r)&(cv.model==m)].iloc[0];ax.plot([.25,.5,.75,1],[row[f'risk_at_{q}'] for q in [.25,.5,.75,1.]],'o-',label=m)
 ax.set_title(r+' (available subset)');ax.set_xlabel('Retained fraction');ax.set_ylabel('Bad heading >5 degree fraction');ax.legend(fontsize=8)
fig.tight_layout();fig.savefig(OUT/'RISK_COVERAGE.png',dpi=160);plt.close(fig)
ci=pd.read_csv(OUT/'DISTANCE_STATION_CI.csv');g=ci[ci.error=='e_s'].reset_index(drop=True);fig,axes=plt.subplots(2,1,figsize=(12,7));xx=np.arange(len(g));axes[0].errorbar(xx,g['mean'],yerr=np.vstack([g['mean']-g.mean_ci_low,g.mean_ci_high-g['mean']]),fmt='o');axes[0].set_ylabel('Full RF minus LUT s mean');axes[1].errorbar(xx,g.rms,yerr=np.vstack([g.rms-g.rms_ci_low,g.rms_ci_high-g.rms]),fmt='o');axes[1].set_ylabel('Residual RMS');axes[1].set_xticks(xx,[str(c)+' '+str(b) for c,b in zip(g.case,g.distance_bin)],rotation=75,ha='right');fig.tight_layout();fig.savefig(OUT/'DISTANCE_RESIDUAL_CI.png',dpi=160);plt.close(fig)
data=pd.concat([pd.read_csv(p,usecols=['route','station_group','P1_jsd','heading_error_deg','available']) for p in sorted((J/'LABELS').glob('*.csv.gz'))],ignore_index=True);st=data[data.available].groupby(['route','station_group'])[['P1_jsd','heading_error_deg']].mean().reset_index();fig,axes=plt.subplots(1,3,figsize=(12,4))
for ax,r in zip(axes,['R2','R4','R5']):
 d=st[st.route==r];ax.hexbin(d.P1_jsd,d.heading_error_deg,gridsize=25,mincnt=1);ax.set_title(r+' station means');ax.set_xlabel('Normalized port-shape JSD');ax.set_ylabel('Absolute RF-heading error (degree)')
fig.tight_layout();fig.savefig(OUT/'FEATURE_HEADING_ASSOCIATION.png',dpi=160);plt.close(fig)
import platform,sklearn,scipy
(J/'ENVIRONMENT.json').write_text(json.dumps({'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__,'matplotlib':matplotlib.__version__},indent=2));print('plots and environment completed',flush=True)
