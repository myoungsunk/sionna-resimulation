"""Presentation-only redraw of the supplied 13 figures, from archived CSVs."""
from pathlib import Path
from zipfile import ZipFile
import csv, hashlib, io, json, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pymupdf as fitz

VAULT=Path('C:/Users/Myoungsun Kim/Obsidian Vault')
BASE=VAULT/'03_Research/EKF/2026-11-01 논문 초안'
OUT=BASE/'figures/01b_physics_ieee_20261102'
OUT.mkdir(parents=True,exist_ok=True)
ZIP=Path('C:/Users/Myoungsun Kim/Downloads/DualLP_ThreeStage_Physics_Figures_Data_20261102.zip')
z=ZipFile(ZIP); PREFIX='DualLP_ThreeStage_Physics_20261102/'
manifest=json.loads(z.read(PREFIX+'PACKAGE_MANIFEST.json'))
hashes={r['path']:r['sha256'] for r in manifest['files']}
sources={}
def read(name):
    data=z.read(PREFIX+'tables/'+name)
    digest=hashlib.sha256(data).hexdigest()
    assert digest==hashes['tables/'+name],name
    sources[name]=digest
    return pd.read_csv(io.BytesIO(data))
p=read('PHYSICAL_LOS_FULL_PACKET_3136.csv')
st=read('THREE_STAGE_COMPARISON_12_BIASES.csv')
bins=read('DISTANCE_BINS_PHYSICAL.csv').query("window=='t>=30'")
res=read('RANGE_ERROR_SAME_FIXED_MASK_B0.csv')
local=read('LOCAL_VS_RECURSIVE_HEADING_12.csv').query("bias=='B0'")
acf=read('POLARIZATION_ACF_TIME_AND_TRAVEL.csv')
win=read('ILLUSTRATIVE_WINDOWS_SELECTION.csv')
sens=read('PHYSICAL_SIGNATURES_3_ROUTES.csv').query("scope=='t>=30'")
gain=read('MATCHED_PRIOR_POLARIZATION_GAIN_12.csv').query("bias=='B0'")
dist=read('DISTANCE_BIN_PERFORMANCE_B0.csv')
assert len(p)==3136 and len(st)==48
CASES=['R2_aB_m0','R4_aB_m0','R5_aB_m0']
NAMES=['Loop','Zigzag','Serpentine']; BIAS=['B0','L0','L1','L2']
COL=['#28689d','#bd641b','#286946']; LS=['-','--','-.']
STAGES=['Direct LoS — zero mean','Full multipath — BB_ORIG','Full multipath — MB_VAR']
LABELS=['LOS (zero mean)','Full BB_ORIG','Full MB_VAR']
plt.rcParams.update({'font.family':'Times New Roman','font.size':9,'axes.labelsize':9,
    'axes.titlesize':9,'legend.fontsize':9,'xtick.labelsize':9,'ytick.labelsize':9,
    'pdf.fonttype':42,'ps.fonttype':42,'mathtext.fontset':'stix','axes.linewidth':.65,
    'lines.linewidth':.9,'hatch.linewidth':.5,'savefig.facecolor':'white'})
selected=set(map(int,sys.argv[1:])) if len(sys.argv)>1 else set(range(1,14))
def layout(nr=1,nc=2,h=3.0):
    fig,ax=plt.subplots(nr,nc,figsize=(7.16,h),squeeze=False)
    return fig,ax
def series(ax,x,ys,labels=LABELS):
    for j,(y,label) in enumerate(zip(ys,labels)):
        ax.plot(x,y,color=COL[j],ls=LS[j],label=label)
def bars(ax,values,labels=LABELS,xticks=NAMES,colors=COL):
    x=np.arange(len(xticks)); w=.24
    for j,(v,label) in enumerate(zip(values,labels)):
        ax.bar(x+(j-(len(values)-1)/2)*w,v,w*.92,label=label,color=colors[j],
            edgecolor='black',linewidth=.5,hatch=['','///','xx'][j])
    ax.set_xticks(x,xticks)
    if np.min(values)>=0:ax.set_ylim(bottom=0)
