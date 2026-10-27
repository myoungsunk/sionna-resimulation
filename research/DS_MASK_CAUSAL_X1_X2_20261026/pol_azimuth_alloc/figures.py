from pathlib import Path
import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent;FIG=ROOT/'figures';FIG.mkdir(exist_ok=True)
CASES=['R2_aA_m45','R4_aA_m0','R4_aB_m0'];BIAS=['B0','L2'];COL=['#2468A0','#A54B00','#754A9D'];STYLE={'BB':'-','MB':'--'}
plt.rcParams.update({'font.size':10,'axes.titlesize':11,'axes.labelsize':10,'legend.fontsize':8,'figure.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})
def finish(fig,name,title,handles,labels):
 fig.suptitle(title,fontsize=15,y=.995);fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.965),ncol=min(6,len(labels)),frameon=False);fig.tight_layout(rect=(0.01,0.01,.99,.89),h_pad=3,w_pad=2);fig.savefig(FIG/name,dpi=160);plt.close(fig)
def decorate(ax):
 ax.set_xscale('log');ax.set_xlabel('GT horizontal distance (m)');ax.grid(alpha=.18);ax.axvspan(.1,.5,color='#e8e8e8',alpha=.5);ax.set_xlim(.2,12);ax.set_xticks([.25,.5,1,2,4,8]);ax.set_xticklabels(['.25','.5','1','2','4','8'])
def subset(df,case,bias,arm):return df[(df.case==case)&(df.bias==bias)&(df.arm==arm)].sort_values('d_gt_med')
def f1():
 df=pd.read_csv(ROOT/'C1_HS_BY_BIN.csv')
 # Separate bias figures avoid averaging opposite behavior; each case has derivative and ratio panels.
 for bias in BIAS:
  fig,axs=plt.subplots(2,3,figsize=(14,8));handles=[];labels=[]
  for c,case in enumerate(CASES):
   for arm in ['BB','MB']:
    g=subset(df,case,bias,arm);x=g.d_gt_med.to_numpy()
    for metric,label,color in [('ds_dbeta','|ds/dbeta|',COL[0]),('ds_dpsi','|ds/dpsi|',COL[1])]:
     line,=axs[0,c].plot(x,g[metric+'_med'],STYLE[arm],color=color,marker='o',ms=3,label=arm+' '+label)
     axs[0,c].fill_between(x,g[metric+'_p10'].to_numpy(),g[metric+'_p90'].to_numpy(),color=color,alpha=.09 if arm=='BB' else .04)
     if c==0:handles.append(line);labels.append(arm+' '+label)
    axs[1,c].plot(x,g.kappa_med,STYLE[arm],color=COL[0] if arm=='BB' else COL[1],marker='o',ms=3,label=arm)
    axs[1,c].fill_between(x,g.kappa_p10.to_numpy(),g.kappa_p90.to_numpy(),color=COL[0] if arm=='BB' else COL[1],alpha=.1)
   axs[0,c].set_title(case+' / '+bias);axs[0,c].set_ylabel('Sensitivity (polarization ratio / deg)');axs[0,c].set_yscale('log');axs[1,c].set_ylabel('kappa (dimensionless)');axs[1,c].set_yscale('log');axs[1,c].legend(frameon=False)
   for val in [.5,1,2]:axs[1,c].axhline(val,color='#555555',lw=.8,ls=':' if val!=1 else '-')
   for ax in axs[:,c]:decorate(ax)
  finish(fig,'F1_kappa_by_d.png' if bias=='B0' else 'F1_kappa_by_d_L2.png',f'H_s sensitivity and kappa | {bias} | bands: packet p10-p90, n >= 30',handles,labels)
