import pathlib, json, hashlib, csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

W=pathlib.Path(__file__).parent
R=W.parent/'repo'
O=W/'proposed_overlay'
O.mkdir(exist_ok=True)
j=json.loads((W/'DIAGNOSIS.json').read_text())
logs=json.loads((W/'SOURCE_LOBES.json').read_text())
RF=R/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
k=np.arange(257); n=np.arange(1028)
kernel=np.exp(2j*np.pi*n[:,None]*k[None,:]/1028)/4
window=.5-.5*np.cos(2*np.pi*k/256)
out=[]; arrays=[]
for c in j['cases']:
    path=RF/'FULL_RF'/f"H_{c['route']}_aB_m0.npy"
    rel=path.relative_to(R).as_posix()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==j['verified_hashes'][rel]
    h=np.load(path,mmap_mode='r')[c['pose_id'],:,:,0]
    a=np.abs(kernel@(h*window[:,None])); gp=a.max()
    floor=64*np.finfo(float).eps*gp
    sets={arm:{c['raw']} for arm in ['V0','VA','VB','VAB']}
    supports={arm:{} for arm in sets}
    for l in logs[c['uid']]:
        rx=int(l['rx']);p=int(l['peak_tap']);v=int(l['left_local_valley']);peak=a[p,rx]
        old=l['reason']=='SUPPORTED_LOBE'
        extra=(l['reason']=='BELOW_PROMINENCE' and l['boundary']=='False'
               and peak>=floor and a[v,rx]<.3*peak and peak-a[v,rx]>=.06*gp)
        if not (old or extra): continue
        e=v+int(np.flatnonzero(a[v:p+1,rx]>=.3*peak)[0])
        base={t for t in (e-1,e,e+1) if v<=t<=p and a[t,rx]>=max(floor,.15*peak)}
        wide=base|{t for t in range(e,p+1) if a[t,rx]>=max(floor,.15*peak)}
        if old:
            assert base==set(json.loads(l['candidate_taps_json']))
            assert e==int(l['edge_tap'])
        for arm in sets:
            if old or (extra and arm in ('VB','VAB')):
                ts=wide if arm in ('VA','VAB') else base
                sets[arm]|=ts
                for t in ts:
                    supports[arm].setdefault(t,[]).append({'rx':rx,'peak':p,'edge':e,'support':'original' if old else 'left_rise'})
    assert sets['V0']==set(c['candidate_taps']),c['uid']
    assert sets['V0']<=sets['VAB']
    ref=c['reference']
    row={key:c[key] for key in ('uid','route','pose_id','reference','raw')}
    row['arms']={arm:{'taps':sorted(ts),'count':len(ts),'reference_supported':ref in supports[arm],
                      'overflow':len(ts)>64,'reference_usable':ref in supports[arm] and len(ts)<=64} for arm,ts in sets.items()}
    row['reference_supports']=supports['VAB'].get(ref,[])
    out.append(row);arrays.append(a/gp)

pdf=PdfPages(O/'CIR_candidate_comparison_8.pdf')
for page in range(2):
    fig,axs=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    for ax,idx in zip(axs.flat,range(page*4,page*4+4)):
        c=j['cases'][idx];row=out[idx];a=arrays[idx];ref=c['reference'];ts=np.arange(ref-6,ref+13)
        ax.plot(ts,a[ts,0],'.-',color='#4682b4',alpha=.65,label='실제 CIR RX0')
        ax.plot(ts,a[ts,1],'.-',color='#d38a39',alpha=.8,label='실제 CIR RX1')
        old=set(row['arms']['V0']['taps']);new=set(row['arms']['VAB']['taps'])-old
        for candidates,marker,color,label in [(old,'o','#222222','기존 후보'),(new,'^','#00834b','제안 추가 후보')]:
            taps=sorted(t for t in candidates if ts.min()<=t<=ts.max())
            # Union candidates are marked on both actual RX curves, not attributed to both ports.
            for rx in (0,1):
                ax.scatter(taps,a[taps,rx],marker=marker,s=62,facecolors='none',edgecolors=color,linewidths=1.5,label=label if rx==0 else None,zorder=5)
        ax.axvline(ref,color='#bf2350',ls='--',lw=1.5,label='LoS 참조 위치')
        ax.scatter([ref],[a[ref,1]],marker='*',s=200,c='#bf2350',edgecolors='white',zorder=7)
        arm=row['arms'];which='A 또는 B로 포함' if arm['VA']['reference_supported'] and arm['VB']['reference_supported'] else ('A로 포함' if arm['VA']['reference_supported'] else 'B로 포함')
        ax.set_title(f"{c['route']} · pose {c['pose_id']} | 참조 tap {ref}\n{which} · 전체 후보 {arm['V0']['count']} → {arm['VAB']['count']}개",fontsize=12)
        ax.set_xlabel('CIR tap');ax.set_ylabel('진폭 / 두 RX 전체 최대 진폭')
        ax.set_xticks(np.arange(ts.min(),ts.max()+1,2));ax.grid(alpha=.18)
    handles,labels=axs.flat[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside upper center',ncol=5,fontsize=11)
    fig.savefig(O/f'CIR_candidate_comparison_{page+1}.png',dpi=160)
    pdf.savefig(fig);plt.close(fig)
pdf.close()
receipt={'scope':'8 exposed cases only; diagnostic evaluation of proposed A/B rules; no production edit or E2',
 'role':'AUDITOR_SELF_REVIEW','base_commit':'7707db1d69bc60b2c7cba591bac2508b611c64c9',
 'E2_started':False,'reference_used_only_after_candidate_construction':True,'original_candidate_log_parity':'PASS',
 'cases':out}
(O/'OVERLAY_CHECK.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for row in out:
    print(row['uid'],{arm:(x['count'],x['reference_usable']) for arm,x in row['arms'].items()})
