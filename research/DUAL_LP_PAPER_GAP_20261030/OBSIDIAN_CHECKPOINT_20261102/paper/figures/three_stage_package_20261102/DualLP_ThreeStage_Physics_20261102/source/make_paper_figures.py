"""Generate provenance-qualified, reproducible multi-panel paper figures from frozen source.
No RT, no new Full EKF: only direct LoS counterfactual already recorded.
"""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile
import io, gzip, json, hashlib, math
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator, MultipleLocator

ROOT=Path('/mnt/data/dual_lp_dramatic_figures_20261102');FIG=ROOT/'figures';TAB=ROOT/'tables';SOURCE=ROOT/'source'
for p in (FIG,TAB,SOURCE):p.mkdir(exist_ok=True,parents=True)
ARCH=Path('/mnt/data/DualLP_Physics_Link_Validation_20261101.zip')
ZIP=ZipFile(ARCH);P='DualLP_Physics_Link_Validation_20261101/'
font='/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
if not Path(font).exists():
  alt=next(Path('/usr/share/fonts').rglob('NanumGothic.ttf'),None)
  font=str(alt) if alt else None
if font:
  font_manager.fontManager.addfont(font);plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
plt.rcParams['axes.unicode_minus']=False
plt.rcParams.update({'font.size':10,'axes.titlesize':12,'axes.labelsize':10,'axes.spines.top':False,'axes.spines.right':False,
 'axes.grid':False,'figure.facecolor':'white','savefig.facecolor':'white','xtick.labelsize':9,'ytick.labelsize':9})
COL={'LOS':'#206aa9','FULL':'#cc6540','MB':'#07857b','OTHER':'#596477','HIGHLIGHT':'#9164b0'}
CASES=['R2_aB_m0','R4_aB_m0','R5_aB_m0'];ROUTES=['R2-B','R4-B','R5-B'];RNAME=dict(zip(CASES,ROUTES))
BIAS=['B0','L0','L1','L2'];SCORESTART=30-1e-9

def read_csv(name):
 b=ZIP.read(P+name);return pd.read_csv(io.BytesIO(gzip.decompress(b) if name.endswith('.gz') else b))
physics=read_csv('results/PHYSICS_PACKET_LEDGER.csv.gz')
score=read_csv('results/tables/RECURSIVE_144_LOGICAL_SCORES.csv')
matched=read_csv('results/MATCHED_PRIOR_2X2.csv.gz')
los=pd.read_csv(TAB/'LOS_COUNTERFACTUAL_24.csv')
assert len(physics)==979+742+1415 and len(matched)==4*len(physics)*4
assert len(los)==24 and set(los['arm'])=={'LOS_ZERO_MEAN','LOS_FROZEN_FULL_BB_MEAN'}
assert set(physics['case'])==set(CASES) and len(score)==144

# Export packet-level physical link with explicit definitions.
phy=physics.copy()
phy['Full_minus_LoS_s']=phy['Full_s']-phy['LoS_s']
phy['Full_minus_LoS_r_m']=phy['Full_r_m']-phy['LoS_r_m']
phy['tap_switched_Full_vs_LoS']=(phy['Full_tap']!=phy['LoS_tap']).astype(int)
phy['strong_port_switched']=(phy['Full_port']!=phy['LoS_port']).astype(int)
phy['J_heading_abs_per_rad']=phy['J_spsi_per_rad'].abs()
phy[['case','pose_id','t_s','rho_true_m','relative_yaw_rad','Full_s','LoS_s','SourceFFD_s','Full_minus_LoS_s','Full_r_m',
'LoS_r_m','Full_minus_LoS_r_m','Full_Pplus','Full_Pminus','LoS_Pplus','LoS_Pminus',
'J_sx','J_sy','J_spsi_per_rad','J_heading_abs_per_rad','Full_tap','LoS_tap','Full_port','LoS_port',
'Full_fp_margin','LoS_fp_margin','tap_switched_Full_vs_LoS','strong_port_switched','eps_s_MB','eps_r_MB']].to_csv(TAB/'PHYSICAL_LOS_FULL_PACKET_3136.csv',index=False)

# Stage score controls: new clean LoS and unchanged original Full BB/MB self-gate.
stages=[]
for case in CASES:
 for b in BIAS:
  for label,arm,where in [('Direct LoS — zero mean','LOS_ZERO_MEAN','new'),('Direct LoS — frozen Full BB mean','LOS_FROZEN_FULL_BB_MEAN','new'),
                        ('Full multipath — BB_ORIG','BB_ORIG','archived'),('Full multipath — MB_VAR','MB_VAR','archived')]:
   sub=los if where=='new' else score
   d=sub[(sub.case==case)&(sub.bias==b)&(sub.arm==arm)]
   if where=='archived':d=d[d.gate=='self']
   assert len(d)==1,(case,b,arm,len(d))
   r=d.iloc[0]
   stages.append(dict(case=case,route=RNAME[case],bias=b,stage=label,source_type=('NEW_EXPLORATORY_LOS' if where=='new' else 'ARCHIVED_FULL'),
     head_rmse_deg=float(r.head_rmse),xy_rmse_cm=float(r.xy_rmse_cm),head_cov95=float(r.head_cov95),xy_cov95=float(r.xy_cov95),
     nees_xy=float(r.nees_xy),n_used=int(r.n_used),n_score=int((physics[physics.case==case].t_s>=SCORESTART).sum())))
stages=pd.DataFrame(stages);stages.to_csv(TAB/'THREE_STAGE_COMPARISON_12_BIASES.csv',index=False)

