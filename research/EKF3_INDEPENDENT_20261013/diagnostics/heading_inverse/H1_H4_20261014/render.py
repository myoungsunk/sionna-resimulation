from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'OPT/FULL';OUT=ROOT/'ANALYSIS'
sys.path.insert(0,str(ROOT/'OPT'))
from run_heading import original_lut,INPUT,RS
from inverse_core import curve,inverse,wrap

def main():
 d=pd.read_csv(DATA/'H12_RF.csv.gz')
 fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
 for ch,color in [('los','#2a7f62'),('full','#cc6234')]:
  a=d[d.channel==ch];v=np.sort(a.oracle_error_deg.dropna());axs[0].plot(v,np.arange(1,len(v)+1)/len(v),label=ch.upper(),color=color)
  v=np.sort(a.band_width_deg);axs[1].plot(v,np.arange(1,len(v)+1)/len(v),label=ch.upper(),color=color)
 axs[0].set(xlim=(0,180),ylim=(0,1),xlabel='Truth-nearest exact-root error (deg)',ylabel='Conditional empirical CDF',title='Oracle diagnostic only; not usable accuracy')
 axs[1].set(xlim=(0,360),ylim=(0,1),xlabel='Total nominal angle-band width (deg)',title='Band from frozen R_s, all components included')
 for ax in axs:ax.grid(alpha=.2);ax.legend()
 fig.savefig(OUT/'H12_INVERSE.png',dpi=160);plt.close(fig)
 # A post-hoc illustrative observation, explicitly not a selection/tuning rule.
 cid='R5_aB_m0';k=1183
 # Load the exact p0 structure returned by the original cache-verified helper.
 from run_heading import input_gate
 p0=input_gate();case=next(c for c in p0['cases'] if c['id']==cid);lut=original_lut(p0)
 f=np.load(INPUT/(cid+'_los.npz'));truth=f['truth'][k];z=float(f['s'][k]);x,y,_,_=curve(lut,case,truth[:2]);iv=inverse(x,y,z,np.sqrt(RS),truth=truth[2])
 angles=np.linspace(-np.pi,np.pi,3601);values=np.interp((angles-x[0])%(2*np.pi)+x[0],x,y)
 fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
 for ax in axs:
  ax.plot(np.degrees(angles),values,color='#306ca3',label='Frozen LoS LUT')
  ax.axhline(z,color='#cc6234',label='Observed LoS s')
  ax.axhspan(z-1.96*np.sqrt(RS),z+1.96*np.sqrt(RS),alpha=.13,color='#cc6234',label='Nominal R_s band')
  ax.axvline(float(np.degrees(wrap(truth[2]))),color='#2a7f62',linestyle='--',label='True heading (offline)')
  ax.scatter(iv['roots_deg'],[z]*iv['root_count'],s=35,color='black',zorder=4,label='Exact roots')
  ax.set(xlabel='Heading (deg)',ylabel='s');ax.grid(alpha=.2)
 axs[0].set(xlim=(-180,180),title='Small residual can remove the nearby exact root')
 th=float(np.degrees(wrap(truth[2])));axs[1].set(xlim=(th-15,th+15),ylim=(z-.006,z+.015),title='Zoom around true heading')
 axs[0].legend(fontsize=8);fig.savefig(OUT/'EXACT_ROOT_DISAPPEARANCE.png',dpi=160);plt.close(fig)
 (OUT/'ILLUSTRATION_CASE.json').write_text(json.dumps(dict(case=cid,sample_index=k,true_heading_deg=th,s_obs=z,roots_deg=iv['roots_deg'],oracle_error_deg=iv['oracle_error_deg'],nominal_band_truth=iv['band_truth'],selection='POST_HOC_ILLUSTRATION_ONLY_NOT_GATE_OR_MODEL_SELECTION'),indent=2))
 a=pd.read_csv(OUT/'H4_POOLED.csv');a=a[(a.arm=='A')&(a.range_model=='B_OLD')]
 fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
 names={'M0':'M0','RF_HUBER_ONLY':'Huber','RF_CAUCHY':'Cauchy'};stages=['NOISE','L0','L1','L2']
 for ax,ch in zip(axs,['los','full']):
  for model,label in names.items():
   g=a[(a.channel==ch)&(a.model==model)].set_index('stage').loc[stages]
   ax.plot(stages,g.heading95_pct,marker='o',label=label)
  ax.axhline(95,color='gray',linestyle='--',label='Nominal 95%')
  ax.set(ylim=(0,101),title=f'{ch.upper()}: heading-only A',ylabel='Actual heading interval coverage (%)',xlabel='Frozen motion condition');ax.grid(alpha=.2);ax.legend()
 fig.savefig(OUT/'H4_HEADING_COVERAGE.png',dpi=160);plt.close(fig)
 print('Rendered 3 figures and one illustration receipt')
if __name__=='__main__':main()
