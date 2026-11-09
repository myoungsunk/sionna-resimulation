from runtime import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import zipfile,io
from scipy.stats import norm
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
m=model();cases=[('R4',393),('R4',492),('R5',725)];records=[]
fig,axs=plt.subplots(3,2,figsize=(14,11),layout='constrained')
for row,(route,k) in enumerate(cases):
 q=ROOT/(route+'_SCAN.npz')
 if q.exists():a=dict(np.load(q))
 else:
  z=zipfile.ZipFile(ROOT.parent/(route+'.zip'));name=next(n for n in z.namelist() if '/active/B_FROZEN/OFF/' in n and n.endswith('.npz'))
  a=dict(np.load(io.BytesIO(z.read(name))));a['half']=norm.ppf(.975)*np.sqrt(a['Pprior'][:,2,2]);a['target']=(a['nu']+a['h'])[:,1];a['widths']=(norm.ppf(.975)*np.sqrt(a['Rbase'][:,1,1]))[:,None]
 x=a['prior'][k];half=np.degrees(a['half'][k]);target=a['target'][k];width=a['widths'][k,0]
 for col,limit in enumerate([180,max(3,half*2)]):
  d=np.linspace(-limit,limit,1441);states=np.tile(x,(len(d),1));states[:,2]+=np.radians(d);values=[]
  for j in range(0,len(d),64):
   stop_check();values.extend(m.batch(states[j:j+64],SPEC,gradient=False)[0][:,1])
  values=np.array(values);ax=axs[row,col]
  ax.axhspan(target-width,target+width,color='#93c5fd',alpha=.35,label='S 허용폭 100%')
  ax.axhspan(target-width*.25,target+width*.25,color='#2563eb',alpha=.2,label='S 허용폭 25%')
  ax.axvspan(-half,half,color='#f59e0b',alpha=.25,label='gyro prior 95%')
  ax.plot(d,values,color='#111827',lw=1,label='실제 비선형 S 모델');ax.axhline(target,color='#dc2626',lw=1,label='보정 평균을 뺀 B 관측')
  ax.set(xlabel='prior 대비 Heading 차이 (°)',ylabel='S',title=f'{route} · {a["t"][k]:.1f}초 · B OFF prior'+(' / 전체 원주' if col==0 else ' / gyro 주변'))
  ax.grid(alpha=.15)
  if row==0 and col==0:ax.legend(fontsize=8,loc='lower left')
  if col==0:
   np.savez_compressed(ROOT/f'{route}_{k}_CIRCULAR.npz',delta_deg=d,S=values,target=target,width=width,gyro_half_deg=half)
   intervals={}
   for scale in [1,.25]:
    inside=abs(values-target)<=width*scale
    starts=np.flatnonzero(inside&~np.r_[False,inside[:-1]]);ends=np.flatnonzero(inside&~np.r_[inside[1:],False])
    intervals[str(scale)]=[[float(d[i]),float(d[j])] for i,j in zip(starts,ends)]
   records.append(dict(route=route,k=k,t=float(a['t'][k]),prior_heading_deg=float(np.degrees(x[2])),gyro_half_deg=half,S_target=float(target),S_halfwidth=float(width),sampled_heading_intervals_delta_deg=intervals,boundary_resolution_deg=.25,disconnected_intervals_preserved=True))
fig.suptitle('같은 실패 시점의 B OFF 상태: 비선형 S 지지 범위와 gyro 범위\n정답은 범위 구성에 사용하지 않음 · 전체 원주 구간은 0.25° 격자 근사 · 기존 ACTIVE prior와 구별',fontsize=14)
fig.savefig(ROOT/'NONLINEAR_RANGES.png',dpi=160)
(ROOT/'CASE_INTERVALS.json').write_text(json.dumps(records,indent=2))
print('FIGURES_DONE',flush=True)