# Finite time truth and original filter traces (preserved original, no recreation).
for case in CASES:
  for b in BIAS:
    # Read BB, MB original from ZIP. clean LoS from separately generated new trace.
    raw={}
    for a in ('BB_ORIG','MB_VAR'):
      f=P+f'results/traces/{case}__{b}__{a}__self.npz'
      with np.load(io.BytesIO(ZIP.read(f)),allow_pickle=False) as fz:
        raw[a]={k:fz[k].copy() for k in ['X','PX','J','xp','Pp','nu','S','Ru','nis','used']}
    lp=TAB/f'{case}_{b}_LOS_ZERO_MEAN.npz'
    with np.load(lp,allow_pickle=False) as fz:
      T=fz['t'].copy();GT=fz['gt'].copy();LOS_X=fz['X'].copy();LOS_P=fz['PX'].copy();LOS_USED=fz['used'].copy()
    N=len(T);assert len(phy[phy.case==case])==N
    p=phy[phy.case==case].sort_values('pose_id').reset_index(drop=True)
    out={'case':np.repeat(case,N),'bias':np.repeat(b,N),'pose_id':np.arange(N),'time_s':T,
         'rho_true_m':p.rho_true_m.to_numpy(),'s_Full_minus_LoS':p.Full_minus_LoS_s.to_numpy(),
         'J_spsi_truth_per_rad':p.J_spsi_per_rad.to_numpy(),'full_vs_los_tap_switch':p.tap_switched_Full_vs_LoS.to_numpy()}
    for name,X,PC,used in [('LOS',LOS_X,LOS_P,LOS_USED),('BB',raw['BB_ORIG']['X'],raw['BB_ORIG']['PX'],raw['BB_ORIG']['used']),('MB',raw['MB_VAR']['X'],raw['MB_VAR']['PX'],raw['MB_VAR']['used'])]:
      e=GT[:,:3]-X[:,:3];eh=np.degrees(np.arctan2(np.sin(e[:,2]),np.cos(e[:,2])))
      out[f'heading_error_{name}_deg']=eh
      out[f'heading_abs_error_{name}_deg']=abs(eh)
      out[f'xy_error_{name}_cm']=100*np.linalg.norm(e[:,:2],axis=1)
      out[f'heading_predicted_std_{name}_deg']=np.degrees(np.sqrt(PC[:,2,2]))
      out[f'used_{name}']=used.astype(int)
      if name!='LOS':
        obs=raw['BB_ORIG' if name=='BB' else 'MB_VAR']
        j=obs['J'];Pp=obs['Pp'];S=obs['S']
        kp=np.linalg.solve(S,np.einsum('nij,njk->nik',j,Pp)).transpose(0,2,1)
        out[f'abs_K_heading_s_{name}']=abs(kp[:,2,1])
        out[f'abs_K_heading_r_{name}']=abs(kp[:,2,0])
        out[f'nis_{name}']=obs['nis']
        out[f'Rss_{name}']=obs['Ru'][:,1,1]
    pd.DataFrame(out).to_csv(TAB/f'TIME_RESOLVED_{case}_{b}.csv',index=False)

# B0 raw RF error analysis with same original BASE acceptance selection. 
res=[]
for case in CASES:
  d=phy[phy.case==case].sort_values('pose_id').reset_index(drop=True)
  f=P+f'recovered/inputs/traces/{case}_B0_CONTROL.npz'
  with np.load(io.BytesIO(ZIP.read(f)),allow_pickle=False) as fz:
    muB=fz['mu'][:,0,0];muM=fz['mu'][:,1,0];sel=fz['acc'][:,0].astype(bool)
  assert len(d)==len(muB)
  residB=d.Full_r_m.to_numpy()-d.h_r.to_numpy()-muB
  residM=d.Full_r_m.to_numpy()-d.h_r.to_numpy()-muM
  # Observe LoS range relative to same continuous bridge, without RF-trained correction.
  residLOS=d.LoS_r_m.to_numpy()-d.h_r.to_numpy()
  mask=sel&(d.t_s.to_numpy()>=SCORESTART)
  for name,arr in [('Direct LoS — no RF mean',residLOS),('Full — original mean',residB),('Full — EXDS mean',residM)]:
    res.append(dict(case=case,route=RNAME[case],stage=name,n=int(mask.sum()),r_error_RMS_cm=float(100*np.sqrt(np.mean(arr[mask]**2))),
                    r_error_mean_cm=float(100*np.mean(arr[mask])),r_error_std_cm=float(100*np.std(arr[mask]))))
  # save signed errors on same original selected time grid for reproducibility
  pd.DataFrame(dict(case=np.repeat(case,len(d)),pose_id=d.pose_id,time_s=d.t_s,rho_true_m=d.rho_true_m,
    fixed_BB_accepted=sel,range_error_original_mean_m=residB,range_error_EXDS_mean_m=residM,range_error_LoS_no_mean_m=residLOS,
    pol_error_fixed_MB=d.eps_s_MB)).to_csv(TAB/f'RANGE_RESIDUALS_{case}_B0.csv',index=False)
res=pd.DataFrame(res);res.to_csv(TAB/'RANGE_ERROR_SAME_FIXED_MASK_B0.csv',index=False)