def save(fig,axes,num,legend=True):
    axes=np.asarray(axes).ravel()
    handles,labels=axes[0].get_legend_handles_labels()
    if legend and handles:fig.legend(handles,labels,loc='upper center',ncol=min(3,len(labels)),frameon=False,bbox_to_anchor=(.5,.995))
    for i,ax in enumerate(axes):
        title=ax.get_title();ax.set_title('')
        ax.set_title(f'({chr(97+i)}) '+title,loc='left',pad=6)
        ax.set_axisbelow(True)
        if num!=2:ax.grid(axis='y',lw=.4,color='.87')
        ax.spines[['top','right']].set_visible(False)
        ax.tick_params(width=.65,length=3)
    fig.tight_layout(rect=(0,0,.90 if num==13 else 1,.91 if fig.legends else 1),h_pad=1.8,w_pad=1.8)
    if num==13:
        cb=fig.colorbar(axes[1].collections[0],cax=fig.add_axes([.925,.14,.018,.64]))
        cb.set_label(r'$|s_{Full}-s_{LOS}|$')
    fig.canvas.draw(); renderer=fig.canvas.get_renderer(); outside=[]
    texts=list(fig.texts)
    if fig.legends:texts+=list(fig.legends[0].get_texts())
    for ax in axes:
        texts += [ax.xaxis.label,ax.yaxis.label,ax.title,ax._left_title]+list(ax.texts)
        texts += [t.label1 for t in ax.xaxis.get_major_ticks() if ax.get_xlim()[0]<=t.get_loc()<=ax.get_xlim()[1]]
        texts += [t.label1 for t in ax.yaxis.get_major_ticks() if ax.get_ylim()[0]<=t.get_loc()<=ax.get_ylim()[1]]
    for t in texts:
        if t.get_visible() and t.get_text():
            b=t.get_window_extent(renderer)
            if b.x0<-.5 or b.y0<-.5 or b.x1>fig.bbox.width+.5 or b.y1>fig.bbox.height+.5:outside.append(t.get_text())
    assert not outside,(num,outside)
    name=f'F{num:02d}_IEEE'
    fig.savefig(OUT/(name+'.pdf'));fig.savefig(OUT/(name+'.png'),dpi=600)
    with fitz.open(OUT/(name+'.pdf')) as doc:
        fonts=doc[0].get_fonts(full=True)
        assert fonts and all('Type3' not in str(f) and len(doc.extract_font(f[0])[3])>0 for f in fonts)
        doc[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(str(OUT/(name+'_preview.png')))
    qa={'figure':name,'inches':list(fig.get_size_inches()),'dpi':600,'embedded_fonts':[f[3] for f in fonts],
        'out_of_canvas_text':outside,'source_tables_sha256':sources,'source_zip_sha256':hashlib.sha256(ZIP.read_bytes()).hexdigest(),
        'new_simulation':False,'labels':LABELS,'routes':dict(zip(CASES,NAMES))}
    (OUT/(name+'_QA.json')).write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    plt.close(fig);print(name,flush=True)

if 1 in selected:
    fig,a=layout(h=3.1)
    for ax,k,y in zip(a[0],['head_rmse_deg','xy_rmse_cm'],['Heading RMSE (deg)','XY RMSE (cm)']):
        bars(ax,[[st.query('case==@c and bias=="B0" and stage==@s')[k].item() for c in CASES] for s in STAGES]);ax.set_ylabel(y)
    save(fig,a,1)
if 2 in selected:
    fig,a=layout(h=5.6); order=[(c,b) for c in CASES for b in BIAS]
    for ax,k,title in zip(a[0],['head_rmse_deg','xy_rmse_cm'],['Heading RMSE (deg)','XY RMSE (cm)']):
        v=np.array([[st.query('case==@c and bias==@b and stage==@s')[k].item() for s in STAGES] for c,b in order])
        ax.imshow(v,aspect='auto',cmap='Blues',vmin=0,vmax=v.max());ax.grid(False)
        ax.set_xticks(range(3),['LOS','Full BB','Full MB']);ax.set_yticks(range(12),[f'{NAMES[CASES.index(c)]} {b}' for c,b in order]);ax.set_title(title)
        for i in range(12):
            for j in range(3):ax.text(j,i,f'{v[i,j]:.2f}',ha='center',va='center',color='white' if v[i,j]>v.max()*.6 else 'black')
    save(fig,a,2,False)
if 3 in selected:
    fig,a=layout(3,2,7.4)
    for i,c in enumerate(CASES):
        d=p[p.case==c].sort_values('pose_id');x=d.t_s
        series(a[i,0],x,[d.LoS_s,d.Full_s],['LOS channel','Full channel']);a[i,0].set_ylabel('Normalized power difference, s');a[i,0].set_ylim(-1.1,1.1);a[i,0].set_title(NAMES[i])
        ax=a[i,1];ax.plot(x,d.Full_minus_LoS_s,color=COL[1]);m=d.tap_switched_Full_vs_LoS.astype(bool);ax.scatter(x[m],d.Full_minus_LoS_s[m],s=4,color=COL[1],marker='x');ax.axhline(0,color='.5',lw=.5);ax.set_ylabel(r'$s_{Full}-s_{LOS}$');ax.set_title('Crosses: different tap')
        for ax in a[i]:ax.set_xlabel('Time (s)')
    save(fig,a,3)
if 4 in selected:
    fig,a=layout(1,3,3.1)
    for ax,k,label in zip(a[0],['Full_LoS_s_RMS','Full_vs_LoS_tap_switch_fraction','median_abs_J_heading_per_rad'],[r'RMS $(s_{Full}-s_{LOS})$','Tap mismatch fraction',r'Median $|H_{s\psi}|$ (rad$^{-1}$)']):
        for j,c in enumerate(CASES):
            d=bins[bins.case==c];ax.plot(d.rho_mid_m,d[k],color=COL[j],ls=LS[j],marker=['o','s','^'][j],markersize=3,label=NAMES[j])
        ax.set_ylabel(label);ax.set_xlabel('Horizontal range (m)');ax.set_ylim(bottom=0)
    save(fig,a,4)
if 5 in selected:
    fig,a=layout(h=3.2)
    stages=list(res.stage.unique())
    for ax,k,label in zip(a[0],['r_error_RMS_cm','r_error_mean_cm'],['Range residual RMS (cm)','Mean range residual (cm)']):
        bars(ax,[[res.query('case==@c and stage==@s')[k].item() for c in CASES] for s in stages],['LOS (zero mean)','Full: original mean','Full: EXDS mean']);ax.set_ylabel(label);ax.axhline(0,color='.5',lw=.5)
    save(fig,a,5)
if 6 in selected:
    fig,a=layout(1,1,3.2);ax=a[0,0]
    d=local.set_index('case').loc[CASES]
    bars(ax,[d.local_pct_MBVAR_vs_MBORIG,d.final_pct_MBVAR_vs_MBORIG],['Same-prior immediate MSE','Recursive RMSE']);ax.axhline(0,color='.3',lw=.7);ax.set_ylabel('Error reduction (%)');save(fig,a,6)
if 7 in selected:
    fig,a=layout(3,3,7.4)
    for i,c in enumerate(CASES):
        d=read(f'TIME_RESOLVED_{c}_B0.csv');t=d.time_s
        a[i,0].plot(t,d.s_Full_minus_LoS,color=COL[1]);a[i,0].set_ylabel(r'$s_{Full}-s_{LOS}$');a[i,0].set_title(NAMES[i])
        ys=[d[f'heading_abs_error_{arm}_deg'].rolling(26,center=True,min_periods=1).mean() for arm in ['LOS','BB','MB']]
        series(a[i,1],t,ys);a[i,1].set_ylabel('Heading absolute error (deg)');a[i,1].set_ylim(bottom=0)
        a[i,2].plot(t,d.rho_true_m,color='.3');a[i,2].set_ylabel('Horizontal range (m)');a[i,2].set_ylim(bottom=0)
        for ax in a[i]:ax.set_xlabel('Time (s)')
    h,l=a[0,1].get_legend_handles_labels();fig.legend(h,l,loc='upper center',ncol=3,frameon=False)
    save(fig,a,7)
if 8 in selected:
    fig,a=layout(h=3.2)
    for ax,k,label in zip(a[0],['lag_time_s','median_path_travel_m'],['Time lag (s)','Median travel at same lag (m)']):
        for j,c in enumerate(CASES):
            d=acf[acf.case==c];ax.plot(d[k],d.acf_unbiased_denominator_no,color=COL[j],ls=LS[j],label=NAMES[j])
        ax.axhline(0,color='.5',lw=.5);ax.set_xlabel(label);ax.set_ylabel('Polarization residual ACF');ax.set_ylim(-.25,1.05)
    save(fig,a,8)
if 9 in selected:
    fig,a=layout(3,2,7.2)
    stages=[STAGES[0],'Direct LoS — frozen Full BB mean',STAGES[1]]
    for i,c in enumerate(CASES):
        for ax,k,label in zip(a[i],['head_rmse_deg','xy_rmse_cm'],['Heading RMSE (deg)','XY RMSE (cm)']):
            bars(ax,[[st.query('case==@c and bias=="B0" and stage==@s')[k].item()] for s in stages],['LOS: zero mean','LOS: Full BB mean','Full BB_ORIG'],[NAMES[i]]);ax.set_ylabel(label)
    save(fig,a,9)
if 10 in selected:
    fig,a=layout(3,2,7.3)
    for i,c in enumerate(CASES):
        center=win.query('case==@c').t_s.item();d=p.query('case==@c and t_s>=@center-3 and t_s<=@center+3')
        series(a[i,0],d.t_s,[d.LoS_s,d.Full_s],['LOS channel','Full channel']);a[i,0].set_ylabel('Normalized power difference, s');a[i,0].set_title(f'{NAMES[i]}: max distortion')
        for j,(key,label) in enumerate([('LoS_Pplus','LOS +'),('LoS_Pminus','LOS -'),('Full_Pplus','Full +'),('Full_Pminus','Full -')]):
            a[i,1].plot(d.t_s,10*np.log10(np.maximum(d[key],1e-300)),color=COL[j//2],ls=['-','--'][j%2],label=label)
        a[i,1].set_ylabel('Relative port power (dB)')
        for ax in a[i]:ax.axvline(center,color='.4',ls=':',lw=.7);ax.set_xlabel('Time (s)')
    h,l=a[0,1].get_legend_handles_labels();a[0,1].legend(h,l,fontsize=9,frameon=False,ncol=2)
    save(fig,a,10)
if 11 in selected:
    fig,a=layout(h=3.3)
    bars(a[0,0],[sens.set_index('case').loc[CASES].median_abs_J_heading],['True-pose SourceFFD']);a[0,0].set_ylabel(r'Median $|H_{s\psi}|$ (rad$^{-1}$)')
    bars(a[0,1],[[gain.query('case==@c and arm==@arm').median_abs_Kpsi_s.item() for c in CASES] for arm in ['BB_ORIG','MB_VAR']],['BB_ORIG','MB_VAR'],colors=[COL[1],COL[2]]);a[0,1].set_ylabel(r'Median $|K_{\psi s}|$ (rad per unit s)');a[0,1].legend(frameon=False)
    save(fig,a,11,False)
if 12 in selected:
    fig,a=layout(3,2,7.3);stages=list(dist.stage.unique())
    for i,c in enumerate(CASES):
        for ax,k,label in zip(a[i],['heading_RMSE_deg','xy_RMSE_cm'],['Heading RMSE (deg)','XY RMSE (cm)']):
            for j,s in enumerate(stages):
                d=dist.query('case==@c and stage==@s').sort_values('rho_mid_m');ax.plot(d.rho_mid_m,d[k],color=COL[j],ls=LS[j],marker=['o','s','^'][j],markersize=3,label=LABELS[j])
            ax.set_xlabel('Horizontal range (m)');ax.set_ylabel(label);ax.set_ylim(bottom=0);ax.set_title(NAMES[i])
    save(fig,a,12)
if 13 in selected:
    fig,a=layout(3,2,7.3)
    for i,c in enumerate(CASES):
        d=p[p.case==c];x=(np.degrees(d.relative_yaw_rad)+180)%360-180
        for j,(key,label) in enumerate([('LoS_s','LOS'),('Full_s','Full')]):a[i,0].scatter(x,d[key],s=3,color=COL[j],alpha=.45,label=label,rasterized=True)
        a[i,0].set_ylabel('Normalized power difference, s');a[i,0].set_title(NAMES[i])
        sc=a[i,1].scatter(x,d.J_heading_abs_per_rad,c=np.abs(d.Full_minus_LoS_s),vmin=0,vmax=1.3,cmap='plasma',s=4,rasterized=True)
        a[i,1].set_ylabel(r'$|H_{s\psi}|$ (rad$^{-1}$)');a[i,1].set_title('Color: absolute Full-LOS difference')
        for ax in a[i]:ax.set_xlabel('Relative yaw (deg)');ax.set_xlim(-180,180);ax.set_xticks([-180,0,180])
    cb=fig.colorbar(sc,ax=a[:,1],location='right',fraction=.035,pad=.04);cb.set_label(r'$|s_{Full}-s_{LOS}|$')
    # Dedicated colorbar placement avoids tight_layout incompatibility.
    cb.remove()
    save(fig,a,13)
