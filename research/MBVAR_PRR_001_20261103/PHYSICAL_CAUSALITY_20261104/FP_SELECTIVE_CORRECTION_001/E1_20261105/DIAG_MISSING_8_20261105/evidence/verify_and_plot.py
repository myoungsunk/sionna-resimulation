import pathlib,json,csv,hashlib,datetime
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
W=pathlib.Path(__file__).parent;R=W.parent/'repo'
j=json.loads((W/'DIAGNOSIS.json').read_text())
RF=R/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
with (W/'CIR_WINDOWS.csv').open() as f:windows=list(csv.DictReader(f))
k=np.arange(257);n=np.arange(1028)
kernel=np.exp(2j*np.pi*n[:,None]*k[None,:]/1028)/4
window=.5-.5*np.cos(2*np.pi*k/256)
checks=[]
for c in j['cases']:
 uid=c['uid'];H=np.load(RF/'FULL_RF'/f"H_{c['route']}_aB_m0.npy",mmap_mode='r')[c['pose_id'],:,:,0]
 cir=kernel@(H*window[:,None]);a=np.abs(cir);gp=a.max()
 ws=[r for r in windows if r['uid']==uid]
 err=max(abs(cir[int(r['tap']),rx]-complex(float(r[f'full_rx{rx}_real']),float(r[f'full_rx{rx}_imag']))) for r in ws for rx in (0,1))
 assert err<1e-12
 for l in c['lobes_near_reference']:
  rx=l['rx'];p=l['peak_tap'];lo=l['valley'];h=a[p,rx];v=a[:,rx]
  left=p
  while left>0 and v[left-1]<=h:left-=1
  right=p
  while right+1<1028 and v[right+1]<=h:right+=1
  prominence=h-max(v[left:p+1].min(),v[p:right+1].min())
  assert abs(prominence/gp-l['prominence_over_global'])<1e-10
  edge=lo+int(np.flatnonzero(v[lo:p+1]>=.3*h)[0])
  assert edge==l['computed_edge']
  if l['reason']=='BELOW_PROMINENCE':assert prominence<.06*gp
  if l['reason']=='SUPPORTED_LOBE':
   actual=[t for t in (edge-1,edge,edge+1) if lo<=t<=p and v[t]>=.15*h]
   assert actual==l['candidate_taps']
 checks.append({'uid':uid,'direct_IDFT_max_abs_difference':float(err),'nearby_lobes_verified':len(c['lobes_near_reference']),'passed':True})
(W/'DIRECT_IDFT_CHECK.json').write_text(json.dumps({'method':'Direct complex matrix inverse DFT, not NumPy FFT; raw original H, original Hann and 257/1028 normalization','checks':checks,'E2_started':False,'review_provenance':'SELF_REVIEW'},indent=2)+'\n')
fig,axes=plt.subplots(4,2,figsize=(13,14),layout='constrained')
for ax,c in zip(axes.flat,j['cases']):
 ws=[r for r in windows if r['uid']==c['uid']];ts=np.array([int(r['tap']) for r in ws]);gp=float(ws[0]['global_peak'])
 for rx,color in [(0,'#1674b8'),(1,'#d27612')]:
  ax.plot(ts,[float(r[f'full_rx{rx}'])/gp for r in ws],'.-',c=color,label=f'Full RX{rx}',lw=1.7)
  ax.plot(ts,[float(r[f'los_rx{rx}'])/gp for r in ws],'--',c=color,alpha=.7,label=f'LoS RX{rx}',lw=1.2)
 ax.axvline(c['reference'],color='#bd2031',lw=1.5,label='LoS reference tap')
 taps=[t for t in c['candidate_taps'] if ts.min()<=t<=ts.max()]
 ax.scatter(taps,[-.055]*len(taps),marker='|',s=100,color='#222',label='Recorded candidate taps')
 ax.set(title=f"{c['route']} pose {c['pose_id']} ({c['time_s']:.1f}s) | reference {c['reference']}, original {c['raw']}",xlabel='CIR tap',ylabel='Amplitude / Full global peak',ylim=(-.09,None))
 ax.set_xticks(np.arange(ts.min(),ts.max()+1,2));ax.grid(alpha=.2)
handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside upper center',ncol=3,fontsize=10)
fig.savefig(W/'CIR_8_CASES.png',dpi=160)
fig.savefig(W/'CIR_8_CASES.pdf')
print('DIRECT_IDFT_AND_LOG_CHECK_PASS',len(checks),'max_error',max(x['direct_IDFT_max_abs_difference'] for x in checks))