# Distance buckets and J/response evidence. Entire finite trajectory, plus evaluation-only version.
BINEDGES=np.array([0,1.5,3,6,10.]);
records=[]
for case in CASES:
 c=phy[phy.case==case]
 for window in ('all','t>=30'):
  d=c if window=='all' else c[c.t_s>=SCORESTART]
  for l,r in zip(BINEDGES[:-1],BINEDGES[1:]):
   sub=d[(d.rho_true_m>=l)&(d.rho_true_m<r)]
   if not len(sub):continue
   records.append(dict(case=case,route=RNAME[case],window=window,rho_lo_m=l,rho_hi_m=r,rho_mid_m=(l+r)/2,
    n=len(sub),Full_LoS_s_RMS=float(np.sqrt(np.mean(sub.Full_minus_LoS_s**2))),
    Full_LoS_s_signed_mean=float(np.mean(sub.Full_minus_LoS_s)),
    Full_LoS_range_RMS_cm=float(100*np.sqrt(np.mean(sub.Full_minus_LoS_r_m**2))),
    Full_vs_LoS_tap_switch_fraction=float(sub.tap_switched_Full_vs_LoS.mean()),
    Full_vs_LoS_port_switch_fraction=float(sub.strong_port_switched.mean()),
    median_abs_J_heading_per_rad=float(sub.J_heading_abs_per_rad.median()),
    median_LoS_Ptotal=float(sub.LoS_Ptotal.median()),median_Full_Ptotal=float(sub.Full_Ptotal.median()),
    median_abs_ratio_error=float(sub.Full_minus_LoS_s.abs().median())))
bins=pd.DataFrame(records);bins.to_csv(TAB/'DISTANCE_BINS_PHYSICAL.csv',index=False)

