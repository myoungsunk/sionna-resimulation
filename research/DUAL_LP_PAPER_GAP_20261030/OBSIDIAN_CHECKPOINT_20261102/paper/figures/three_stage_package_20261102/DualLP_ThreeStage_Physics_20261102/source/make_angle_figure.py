import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from pathlib import Path
ROOT=Path('/mnt/data/dual_lp_dramatic_figures_20261102');T=ROOT/'tables';F=ROOT/'figures'
font='/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
font_manager.fontManager.addfont(font);plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name();plt.rcParams['axes.unicode_minus']=False
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
D=pd.read_csv(T/'PHYSICAL_LOS_FULL_PACKET_3136.csv');D=D[D.t_s>=30].copy()
D['relative_yaw_deg']=((np.degrees(D.relative_yaw_rad)+180)%360)-180
D['abs_s_error']=abs(D.Full_minus_LoS_s)
records=[]
for case,g in D.groupby('case'):
 for lo in range(-180,180,30):
  a=g[(g.relative_yaw_deg>=lo)&(g.relative_yaw_deg<lo+30)]
  if len(a)==0:continue
  records.append(dict(case=case,relative_yaw_lo_deg=lo,relative_yaw_hi_deg=lo+30,n=len(a),
    mean_LoS_s=float(a.LoS_s.mean()),mean_Full_s=float(a.Full_s.mean()),
    RMS_Full_minus_LoS_s=float(np.sqrt(np.mean(a.Full_minus_LoS_s**2))),
    median_abs_J_spsi_per_rad=float(a.J_heading_abs_per_rad.median()),
    tap_switch_pct=float(100*a.tap_switched_Full_vs_LoS.mean()),
    mean_rho_m=float(a.rho_true_m.mean())))
pd.DataFrame(records).to_csv(T/'YAW_BIN_PHYSICAL_SIGNATURES.csv',index=False)
cases=['R2_aB_m0','R4_aB_m0','R5_aB_m0'];names=['R2-B','R4-B','R5-B'];colors={'los':'#206aa9','full':'#cc6540'}
fig,axes=plt.subplots(3,2,figsize=(13,9),gridspec_kw={'hspace':.34,'wspace':.25})
for i,(c,name) in enumerate(zip(cases,names)):
 a=D[D.case==c].sort_values('relative_yaw_deg');ax=axes[i,0];
 ax.scatter(a.relative_yaw_deg,a.LoS_s,s=9,alpha=.35,c=colors['los'],label='Direct LoS')
 ax.scatter(a.relative_yaw_deg,a.Full_s,s=9,alpha=.25,c=colors['full'],label='Full multipath')
 ax.axhline(0,color='#9ca3af',lw=.8);ax.set_ylim(-1.08,1.08);ax.set_xlim(-180,180)
 ax.set_ylabel(f'{name} signed s');ax.set_xlabel('상대 방위 / yaw (°)');ax.set_title('물리 편파 응답의 각도 의존성')
 ax.grid(axis='y',alpha=.2)
 ax=axes[i,1];
 sc=ax.scatter(a.relative_yaw_deg,a.J_heading_abs_per_rad,s=12,c=a.abs_s_error,cmap='plasma',vmin=0,vmax=1.3,alpha=.8,edgecolors='none')
 ax.set_xlim(-180,180);ax.set_ylabel('|H_sψ| (rad⁻¹)');ax.set_xlabel('상대 방위 / yaw (°)');ax.set_title('물리 민감도와 같은 pose의 편파 왜곡');ax.grid(axis='y',alpha=.2)
axes[0,0].legend(loc='upper left',frameon=False,fontsize=9,ncol=2)
fig.colorbar(sc,ax=axes[:,1].ravel().tolist(),shrink=.8,pad=.012,label='|Full - LoS signed s|')
fig.suptitle('실제 Dual-LP 패턴: 방향 민감도가 높아도 Full RF 왜곡은 함께 나타납니다',fontsize=15,fontweight='bold')
fig.text(.018,.009,'t≥30 s 전체 finite packet · true-pose SourceFFD 편파 Jacobian · 한 장면의 경로별 조건부 분포 · 색깔은 같은 pose의 Full vs LoS 차이',fontsize=9,color='#475569')
fig.subplots_adjust(left=.085,right=.91,bottom=.065,top=.9)
fig.savefig(F/'F13_YAW_DEPENDENT_DUAL_LP_PHYSICS.png',dpi=190,bbox_inches='tight')
fig.savefig(F/'F13_YAW_DEPENDENT_DUAL_LP_PHYSICS.svg',bbox_inches='tight')
plt.close(fig)
print('bins',len(records),'n_r2',len(D[D.case==cases[0]]))