def panels(name,title,kind):
 files={'pred':'C1B_BY_BIN.csv','alloc':'C2_ALLOC_BY_BIN.csv','calib':'C3_CALIB_BY_BIN.csv'};df=pd.read_csv(ROOT/files[kind]);fig,axs=plt.subplots(2,3,figsize=(14,9));handles=[];labels=[]
 for i,bias in enumerate(BIAS):
  for c,case in enumerate(CASES):
   ax=axs[i,c];ax.set_title(case+' / '+bias)
   for arm in ['BB','MB']:
    g=subset(df,case,bias,arm);x=g.d_gt_med
    metrics={'pred':[('rms_ds_pos','Position prediction',COL[0]),('rms_ds_psi','Heading prediction',COL[1])],'alloc':[('share_psi_med','psi',COL[0]),('share_tan_med','tangent',COL[1]),('share_rad_med','radial',COL[2])],'calib':[('rms_z_t','z_t',COL[0]),('rms_z_r','z_r',COL[1]),('rms_z_psi','z_psi',COL[2])]}[kind]
    for metric,label,color in metrics:
     line,=ax.plot(x,g[metric],STYLE[arm],color=color,marker='o',ms=3)
     if i==c==0:handles.append(line);labels.append(arm+' '+label)
    if kind=='pred' and arm=='BB':
     for metric,label,ls in [('rms_r_base','Measurement residual',':'),('sqrt_V_rms','sqrt(mean V)','-.')]:
      line,=ax.plot(x,g[metric],ls,color='#333333',marker='s',ms=3)
      if i==c==0:handles.append(line);labels.append(label)
   decorate(ax)
   if kind=='pred':ax.set_yscale('log');ax.set_ylabel('Polarization ratio (RMS)')
   if kind=='alloc':ax.axhline(0,color='#555555',lw=.8);ax.axhline(.5,color='#777777',lw=.7,ls=':');ax.set_ylabel('Median signed allocation share')
   if kind=='calib':ax.axhline(1,color='#555555',lw=.8);ax.set_ylabel('RMS(normalized error)')
 finish(fig,name,title+' | n >= 30; shaded distance < 0.5 m',handles,labels)
def f5():
 c3=pd.read_csv(ROOT/'C3_PACKETS.csv.gz');c2=pd.read_csv(ROOT/'C2_PACKETS.csv.gz');c3=c3[(c3.case=='R4_aB_m0')&(c3.bias=='B0')];c2=c2[(c2.case=='R4_aB_m0')&(c2.bias=='B0')];b=c3[(c3.arm=='BB')&c3.scoring];center=float(b.loc[b.d_gt_m.idxmin(),'t_s']);lo=center-10;hi=center+10
 fig,axs=plt.subplots(5,1,figsize=(13,12),sharex=True);lines=[];labels=[]
 for arm,color in [('BB',COL[0]),('MB',COL[1])]:
  g=c3[(c3.arm==arm)&c3.t_s.between(lo,hi)];q=c2[(c2.arm==arm)&c2.t_s.between(lo,hi)];t=g.t_s
  if arm=='BB':axs[0].plot(t,g.d_gt_m,color='#444444');axs[0].axhline(1.5,color='#777777',ls=':')
  a,=axs[1].plot(t,g.e_t_cm,color=color);bb,=axs[1].plot(t,g.sigma_t_cm,'--',color=color);axs[1].plot(t,-g.sigma_t_cm,'--',color=color,alpha=.6)
  lines.extend([a,bb]);labels.extend([arm+' error',arm+' +/- sigma'])
  axs[2].plot(t,g.psi_err_deg,color=color);axs[2].plot(t,g.sigma_psi_deg,'--',color=color);axs[2].plot(t,-g.sigma_psi_deg,'--',color=color,alpha=.6)
  axs[3].plot(q.t_s,np.where(q.accepted,q.share_psi,np.nan),color=color)
  l1,=axs[4].plot(q.t_s,np.where(q.accepted,q.dpsi_pol_deg,np.nan),color=color,label=arm+' dpsi');l2,=axs[4].plot(q.t_s,np.where(q.accepted,q.dbeta_pol_deg,np.nan),':',color=color,label=arm+' dbeta')
 for ax,lab in zip(axs,['GT distance (m)','Tangential error / sigma (cm)','Heading error / sigma (deg)','share_psi (accepted only)','Pol increment (deg)']):ax.set_ylabel(lab);ax.grid(alpha=.2);ax.axvline(center,color='#888888',ls=':',lw=.7)
 for ax in axs[1:]:ax.axhline(0,color='#555555',lw=.7)
 axs[-1].legend(ncol=4,frameon=False);axs[-1].set_xlabel('Time (s)');axs[-1].set_xlim(lo,hi)
 finish(fig,'F5_example_pass.png',f'R4_aB_m0 / B0: closest GT pass at {center:.2f} s (+/-10 s)',lines,labels)
 pd.DataFrame([dict(case='R4_aB_m0',bias='B0',center_t_s=center,lo=lo,hi=hi,selection='minimum GT horizontal distance at t>=30')]).to_csv(ROOT/'F5_SELECTION.csv',index=False)
if __name__=='__main__':
 f1();panels('F2_pred_vs_meas.png','Prediction error vs measurement residual','pred');panels('F3_allocation.png','Joint polarization-column allocation (signed)','alloc');panels('F4_calibration.png','Posterior calibration by distance','calib');f5();print('Rendered six figures')