# time-lag ACF and path-distance equivalent from same time lag (NOT independent spatial covariance).
acf=[]
for case in CASES:
  d=phy[phy.case==case].sort_values('pose_id').reset_index(drop=True)
  eps=d.eps_s_MB.to_numpy(); e=eps-eps.mean()
  norm=float(np.dot(e,e));xy=d[['x_truth_offline_m','y_truth_offline_m']].to_numpy()
  cumulative=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
  for lag in range(1,min(81,len(e)//2)):
    acf.append(dict(case=case,route=RNAME[case],lag_packets=lag,lag_time_s=float(.2*lag),
       acf_unbiased_denominator_no=float(np.dot(e[:-lag],e[lag:])/norm),
       median_path_travel_m=float(np.median(cumulative[lag:]-cumulative[:-lag])),n_pairs=len(e)-lag))
acf=pd.DataFrame(acf);acf.to_csv(TAB/'POLARIZATION_ACF_TIME_AND_TRAVEL.csv',index=False)

# raw physical summary (entire timeline, not gate selected)
physummary=[]
for case in CASES:
 d=phy[phy.case==case];s=d[d.t_s>=SCORESTART]
 for scope,x in [('all',d),('t>=30',s)]:
  physummary.append(dict(case=case,route=RNAME[case],scope=scope,n=len(x),
   Full_LoS_s_RMS=float(np.sqrt(np.mean(x.Full_minus_LoS_s**2))),
   Full_LoS_r_RMS_cm=float(100*np.sqrt(np.mean(x.Full_minus_LoS_r_m**2))),
   median_abs_J_heading=float(x.J_heading_abs_per_rad.median()),
   tap_switch_pct=float(x.tap_switched_Full_vs_LoS.mean()*100),
   port_switch_pct=float(x.strong_port_switched.mean()*100),
   signed_s_error_mean=float(x.Full_minus_LoS_s.mean())))
physummary=pd.DataFrame(physummary);physummary.to_csv(TAB/'PHYSICAL_SIGNATURES_3_ROUTES.csv',index=False)

# local mean-only vs combined for BB prior; compare end-to-end from separate replays.
# local columns case_ bias_ via flatten if tuple; fix names robustly
local=read_csv('results/tables/SAME_PRIOR_VARIANCE_CONTRASTS_12.csv')
selfscore=score.query("gate=='self' and arm in ['MB_ORIG','MB_VAR']").pivot(index=['case','bias'],columns='arm',values=['head_rmse','xy_rmse_cm'])
selfscore.columns=['_'.join(c) for c in selfscore.columns]; local=local.merge(selfscore.reset_index(),on=['case','bias'])
local['local_pct_MBVAR_vs_MBORIG']=100*(1-local.combined_head_mse_deg2/local.mean_only_head_mse_deg2)
local['final_pct_MBVAR_vs_MBORIG']=100*(1-local.head_rmse_MB_VAR/local.head_rmse_MB_ORIG)
local.to_csv(TAB/'LOCAL_VS_RECURSIVE_HEADING_12.csv',index=False)

# same-prior signed gain medians at t>=30 & original BASE acceptance, paired BB-prior.
mg=[]
for case in CASES:
 for bias in BIAS:
  a=matched[(matched.case==case)&(matched.bias==bias)&matched.fixed_accepted&matched.primary_score_mask]
  for arm in ('BB_ORIG','MB_ORIG','BB_VAR','MB_VAR'):
   v=a[a.arm==arm]
   mg.append(dict(case=case,route=RNAME[case],bias=bias,arm=arm,n=len(v),
     median_abs_Kpsi_s=float(v.K_psi_s.abs().median()),mean_abs_Kpsi_s=float(v.K_psi_s.abs().mean()),
     median_abs_dpsi_pol_rad=float(v.dx_psi_pol.abs().median()),
     mean_signed_dpsi_pol_rad=float(v.dx_psi_pol.mean()),
     mean_eps_s=float(v.epsilon_s.mean()),mean_nis=float(v.NIS.mean()),
     mean_head_loss_deg2=float(v.head_loss_deg2.mean())))
pd.DataFrame(mg).to_csv(TAB/'MATCHED_PRIOR_POLARIZATION_GAIN_12.csv',index=False)

# Map source evidence into precomputed publications; never treat LoS simulations as archived.
qa=dict(archive_sha256=hashlib.sha256(ARCH.read_bytes()).hexdigest(),source_archive=ARCH.name,
  source_physical_n=len(physics),source_shadows_n=len(matched),source_scores_n=len(score),
  source_new_los_runs_n=len(los),n_LoS_source_cases=3,
  new_los_exploratory=True,originalFullUnchanged=True,
  original_full_score_validation_max_abs=float(np.max(abs(stages[stages.source_type=='ARCHIVED_FULL'].query("stage == 'Full multipath — MB_VAR'").head(1).head_rmse_deg.to_numpy()-score.query("case=='R2_aB_m0' and bias=='B0' and arm=='MB_VAR' and gate=='self'").head_rmse.to_numpy()))),
  only_single_original_scene=True,ratio_and_jacobian_are_physical_not_post_correction=True,
  LoS_mean_zero_vs_Full_mean_is_not_single_variable_multipath_intervention=True)
(TAB/'PLOT_SOURCE_QA.json').write_text(json.dumps(qa,indent=2))

# -------- Visual assets ---------
def save(fig,path):
 fig.savefig(FIG/path,dpi=185,bbox_inches='tight');fig.savefig(FIG/path.replace('.png','.svg'),bbox_inches='tight');plt.close(fig)
def add_note(fig,text):fig.text(.02,.013,text,fontsize=8,color='#475569')
def direct_stage(case,b,stage):return stages[(stages.case==case)&(stages.bias==b)&(stages.stage==stage)].iloc[0]

# FIG 01: three-stage performance B0.
fig,axes=plt.subplots(1,2,figsize=(13,5.2),gridspec_kw={'wspace':.16})
inds=np.arange(3);sw=.245
stageDefs=[('Direct LoS — zero mean','Direct LoS · clean mean',COL['LOS']),('Full multipath — BB_ORIG','Full RF · baseline',COL['FULL']),('Full multipath — MB_VAR','Full RF · proposed',COL['MB'])]
for ai,(metric,title,unit) in enumerate([('head_rmse_deg','Heading RMSE','°'),('xy_rmse_cm','Position RMSE (XY)','cm')]):
 ax=axes[ai]
 for j,(key,label,color) in enumerate(stageDefs):
  vals=[float(direct_stage(c,'B0',key)[metric]) for c in CASES]
  bars=ax.bar(inds+(j-1)*sw,vals,width=sw,alpha=.95,label=label,color=color)
  for rect,v in zip(bars,vals):ax.annotate(f'{v:.2f}',(rect.get_x()+rect.get_width()/2,v),ha='center',va='bottom',fontsize=8,xytext=(0,3),textcoords='offset points')
 ax.set_xticks(inds,ROUTES);ax.set_title(title,fontweight='bold');ax.set_ylabel(unit);ax.grid(axis='y',alpha=.23)
 ax.set_ylim(0,max([float(direct_stage(c,'B0',k)[metric]) for c in CASES for k,_,_ in stageDefs])*1.22)
fig.suptitle('같은 RF 경로에서: Direct LoS → Full multipath → 경험적 보정',fontsize=15,fontweight='bold')
axes[0].legend(loc='upper left',frameon=False,fontsize=8)
add_note(fig,'B0 · 동일 운동/초기/P0/R_base · LoS만 μ=0; Full BB/MB는 기존 μ 사용. LoS→Full 차이는 순수 단일요인 인과효과가 아님.')
fig.tight_layout(rect=[0,.05,1,.95]);save(fig,'F01_THREE_STAGE_B0_PERFORMANCE.png')

# FIG 02: 12-case three-stage heatmaps
vals_h=[];vals_xy=[];labels=[]
for c in CASES:
 for b in BIAS:
  labels.append(f'{RNAME[c]} / {b}')
  vals_h.append([float(direct_stage(c,b,k).head_rmse_deg) for k,_,_ in stageDefs])
  vals_xy.append([float(direct_stage(c,b,k).xy_rmse_cm) for k,_,_ in stageDefs])
fig,axes=plt.subplots(1,2,figsize=(11.3,8.8),gridspec_kw={'wspace':.45})
for ax,grid,tt,unit in zip(axes,[np.asarray(vals_h),np.asarray(vals_xy)],['Heading RMSE (°)','XY RMSE (cm)'],['°','cm']):
 im=ax.imshow(grid,aspect='auto',cmap='YlOrRd',vmin=0,vmax=float(np.max(grid)))
 ax.set_yticks(np.arange(len(labels)),labels);ax.set_xticks(range(3),['Direct LoS','Full BB','Full MB'],rotation=25,ha='right')
 for i in range(len(labels)):
  for j in range(3):
   col='#f8fafc' if grid[i,j]>np.max(grid)*.6 else '#1e293b'
   ax.text(j,i,f'{grid[i,j]:.2f}',ha='center',va='center',fontsize=8,color=col)
 ax.set_title(tt,fontweight='bold');ax.set_yticks([3.5,7.5],minor=True);ax.grid(which='minor',axis='y',color='white',linewidth=2)
 fig.colorbar(im,ax=ax,shrink=.7,label=unit)
fig.suptitle('12조건 전체: 세 단계의 Heading 및 XY 성능',fontsize=15,fontweight='bold')
add_note(fig,'Direct LoS=새 탐색적 μ0 replay, Full BB/MB=보존 self-gate 결과. 동일 Corridor·seed의 반복 조건, 독립 물리 환경 아님.')
fig.tight_layout(rect=[0,.045,1,.955]);save(fig,'F02_THREE_STAGE_12_CONDITIONS.png')

# FIG 03: original polarized signal LoS vs Full plus signed difference
fig,axes=plt.subplots(3,2,figsize=(13,9.0),sharex='row',gridspec_kw={'wspace':.2,'hspace':.30})
for i,c in enumerate(CASES):
 d=phy[phy.case==c]
 a,b=axes[i]
 a.plot(d.t_s,d.LoS_s,color=COL['LOS'],linewidth=1.2,label='Direct LoS')
 a.plot(d.t_s,d.Full_s,color=COL['FULL'],linewidth=.9,alpha=.87,label='Full multipath')
 a.set_ylim(-1.08,1.08);a.set_ylabel(f'{RNAME[c]}   s [-]');a.set_title(f'{RNAME[c]} · 실제 두 포트 편파비')
 a.axvline(30,color='#9ca3af',ls=':',lw=.8)
 b.plot(d.t_s,d.Full_minus_LoS_s,color=COL['FULL'],lw=.95,label='Full - LoS')
 sw=d[d.tap_switched_Full_vs_LoS==1]
 b.scatter(sw.t_s,sw.Full_minus_LoS_s,color=COL['HIGHLIGHT'],s=5,alpha=.45,label='tap changed' if i==0 else None)
 b.axhline(0,color='#87909b',lw=.6);b.axvline(30,color='#9ca3af',ls=':',lw=.8)
 b.set_title('다중경로에 따른 signed 편파 변화 + tap 전환')
 b.set_ylabel('Full - LoS 편파비')
 for ax in (a,b):ax.set_xlim(0,d.t_s.iloc[-1]);ax.set_xlabel('주행 시간 (s)');ax.grid(axis='y',alpha=.18)
axes[0,0].legend(frameon=False,ncol=2,fontsize=8);axes[0,1].legend(frameon=False,fontsize=8)
fig.suptitle('동일 pose의 실제 H 비교: LoS 편파정보와 Full RF 왜곡',fontsize=15,fontweight='bold')
add_note(fig,'Original H에서 산출한 공통 first-path tap · 점=Full/LoS tap 불일치 · 좌·우 동일 시간/pose · filter 성능 결과가 아님.')
fig.tight_layout(rect=[0,.037,1,.96]);save(fig,'F03_RAW_MULTIPATH_POLARIZATION_TIME.png')

# FIG 04: distance conditions 3 related physical quantities
f=bins[bins.window=='t>=30'].copy();groups=[(c,f[f.case==c]) for c in CASES]
fig,axes=plt.subplots(1,3,figsize=(14.5,4.8),gridspec_kw={'wspace':.25})
setts=[('Full_LoS_s_RMS','RMS 편파 변화: Full - LoS','편파비 [-]'),('Full_vs_LoS_tap_switch_fraction','첫 경로 tap 변경 비율','비율'),('median_abs_J_heading_per_rad','Direct LoS 모델의 Heading 민감도','|H_sψ| (rad⁻¹)')]
style=[COL['LOS'],COL['FULL'],COL['MB']]
for ax,(key,title,ylabel) in zip(axes,setts):
 for (c,d),color in zip(groups,style):
  ax.plot(d.rho_mid_m,d[key],'-o',label=RNAME[c],color=color,markersize=6,linewidth=2)
  for _,r in d.iterrows():
   if r['n']<20:ax.annotate(f'n={int(r["n"])}',(r.rho_mid_m,r[key]),fontsize=7,xytext=(2,4),textcoords='offset points')
 ax.set_title(title,fontweight='bold');ax.set_xlabel('앵커 수평거리 구간 중심 (m)');ax.set_ylabel(ylabel);ax.grid(axis='y',alpha=.2)
ax=axes[-1];ax.legend(frameon=False,fontsize=8)
fig.suptitle('거리 조건별: 관측 왜곡 · 검출 전환 · 물리적 Heading 민감도',fontsize=15,fontweight='bold')
add_note(fig,'t≥30 s 모든 finite packet · 각 점은 거리 구간의 통계, 구간 수는 별도 CSV · 민감도는 true pose SourceFFD·필터 후 개선량 아님.')
fig.tight_layout(rect=[0,.05,1,.95]);save(fig,'F04_RANGE_CONDITIONED_PHYSICS.png')

# FIG 05: range mean correction does not change s physics; same B0 BASE mask
fig,axes=plt.subplots(1,2,figsize=(12,4.8))
for ai,metric,title in [(0,'r_error_RMS_cm','거리 관측오차 RMS'),(1,'r_error_mean_cm','signed 거리 오차 평균')]:
 ax=axes[ai];sh=.24;idx=np.arange(3)
 for j,(stage,label,color) in enumerate([('Direct LoS — no RF mean','Direct LoS (μ=0)',COL['LOS']),('Full — original mean','Full + 기존 평균',COL['FULL']),('Full — EXDS mean','Full + EXDS 평균',COL['MB'])]):
  vals=[res.query('case==@c and stage==@stage')[metric].item() for c in CASES]
  bars=ax.bar(idx+(j-1)*sh,vals,width=sh,label=label,color=color)
  for bar,v in zip(bars,vals):ax.annotate(f'{v:+.1f}' if ai else f'{v:.1f}',(bar.get_x()+bar.get_width()/2,bar.get_height()),xytext=(0,4 if v>=0 else -10),textcoords='offset points',fontsize=8,ha='center')
 ax.axhline(0,color='#909aa5',lw=.8);ax.set_xticks(idx,ROUTES);ax.set_title(title,fontweight='bold');ax.set_ylabel('cm');ax.grid(axis='y',alpha=.18)
axes[0].legend(frameon=False,fontsize=8)
fig.suptitle('같은 B0 BASE 수용집합: 거리 평균 교체가 실제로 바꾼 것은 무엇인가?',fontsize=15,fontweight='bold')
add_note(fig,'Full 원 RF, 동일 기준 관측 집합(t≥30s & BB BASE accepted). 편파 원신호와 물리 J는 평균 교체로 바뀌지 않음.')
fig.tight_layout(rect=[0,.05,1,.95]);save(fig,'F05_RANGE_MEAN_ERROR_DECOMPOSITION.png')

# FIG 06: same prior local metric vs full recursive performance
s=local[local.bias=='B0'].set_index('case').loc[CASES]
fig,ax=plt.subplots(figsize=(10.5,5.5));ind=np.arange(3);width=.33
for j,(col,title,color) in enumerate([('local_pct_MBVAR_vs_MBORIG','동일 BB prior의 즉시 Heading MSE 개선율',COL['FULL']),('final_pct_MBVAR_vs_MBORIG','전체 재귀 Heading RMSE 개선율',COL['MB'])]):
 bars=ax.bar(ind+(j-.5)*width,s[col],width=width,color=color,label=title)
 for rect,v in zip(bars,s[col]):
  ax.annotate(f'{v:+.1f}%',(rect.get_x()+rect.get_width()/2,v),ha='center',va='bottom' if v>=0 else 'top',xytext=(0,3 if v>=0 else -3),textcoords='offset points',fontsize=9)
ax.axhline(0,color='#475569',lw=1);ax.set_xticks(ind,ROUTES);ax.set_ylabel('오차 변화율 (%) — 양수는 개선');ax.set_title('국소 효과와 전체 재귀 효과는 같은 방향일 필요가 없습니다',fontweight='bold');ax.grid(axis='y',alpha=.22)
ax.legend(frameon=False,fontsize=9,loc='upper right')
fig.suptitle('물리 관측의 신뢰도 조절: 동일 prior vs 누적 갱신',fontsize=15,fontweight='bold')
add_note(fig,'서로 다른 오차 지표(MSE vs RMSE)의 동일 기준 상대변화. 동일-prior shadow는 BB prior, 전체재귀는 각 arm 자신의 self-gate.')
fig.tight_layout(rect=[0,.06,1,.95]);save(fig,'F06_LOCAL_VS_RECURSIVE_EFFECT.png')

# FIG 07: B0 heading time response, physical multipath error, and range axis
fig,axes=plt.subplots(3,3,figsize=(16,9),gridspec_kw={'hspace':.32,'wspace':.26})
for i,c in enumerate(CASES):
 d=pd.read_csv(TAB/f'TIME_RESOLVED_{c}_B0.csv')
 t=d.time_s.to_numpy();ax=axes[i,0]
 ax.plot(t,d.s_Full_minus_LoS,color=COL['FULL'],lw=.9)
 ax.axhline(0,color='#777',lw=.7);ax.set_ylabel(f'{RNAME[c]}\nΔs (Full-LoS)')
 ax=axes[i,1]
 for key,label,color in [('LOS','Direct LoS',COL['LOS']),('BB','Full BB',COL['FULL']),('MB','Full MB',COL['MB'])]:
  y=d[f'heading_abs_error_{key}_deg'].rolling(26,center=True,min_periods=1).mean()
  ax.plot(t,y,color=color,lw=1.7,label=label)
 ax.set_ylabel('Heading |error| (°)');ax.set_ylim(bottom=0)
 ax=axes[i,2];ax.plot(t,d.rho_true_m,color=COL['OTHER'],lw=1.5);ax.set_ylabel('수평거리 ρ (m)');ax.set_ylim(-.3,10)
 for ax in axes[i]:
  ax.axvline(30,color='#94a3b8',ls=':',lw=1)
  ax.grid(axis='y',alpha=.16);ax.set_xlim(t[0],t[-1]);ax.set_xlabel('시간 t (s)')
axes[0,0].set_title('원시 물리 오염');axes[0,1].set_title('Heading 오차: 5.2s 이동평균');axes[0,2].set_title('기하 조건의 시간 변화')
axes[0,1].legend(frameon=False,fontsize=8,ncol=3,loc='upper right')
fig.suptitle('같은 시간축에서: 편파 왜곡 → Heading 오차 → 거리 조건',fontsize=15,fontweight='bold')
add_note(fig,'B0 / seed0 · LoS는 새 zero-mean counterfactual · 원 Full BB/MB trace · Δs는 원 Full-LoS H · 시간 평균은 시각화용, 평가는 원 전체시점 RMSE.')
fig.tight_layout(rect=[0,.03,1,.96]);save(fig,'F07_TIME_ALIGNED_PHYSICS_AND_HEADING.png')

# FIG 08: time correlation and equivalent travel distance of same samples
fig,axes=plt.subplots(1,2,figsize=(12.5,4.8))
for case,color in zip(CASES,[COL['LOS'],COL['FULL'],COL['MB']]):
 a=acf[acf.case==case]
 axes[0].plot(a.lag_time_s,a.acf_unbiased_denominator_no,label=RNAME[case],color=color,lw=2)
 axes[1].plot(a.median_path_travel_m,a.acf_unbiased_denominator_no,label=RNAME[case],color=color,lw=2)
for ax in axes:
 ax.axhline(np.exp(-1),color='#4b5563',lw=1,ls='--');ax.axhline(0,color='#94a3b8',lw=.7)
 ax.grid(axis='y',alpha=.22);ax.set_ylim(-.25,1.05);ax.set_ylabel('편파 잔차 ACF')
axes[0].set_xlabel('시간 lag (s)');axes[0].set_title('시간순 잔차의 지속성')
axes[1].set_xlabel('동일 lag의 이동거리 중앙값 (m)');axes[1].set_title('시간 lag을 이동거리로 환산')
axes[0].legend(frameon=False,fontsize=9)
fig.suptitle('주행 시계열의 편파 잔차 상관 — 공간/시간 과정의 독립적 분해는 아님',fontsize=14,fontweight='bold')
add_note(fig,'B0 Full RF와 SourceFFD 기준 MB 편파 잔차 · 전체 timeline · 거리=동일 시간lag의 누적 주행거리 중앙값, 공간 field covariance 추정 아님.')
fig.tight_layout(rect=[0,.05,1,.95]);save(fig,'F08_TEMPORAL_CORRELATION_AND_TRAVEL.png')

# FIG 09: why zero-mean LoS and frozen-full-mean LoS are different benchmarks
fig,axes=plt.subplots(1,2,figsize=(12.5,4.7))
styles=[('Direct LoS — zero mean','LoS + clean μ0',COL['LOS']),('Direct LoS — frozen Full BB mean','LoS + Full BB의 μ',COL['HIGHLIGHT']),('Full multipath — BB_ORIG','Full BB',COL['FULL'])]
for ax,metric,title in zip(axes,['head_rmse_deg','xy_rmse_cm'],['Heading RMSE','XY RMSE']):
 for i,c in enumerate(CASES):
  vals=[float(direct_stage(c,'B0',k)[metric]) for k,_,_ in styles]
  ax.plot(range(3),vals,'-o',lw=1.75,color=[COL['LOS'],COL['OTHER'],COL['FULL']][i],label=RNAME[c])
  for j,v in enumerate(vals):ax.annotate(f'{v:.2f}',(j,v),xytext=(3,5),textcoords='offset points',fontsize=8)
 ax.set_xticks(range(3),[lab for _,lab,_ in styles],rotation=15,ha='right');ax.set_ylabel('°' if metric=='head_rmse_deg' else 'cm');ax.set_title(title)
 ax.grid(axis='y',alpha=.2)
axes[0].legend(frameon=False,ncol=1,fontsize=8)
fig.suptitle('통제 실험: 다중경로 유무와 평균보정 적합성은 구분해야 합니다',fontsize=14,fontweight='bold')
add_note(fig,'Direct H의 평균 μ0는 LoS에 맞는 이상적 참조. LoS+Full μ는 RF H만 바꾼 통제군이며 보정 전이를 보증하지 않음.')
fig.tight_layout(rect=[0,.05,1,.95]);save(fig,'F09_LOS_MEAN_CONTROL_AND_CAUSAL_BOUNDARY.png')

# FIG 10: one reproducible high-multipath example from each case (max |Full-LoS s| after t>=30)
fig,axes=plt.subplots(3,2,figsize=(13,8.5),gridspec_kw={'hspace':.36,'wspace':.22})
chosen=[]
for i,c in enumerate(CASES):
 d=phy[(phy.case==c)&(phy.t_s>=30)].copy()
 idx=d.Full_minus_LoS_s.abs().idxmax();r=d.loc[idx];chosen.append(dict(case=c,pose_id=int(r.pose_id),t_s=float(r.t_s),abs_delta_s=float(abs(r.Full_minus_LoS_s)),source_rule='MAX_ABS_FULL_MINUS_LOS_S_WHEN_T_GE_30'))
 clip=phy[(phy.case==c)&(abs(phy.t_s-r.t_s)<4.9)]
 ax=axes[i,0];ax.plot(clip.t_s,clip.LoS_s,color=COL['LOS'],lw=1.5,label='LoS');ax.plot(clip.t_s,clip.Full_s,color=COL['FULL'],lw=1.5,label='Full');ax.axvline(r.t_s,color=COL['HIGHLIGHT'],ls=':',lw=1)
 ax.set_ylim(-1.07,1.07);ax.set_ylabel(f'{RNAME[c]} signed s');ax.set_title(f'큰 편파 왜곡 예시 t={r.t_s:.1f}s, ρ={r.rho_true_m:.2f}m')
 ax=axes[i,1];ax.plot(clip.t_s,10*np.log10(np.maximum(clip.LoS_Pplus,1e-30)),color=COL['LOS'],lw=1.25,label='LoS P+')
 ax.plot(clip.t_s,10*np.log10(np.maximum(clip.LoS_Pminus,1e-30)),color=COL['LOS'],lw=1.25,ls='--',label='LoS P-')
 ax.plot(clip.t_s,10*np.log10(np.maximum(clip.Full_Pplus,1e-30)),color=COL['FULL'],lw=1.25,label='Full P+')
 ax.plot(clip.t_s,10*np.log10(np.maximum(clip.Full_Pminus,1e-30)),color=COL['FULL'],lw=1.25,ls='--',label='Full P-')
 ax.axvline(r.t_s,color=COL['HIGHLIGHT'],ls=':',lw=1);ax.set_ylabel('10log10(P) (상대 단위)');ax.set_title('두 수신 포트 복소 중첩의 전력 변화')
 for ax in axes[i]:ax.set_xlabel('시간 t (s)');ax.grid(axis='y',alpha=.16)
axes[0,0].legend(frameon=False,fontsize=8);axes[0,1].legend(frameon=False,ncol=2,fontsize=8)
fig.suptitle('대표적인 큰 편파 왜곡 구간 — 최대 |Full-LoS|로 선택한 예시이며 평균적인 사례가 아님',fontsize=14,fontweight='bold')
add_note(fig,'t≥30 각 case의 최대 |Δs| 조건 선택을 명시. P±은 원 채널 상대 전력값, dBm이 아님; 이 그림만으로 특정 ray 원인 증명 불가.')
fig.tight_layout(rect=[0,.035,1,.955]);save(fig,'F10_MAX_DISTORTION_PORT_POWER_EXAMPLES.png')
pd.DataFrame(chosen).to_csv(TAB/'ILLUSTRATIVE_WINDOWS_SELECTION.csv',index=False)


# FIG 11: raw physical angular sensitivity vs effective identical-prior information weight
fig,axes=plt.subplots(1,2,figsize=(12.2,4.8),gridspec_kw={'wspace':.25})
x=np.arange(3)
sens=physummary.query("scope == 't>=30'").set_index('case').loc[CASES,'median_abs_J_heading'].to_numpy()
bar=axes[0].bar(x,sens,color=[COL['LOS'],COL['FULL'],COL['MB']],width=.55)
for r,v in zip(bar,sens):axes[0].annotate(f'{v:.3f}',(r.get_x()+r.get_width()/2,v),ha='center',xytext=(0,5),textcoords='offset points')
axes[0].set_xticks(x,ROUTES);axes[0].set_ylabel('median |H_sψ| (rad⁻¹)')
axes[0].set_title('물리적 Heading 민감도 (true-pose FFD)',fontweight='bold')
axes[0].grid(axis='y',alpha=.22)
pa=pd.read_csv(TAB/'MATCHED_PRIOR_POLARIZATION_GAIN_12.csv').query("bias == 'B0'")
for j,(arm,name,color) in enumerate([('BB_ORIG','기본 R',COL['FULL']),('MB_VAR','편파 추가분산 R',COL['MB'])]):
 vals=pa.query('arm == @arm').set_index('case').loc[CASES,'median_abs_Kpsi_s'].to_numpy()
 bars=axes[1].bar(x+(j-.5)*.33,vals,width=.33,color=color,label=name)
 for rect,v in zip(bars,vals):axes[1].annotate(f'{v:.4f}',(rect.get_x()+rect.get_width()/2,v),ha='center',xytext=(0,5),textcoords='offset points',fontsize=9)
axes[1].set_xticks(x,ROUTES);axes[1].set_ylabel('median |K_ψ,s| (rad per unit s)')
axes[1].set_title('같은 BB prior에서 편파 갱신 gain',fontweight='bold');axes[1].legend(frameon=False,fontsize=9)
axes[1].grid(axis='y',alpha=.22)
fig.suptitle('물리적 센서의 민감도와 필터의 신뢰도 가중치는 다릅니다',fontsize=14,fontweight='bold')
add_note(fig,'좌: t≥30 모든 finite true-pose 표본. 우: 동일 BB-prior shadow, fixed BASE accepted & t≥30. 서로 다른 분모이므로 인과 기여량 아님.')
fig.tight_layout(rect=[0,.045,1,.95]);save(fig,'F11_PHYSICAL_SENSITIVITY_VS_FILTER_GAIN.png')

# FIG 12: heading/XY RMSE within physical distance bins, 3-stage same timepoints
perf=[]
for c in CASES:
 d=pd.read_csv(TAB/f'TIME_RESOLVED_{c}_B0.csv')
 d=d[d.time_s>=SCORESTART]
 for l,r in zip(BINEDGES[:-1],BINEDGES[1:]):
  v=d[(d.rho_true_m>=l)&(d.rho_true_m<r)]
  if not len(v):continue
  for key,name in [('LOS','Direct LoS'),('BB','Full baseline'),('MB','Full corrected')]:
   perf.append(dict(case=c,route=RNAME[c],gyro='B0',rho_lo_m=l,rho_hi_m=r,rho_mid_m=(l+r)/2,n_timepoints=len(v),stage=name,
    heading_RMSE_deg=float(np.sqrt(np.mean(v[f'heading_error_{key}_deg']**2))),
    xy_RMSE_cm=float(np.sqrt(np.mean(v[f'xy_error_{key}_cm']**2)))))
perf=pd.DataFrame(perf);perf.to_csv(TAB/'DISTANCE_BIN_PERFORMANCE_B0.csv',index=False)
fig,axes=plt.subplots(3,2,figsize=(12.5,9.2),gridspec_kw={'hspace':.38,'wspace':.26})
for i,c in enumerate(CASES):
 for j,(metric,title,unit) in enumerate([('heading_RMSE_deg','거리별 Heading RMSE','°'),('xy_RMSE_cm','거리별 XY RMSE','cm')]):
  ax=axes[i,j];q=perf[perf.case==c];
  for s,name,color in [('Direct LoS','Direct LoS',COL['LOS']),('Full baseline','Full BB',COL['FULL']),('Full corrected','Full MB_VAR',COL['MB'])]:
   v=q[q.stage==s];ax.plot(v.rho_mid_m,v[metric],'-o',lw=1.85,color=color,markersize=5,label=name)
  ax.set_xlabel('수평거리 구간 중심 ρ (m)');ax.set_ylabel(f'{RNAME[c]}  {unit}');ax.set_title(title,fontweight='bold')
  ax.grid(axis='y',alpha=.2)
  if i==0 and j==0:ax.legend(frameon=False,fontsize=8,ncol=3)
fig.suptitle('거리 조건에 따라 Full 오염과 보정의 Heading·위치 효과도 달라집니다',fontsize=14,fontweight='bold')
add_note(fig,'B0, 원 평가구간 t≥30 전체 timepoints · 거리 구간은 같은 원 자료를 분할한 조건부 RMSE · LoS=새 zero-mean counterfactual.')
fig.tight_layout(rect=[0,.035,1,.955]);save(fig,'F12_DISTANCE_CONDITIONED_3_STAGE_PERFORMANCE.png')

print('FIGURES',len(list(FIG.glob('*.png'))),'TABLES',len(list(TAB.glob('*.csv'))))
print('PHYS SUMMARY\n',physummary.to_string(index=False))
print('THREE STAGE B0\n',stages[stages.bias=='B0'][['route','stage','head_rmse_deg','xy_rmse_cm']].to_string(index=False))
