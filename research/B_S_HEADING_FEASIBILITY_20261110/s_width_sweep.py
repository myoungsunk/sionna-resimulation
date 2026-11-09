"""Offline frozen B OFF priors; local-linear interval intersection diagnostic.
No gate/variance changes are applied to the stored EKF or future states.
"""
import pathlib,zipfile,io,json,csv
import numpy as np
from scipy.stats import norm,chi2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=pathlib.Path(__file__).parent;Z=norm.ppf(.975)
wrap=lambda x:(x+np.pi)%(2*np.pi)-np.pi
def writecsv(name,rows):
 with (p/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
blocks=[];parts=[];evidence=[]
for r in ['R2','R4','R5']:
 z=zipfile.ZipFile(p/(r+'.zip'));name=next(n for n in z.namelist() if '/active/B_FROZEN/OFF/' in n and n.endswith('.npz'))
 a=dict(np.load(io.BytesIO(z.read(name))));o=dict(np.load(p/(r+'_B0_Full_10__online.npz')));ev=dict(np.load(p/(r+'_B0_Full_10__evaluator.npz')))
 assert np.array_equal(a['t'],o['t']) and np.array_equal(a['t'],ev['t']) and np.array_equal(a['pose_id'],ev['pose_id'])
 base=o['R'][:,1,1];total=a['Rbase'][:,1,1];extra=total-base
 prev=np.vstack([o['x0'],a['x'][:-1]]);rho=np.linalg.norm(prev[:,:2]-[10,0],axis=1);sig=np.interp(rho,[0,1.5,3,6,10],[.011,.020,.050,.120,.240])
 assert np.max(abs(extra-sig**2))<1e-12
 H=a['H'];P=a['Pprior'];R=a['Rbase'];nu=a['nu'];xp=a['prior'];n=len(xp)
 K=np.linalg.solve(H@P@H.transpose(0,2,1)+R,H@P).transpose(0,2,1)
 full=xp+np.einsum('nij,nj->ni',K,nu);full[:,2]=wrap(full[:,2]);assert np.max(abs(full[a['mask']]-a['x'][a['mask']]))<1e-10
 hr=H[:,0:1];kr=np.linalg.solve(hr@P@hr.transpose(0,2,1)+R[:,0:1,0:1],hr@P).transpose(0,2,1)
 onlyr=xp+np.einsum('nij,nj->ni',kr,nu[:,0:1]);onlyr[:,2]=wrap(onlyr[:,2])
 # Labels use truth AFTER all candidate updates and interval ingredients exist.
 truth=ev['truth'];eh=lambda x:np.degrees(wrap(x[:,2]-truth[:,2]))**2
 ex=lambda x:np.sum((x[:,:2]-truth[:,:2])**2,axis=1)*1e4
 dh=eh(full)-eh(onlyr);dx=ex(full)-ex(onlyr);df=eh(full)-eh(xp)
 # RF quality: LoS-only polarization at the SAME B tap, preserving tap definition.
 nf=o['Hrf'].shape[1];win=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
 cir=np.fft.ifft(o['Hrf']*win[None,:,None],n=4*nf,axis=1)*nf
 amp=abs(cir);tap=np.argmax(amp>=.3*amp.max(axis=1)[:,None,:],axis=1).min(axis=1)
 def sval(c):
  pow=abs(c[np.arange(n),tap])**2;return (pow[:,0]-pow[:,1])/pow.sum(axis=1)
 s=sval(cir);assert np.max(abs(s-(a['nu']+a['h']+a['mu'])[:,1]))<1e-9
 clean=np.fft.ifft(ev['clean_H']*win[None,:,None],n=4*nf,axis=1)*nf;ds=abs(s-sval(clean))
 gyro=Z*np.sqrt(P[:,2,2]);j=abs(H[:,1,2]);xy=np.sqrt(np.maximum(0,chi2.ppf(.95,2)*np.einsum('ni,nij,nj->n',H[:,1,:2],P[:,:2,:2],H[:,1,:2])))
 blocks.append(dict(route=r,n=n,base=base,total=total,extra=extra,absnu=abs(nu[:,1]),g=j*gyro,xy=xy,mask=a['mask'],dh=dh,dx=dx,df=df,ds=ds))
 parts.append(dict(route=r,n=n,base_variance_median=float(np.median(base)),extra_variance_median=float(np.median(extra)),total_variance_median=float(np.median(total)),total_sigma_median=float(np.median(np.sqrt(total))),extra_share_sum=float(extra.sum()/total.sum()),extra_share_median=float(np.median(extra/total)),base_unique=np.unique(base).tolist()))
 for k in range(n):evidence.append(dict(route=r,k=k,t=float(a['t'][k]),accepted=int(a['mask'][k]),base_var=base[k],extra_var=extra[k],total_var=total[k],abs_nu_s=abs(nu[k,1]),gyro_allowance_s=j[k]*gyro[k],xy_allowance_s=xy[k],S_increment_heading_se=dh[k],S_increment_xy_se=dx[k],B_vs_skip_heading_se=df[k],abs_full_clean_s_at_B=ds[k]))
policies=[('current',1,1,1),('no_extra',1,0,1),('no_base',0,1,1),('width75',1,1,.75),('width50',1,1,.5),('width25',1,1,.25),('width10',1,1,.1),('width0',1,1,0)]
results=[]
for route in ['ALL','R2','R4','R5']:
 bb=blocks if route=='ALL' else [b for b in blocks if b['route']==route]
 cat=lambda key:np.concatenate([b[key] for b in bb]);mask=cat('mask');dh=cat('dh');dx=cat('dx');df=cat('df');ds=cat('ds')
 good=mask&(dh< -1e-10);bad=mask&(dh>1e-10)
 for xy_on in [False,True]:
  for name,wb,we,scale in policies:
   bound=cat('g')+scale*Z*np.sqrt(wb*cat('base')+we*cat('extra'))+(cat('xy') if xy_on else 0)
   reject=cat('absnu')>bound+1e-12
   rec=dict(route=route,xy=xy_on,policy=name,accepted=int(mask.sum()),S_helpful=int(good.sum()),S_harmful=int(bad.sum()),S_neutral=int((mask&~good&~bad).sum()),rejected=int((mask&reject).sum()),helpful_protected=int((good&~reject).sum()),helpful_protection=float((good&~reject).sum()/good.sum()),harmful_rejected=int((bad&reject).sum()),harmful_rejection=float((bad&reject).sum()/bad.sum()),helpful_rejected=int((good&reject).sum()),harm_saved_h_se=float(dh[bad&reject].sum()),benefit_lost_h_se=float(-dh[good&reject].sum()),one_step_net_h_se=float(-dh[mask&reject].sum()),one_step_net_xy_se=float(-dx[mask&reject].sum()),B_helpful_protected=int((mask&(df< -1e-10)&~reject).sum()),B_helpful_total=int((mask&(df< -1e-10)).sum()))
   for threshold,label in [(.01,'01'),(.03,'03'),(.05,'05')]:
    normal=mask&(ds<=threshold);rec['clean_'+label+'_total']=int(normal.sum());rec['clean_'+label+'_protected']=int((normal&~reject).sum())
   results.append(rec)
writecsv('s_width_sweep_rows.csv',evidence);writecsv('s_width_sweep_summary.csv',results)
(p/'s_variance_components.json').write_text(json.dumps(parts,indent=2))
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
axs[0].bar([b['route'] for b in blocks],[1-v['extra_share_sum'] for v in parts],label='저장 기본 Rss',color='#2563eb')
axs[0].bar([b['route'] for b in blocks],[v['extra_share_sum'] for v in parts],bottom=[1-v['extra_share_sum'] for v in parts],label='거리 의존 추가 σb²',color='#d97706');axs[0].set(ylabel='전체 분산 합에서의 비중',title='S 분산의 실제 두 구성 항');axs[0].legend()
for xy_on,color in [(False,'#2563eb'),(True,'#d97706')]:
 rr=[r for r in results if r['route']=='ALL' and r['xy']==xy_on and (r['policy']=='current' or r['policy'].startswith('width'))]
 axs[1].plot([100*(1-r['helpful_protection']) for r in rr],[100*r['harmful_rejection'] for r in rr],'-o',color=color,label='위치 범위 포함' if xy_on else '위치 고정')
 for r in rr:axs[1].annotate(r['policy'].replace('width','').replace('current','100'),(100*(1-r['helpful_protection']),100*r['harmful_rejection']),xytext=(4,4),textcoords='offset points',fontsize=9)
axs[1].set(xlabel='유익한 S 갱신을 잘못 거르는 비율 (%)',ylabel='해로운 S 갱신을 거르는 비율 (%)',title='허용폭 축소: 숫자는 S 잡음 허용폭의 %');axs[1].grid(alpha=.2);axs[1].legend()
fig.suptitle('그냥 B OFF prior 고정 | 전체 3,136행 중 기존 게이트 수용 행 평가\n정답은 사후 분류에만 사용 · 국소 선형 교집합 검사 · 새 재귀 실행 없음',fontsize=14)
fig.savefig(p/'s_width_tradeoff.png',dpi=160)
print('COMPONENTS',json.dumps(parts));print('POOLED',json.dumps([r for r in results if r['route']=='ALL']))
