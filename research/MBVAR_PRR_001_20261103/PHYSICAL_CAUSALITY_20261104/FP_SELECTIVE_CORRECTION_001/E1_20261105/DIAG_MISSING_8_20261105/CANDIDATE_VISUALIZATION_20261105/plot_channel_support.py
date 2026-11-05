import pathlib,json,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
W=pathlib.Path(__file__).parent; R=W.parent/'repo'; O=W/'channel_support';O.mkdir(exist_ok=True)
j=json.loads((W/'DIAGNOSIS.json').read_text());logs=json.loads((W/'SOURCE_LOBES.json').read_text())
prior=json.loads((W/'proposed_overlay/OVERLAY_CHECK.json').read_text())
RF=R/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
k=np.arange(257);n=np.arange(1028);kernel=np.exp(2j*np.pi*n[:,None]*k[None,:]/1028)/4
window=.5-.5*np.cos(2*np.pi*k/256)
records=[];pdf=PdfPages(O/'RX_separated_all_8.pdf')
for ci,c in enumerate(j['cases']):
 path=RF/'FULL_RF'/f"H_{c['route']}_aB_m0.npy"
 assert hashlib.sha256(path.read_bytes()).hexdigest()==j['verified_hashes'][path.relative_to(R).as_posix()]
 a=np.abs(kernel@(np.load(path,mmap_mode='r')[c['pose_id'],:,:,0]*window[:,None]));gp=a.max();floor=64*np.finfo(float).eps*gp
 old=[set(),set()];new=[set(),set()];ls=[[],[]]
 for l in logs[c['uid']]:
  rx=int(l['rx']);p=int(l['peak_tap']);v=int(l['left_local_valley']);h=a[p,rx]
  was=l['reason']=='SUPPORTED_LOBE'
  extra=l['reason']=='BELOW_PROMINENCE' and l['boundary']=='False' and h>=floor and a[v,rx]<.3*h and h-a[v,rx]>=.06*gp
  d={'peak':p,'valley':v,'old_reason':l['reason'],'old':was,'extra':bool(extra),'height':float(h/gp),'edge':None,'taps':[]}
  if was or extra:
   e=v+int(np.flatnonzero(a[v:p+1,rx]>=.3*h)[0]);d['edge']=e
   base={t for t in (e-1,e,e+1) if v<=t<=p and a[t,rx]>=max(floor,.15*h)}
   wide=base|{t for t in range(e,p+1) if a[t,rx]>=max(floor,.15*h)}
   if was:
    assert base==set(json.loads(l['candidate_taps_json']));old[rx]|=base
   new[rx]|=wide;d['taps']=sorted(wide)
  ls[rx].append(d)
 assert old[0]|old[1]|{c['raw']}==set(c['candidate_taps'])
 assert new[0]|new[1]|{c['raw']}==set(prior['cases'][ci]['arms']['VAB']['taps'])
 fig,axs=plt.subplots(1,2,figsize=(16,6),layout='constrained');ref=c['reference'];ts=np.arange(ref-6,ref+13)
 for rx,ax in enumerate(axs):
  ax.plot(ts,a[ts,rx]/gp,'.-',lw=1.6,color=['#417eb0','#cf852f'][rx],label=f'실제 CIR RX{rx}')
  for s,m,col,lab in [(old[rx],'o','#222','기존 채널 지지'),(new[rx]-old[rx],'^','#00834b','제안 추가 지지')]:
   t=sorted(s&set(ts));ax.scatter(t,a[t,rx]/gp,marker=m,s=85,facecolors='none',edgecolors=col,linewidths=1.8,zorder=5,label=lab)
  ax.axvline(ref,c='#bd2350',ls='--',lw=1.3,label='참조 위치')
  ax.set_ylim(-.07,1.56);ax.set_xlim(ts[0]-.4,ts[-1]+.4)
  visible=[l for l in ls[rx] if ts[0]<=l['peak']<=ts[-1] and l['height']>=.05]
  annotations=[]
  for l in visible:
   p=l['peak']
   if l['taps']:
    start=l['taps'][0];e=l['edge']
    if ts[0]<=start<=ts[-1]:
     t=start-1
     why='15% 진폭 미달' if t==e-1 and a[t,rx]<max(floor,.15*a[p,rx]) else '에지-1보다 앞'
     annotations.append((start,f"{start}부터 후보\n직전: {why}"))
    stop=p+1
    why='다른 봉우리 지지로 유지' if stop in new[rx] else '이후 하강/평탄부 제외'
    annotations.append((p,f"봉우리 {p}에서 종료\n{why}"))
    if l['extra']:
     ax.text(p,l['height']+.035,'B로 추가 허용',fontsize=8,color='#00834b',ha='center')
    elif p not in old[rx]:
     ax.text(p,l['height']+.035,'A로 봉우리까지 확장',fontsize=8,color='#00834b',ha='center')
    if l['old']:
     old_end=max(t for t in old[rx] if max(l['valley'],e-1)<=t<=min(p,e+1))
     ax.annotate(f'기존 끝 {old_end}\n에지±1 / 봉우리 제한',xy=(old_end,a[old_end,rx]/gp),xytext=(0,-35),textcoords='offset points',fontsize=8,ha='center',color='#333',arrowprops={'arrowstyle':'-','color':'#555'})
   else:
    why={'BELOW_PROMINENCE':'돌출도·왼쪽 상승 조건 미달','UNRESOLVED_LOCAL_LEADING_EDGE':'30% 에지 분리 불가','BELOW_ABSOLUTE_SUPPORT':'절대 진폭 미달','BOUNDARY_PEAK_NOT_CANDIDATE':'경계 봉우리 제외'}.get(l['old_reason'],l['old_reason'])
    if l['old_reason']=='BELOW_PROMINENCE' and a[l['valley'],rx]>=.3*a[p,rx]:
     why='돌출도 미달 + 30% 에지 분리 불가'
    annotations.append((p,f'봉우리 {p} 제외\n{why}'))
  # Space labels evenly in a dedicated band above the waveform.
  annotations.sort()
  for q,(t,txt) in enumerate(annotations):
   xp=(q+.5)/max(1,len(annotations));yp=.94 if q%2==0 else .79
   ax.annotate(txt,xy=(t,a[t,rx]/gp),xytext=(xp,yp),textcoords='axes fraction',ha='center',va='top',fontsize=8,
    bbox={'boxstyle':'round,pad=.3','fc':'white','ec':'#aaa','alpha':.95},arrowprops={'arrowstyle':'->','color':'#888','lw':.8})
  ok='포함' if ref in new[rx] else '미포함'
  ax.set_title(f"{c['route']} · pose {c['pose_id']} · RX{rx} | 참조 {ref}: {ok}",fontsize=13)
  ax.set_xlabel('CIR tap (참조 주변 확대)');ax.set_ylabel('진폭 / 두 RX 전체 최대 진폭')
  ax.set_xticks(np.arange(ts[0],ts[-1]+1,2));ax.grid(alpha=.16)
  ax.legend(loc='lower right',fontsize=8)
 fig.savefig(O/f"{c['route']}_{c['pose_id']}_RX_separated.png",dpi=160);pdf.savefig(fig);plt.close(fig)
 records.append({'uid':c['uid'],'reference':ref,'ports':[{'rx':rx,'old_supported_taps':sorted(old[rx]),'proposed_supported_taps':sorted(new[rx]),'reference_supported':ref in new[rx],'lobes':ls[rx]} for rx in (0,1)]})
pdf.close()
(O/'CHANNEL_SUPPORT_CHECK.json').write_text(json.dumps({'role':'AUDITOR_SELF_REVIEW','scope':'8-case diagnostic visualization only','E2_started':False,'raw_fallback_not_attributed_to_ports':True,'old_log_parity':'PASS','prior_proposed_union_parity':'PASS','cases':records},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: original per-port logs and proposed union parity, 8 cases; E2 not run')
