from pathlib import Path
import sys,json,hashlib,shutil
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image
out=Path(sys.argv[1]); d=pd.read_csv(out/'THREE_STAGE_SCORES.csv'); e=pd.read_csv(out/'TIME_DISTANCE_ERRORS.csv.gz')
assert len(d)==36 and not d.duplicated(['case','bias','stage']).any()
plt.rcParams.update({'font.family':'Times New Roman','font.size':9,'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'axes.linewidth':.6,'lines.linewidth':1.1,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.dpi':600})
stages=['LOS_EKF','MULTIPATH_EKF','PROPOSED_MB_VAR']; labels=['LoS: conventional EKF','Multipath: conventional EKF','Multipath: proposed model']; colors=['#6C8995','#C77C26','#286946']; hatches=['','///','xx']; markers=['o','s','^']; routes=['R2','R4','R5']; biases=['B0','L0','L1','L2']
checks=[]
def style(ax):
    ax.grid(axis='y',color='.88',linewidth=.4);ax.set_axisbelow(True)
    ax.spines[['top','right']].set_visible(False)
def save(fig,name):
    fig.savefig(out/(name+'.pdf'));fig.savefig(out/(name+'.svg'));fig.savefig(out/(name+'.png'),dpi=600)
    checks.append(dict(figure=name,size_inches=list(fig.get_size_inches()),pixels=Image.open(out/(name+'.png')).size,font=font_manager.findfont('Times New Roman'),pdf_fonttype=42))
    plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(7.16,2.9)); fig.subplots_adjust(left=.085,right=.99,bottom=.19,top=.81,wspace=.34)
for ax,metric,ylabel,panel in zip(axs,['head_rmse','xy_rmse_cm'],['Heading RMSE (deg)','Position RMSE (cm)'],['(a)','(b)']):
    for j,st in enumerate(stages):
        vals=[float(d[(d.route==r)&(d.bias=='B0')&(d.stage==st)][metric].iloc[0]) for r in routes]
        bars=ax.bar(np.arange(3)+(j-1)*.25,vals,.23,label=labels[j],color=colors[j],hatch=hatches[j],edgecolor='black',linewidth=.45)
        for b,v in zip(bars,vals):ax.annotate(f'{v:.2f}',(b.get_x()+b.get_width()/2,b.get_height()),ha='center',va='bottom',fontsize=7,xytext=(0,2),textcoords='offset points')
    ax.set_xticks(range(3),routes);ax.set_ylabel(ylabel);ax.set_xlabel('Route');ax.text(.01,.98,panel,transform=ax.transAxes,va='top');ax.margins(y=.18);style(ax)
fig.legend(*axs[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.985),ncol=3,frameon=False,columnspacing=1.1,handlelength=1.8)
save(fig,'F01_B0_THREE_STAGE_IEEE')
d[d.bias=='B0'].to_csv(out/'F01_DATA.csv',index=False)
fig,axs=plt.subplots(2,3,figsize=(7.16,4.5));fig.subplots_adjust(left=.085,right=.99,bottom=.12,top=.84,wspace=.36,hspace=.35)
for col,r in enumerate(routes):
    for row,(metric,ylabel) in enumerate([('head_rmse','Heading RMSE (deg)'),('xy_rmse_cm','Position RMSE (cm)')]):
        ax=axs[row,col]
        for j,st in enumerate(stages):
            vals=[d[(d.route==r)&(d.bias==b)&(d.stage==st)][metric].iloc[0] for b in biases]
            ax.plot(range(4),vals,color=colors[j],marker=markers[j],markersize=3.5,label=labels[j],linestyle=['-', '--', '-.'][j])
        ax.set_xticks(range(4),['0','.01','.05','.20']);ax.set_title(r if row==0 else '',fontsize=9);style(ax)
        if col==0:ax.set_ylabel(ylabel)
        if row==1:ax.set_xlabel('Gyro bias (deg/s)')
fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',ncol=3,frameon=False,bbox_to_anchor=(.5,1))
save(fig,'F02_ALL12_GYRO_SENSITIVITY_IEEE')
fig,axs=plt.subplots(2,3,figsize=(7.16,4.5));fig.subplots_adjust(left=.085,right=.99,bottom=.12,top=.84,wspace=.36,hspace=.35)
windows=[]
for col,r in enumerate(routes):
    for j,st in enumerate(stages):
        a=e[(e.case.str.startswith(r))&(e.bias=='B0')&(e.stage==st)&e.scored].copy();a['window']=np.floor(a.t_s/10)*10
        g=a.groupby('window').agg(t_s=('t_s','mean'),heading_rmse_deg=('heading_error_deg',lambda x:np.sqrt(np.mean(x*x))),xy_rmse_cm=('xy_error_cm',lambda x:np.sqrt(np.mean(x*x))),n=('t_s','size')).reset_index();g['route']=r;g['stage']=st;windows.append(g)
        for row,metric in enumerate(['heading_rmse_deg','xy_rmse_cm']):axs[row,col].plot(g.t_s,g[metric],color=colors[j],linestyle=['-','--','-.'][j],label=labels[j])
    for row in range(2):
        ax=axs[row,col];style(ax)
        if row==0:ax.set_title(r,fontsize=9)
        else:ax.set_xlabel('Time (s)')
        if col==0:ax.set_ylabel(['Heading RMSE (deg)','Position RMSE (cm)'][row])
fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',ncol=3,frameon=False,bbox_to_anchor=(.5,1));save(fig,'F03_B0_TIME_10S_RMSE_IEEE');pd.concat(windows).to_csv(out/'F03_10S_WINDOW_DATA.csv',index=False)
fig,axs=plt.subplots(2,3,figsize=(7.16,4.5));fig.subplots_adjust(left=.085,right=.99,bottom=.12,top=.84,wspace=.36,hspace=.35)
bins=[0,1.5,3,6,10,np.inf];blabel=['<1.5','1.5–3','3–6','6–10','>=10'];br=[]
for col,r in enumerate(routes):
    for j,st in enumerate(stages):
        a=e[(e.case.str.startswith(r))&(e.bias=='B0')&(e.stage==st)&e.scored].copy();a['bin']=pd.cut(a.rho_true_m,bins,right=False,labels=False)
        vals=[[],[]]
        for k in range(5):
            v=a[a.bin==k];n=len(v);h=np.sqrt(np.mean(v.heading_error_deg**2)) if n else np.nan;x=np.sqrt(np.mean(v.xy_error_cm**2)) if n else np.nan;vals[0].append(h);vals[1].append(x);br.append(dict(route=r,stage=st,bin=blabel[k],n=n,heading_rmse_deg=h,xy_rmse_cm=x))
        for row in range(2):axs[row,col].plot(range(5),vals[row],color=colors[j],marker=markers[j],markersize=3,linestyle=['-','--','-.'][j],label=labels[j])
    for row in range(2):
        ax=axs[row,col];style(ax);ax.set_xticks(range(5),blabel,rotation=25,ha='right',fontsize=7)
        if row==0:ax.set_title(r,fontsize=9)
        else:ax.set_xlabel('Horizontal distance (m)',fontsize=8)
        if col==0:ax.set_ylabel(['Heading RMSE (deg)','Position RMSE (cm)'][row])
fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',ncol=3,frameon=False,bbox_to_anchor=(.5,1));save(fig,'F04_B0_DISTANCE_RMSE_IEEE');pd.DataFrame(br).to_csv(out/'F04_DISTANCE_BIN_DATA.csv',index=False)
(out/'FIGURE_FORMAT_QA.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
for name in ['replay_conventional.py','plot_conventional.py']:shutil.copy2(Path(__file__).parent/name,out/name)
(out/'OUTPUT_HASHES.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='OUTPUT_HASHES.json'},indent=2),encoding='utf-8')
print(d[d.bias=='B0'][['route','stage','head_rmse','xy_rmse_cm','n_used']].to_string(index=False));print('FIGURES_COMPLETE')
