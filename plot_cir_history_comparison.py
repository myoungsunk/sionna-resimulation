import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import sys,json,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.fp_sc.followup.numerics import cir_from_spectrum
from qclean_uwb.fp_sc.followup.contracts import STEP_M,Policy
from qclean_uwb.fp_sc.followup.input_sensitivity import raw_score_grid
B=ROOT/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001'
S=B/'PM_INPUT_SENSITIVITY_R1_20261106/RUN_001'
OUT=B/'PM_INPUT_SENSITIVITY_R1_20261106/CIR_HISTORY_COMPARISON_20261106'
OUT.mkdir(exist_ok=True)
manifest=json.loads((B/'PRIOR_INTEGRITY_R1_20261105/PREPARATION_001/MANIFEST_PREP_ONLY.json').read_text())
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
records=[]
for route,k in [('R2',148),('R4',61),('R5',107)]:
    case=route+'_B0_Full_10'
    paths=[S/(case+'_ONLINE.npz'),S/(case+'_EVALUATOR.npz'),ROOT/manifest['cases'][case]['online_npz']]
    a,e,inp=[np.load(p,allow_pickle=False) for p in paths]
    ids=list(a['scenario_ids']); s0=ids.index('NOMINAL'); s1=ids.index('M_FP_2.0'); j=int(a['history_j'][s0,k])
    raw=int(a['raw_tap'][k]); prev=int(a['raw_tap'][j]); bounds=[]
    assert raw==e['reference_tap'][k] and prev==e['reference_tap'][j]
    assert a['flags'][s0,k,2]==0 and a['flags'][s1,k,2]==1
    assert int(a['history_j'][s1,k])==j
    np.testing.assert_allclose(a['p_bounds'][s0,k],a['p_bounds'][s1,k])
    np.testing.assert_allclose((a['m_bounds'][s1,k]-a['m_bounds'][s0,k])/STEP_M,[2,2])
    for s in [s0,s1]:
        scores,flags,status=raw_score_grid(raw,float(a['c_score'][k]),a['p_bounds'][s,k][None,:],a['m_bounds'][s,k][None,:],Policy())
        np.testing.assert_allclose(scores[0],a['scores'][s,k],equal_nan=True)
        np.testing.assert_array_equal(flags[0],a['flags'][s,k])
        bounds.append({'P':(a['p_bounds'][s,k]/STEP_M).tolist(),'M':(a['m_bounds'][s,k]/STEP_M).tolist(),'scores_C_P_M_PM':scores[0].tolist()})
    h=cir_from_spectrum(inp['Hrf'][[j,k]])
    amp=np.abs(h);amp=amp/amp.max(axis=(1,2),keepdims=True)
    allx=[raw,prev,prev+2]+sum([b['P']+b['M'] for b in bounds],[])
    lo=max(0,int(min(allx))-6);hi=min(1027,int(max(allx))+10)
    fig,axs=plt.subplots(3,2,figsize=(14,11),gridspec_kw={'height_ratios':[1,1.45,.5]})
    fig.subplots_adjust(top=.88,bottom=.10,hspace=.65,wspace=.20)
    fig.suptitle(f'{route}: 과거 FP 기록만 +2 tap 변경 — 현재 정상 FP의 M 오탐\n실제 CIR 동일 · 현재 raw = 참조 tap {raw} · 고정 임계값 2.0',fontsize=19,y=.98)
    for col,s in enumerate([s0,s1]):
        for row in [0,1]:
            ax=axs[row,col]
            ax.plot(np.arange(1028),amp[row,:,0],color='#334e68',label='RX0',lw=1.8)
            ax.plot(np.arange(1028),amp[row,:,1],color='#9c6a28',label='RX1',ls='--',lw=1.5)
            tap=prev if row==0 else raw
            ax.axvline(tap,color='#17805c',lw=2,label=f'실제 raw = 참조 ({tap})')
            ax.set_xlim(lo,hi);ax.set_ylim(0,1.48 if row else 1.2)
            ax.set_ylabel('정규화 |CIR|');ax.set_xlabel('tap (확대 구간)');ax.grid(alpha=.15)
            if row==0:
                ax.set_title(('무개입' if col==0 else '과거 FP 기록 +2 tap')+f' | 직전 파형 j={j}',fontsize=14)
                if col:
                    ax.axvline(prev+2,color='#bd3b35',ls=':',lw=2,label=f'주입한 이력 ({prev+2})')
                ax.legend(loc='upper right',fontsize=9)
            else:
                for typ,y,color in [('P',1.12,'#3978b7'),('M',1.31,'#c06432')]:
                    l,r=bounds[col][typ]
                    ax.fill_between([l,r],y-.035,y+.035,color=color,alpha=.65)
                    ax.text((l+r)/2,y+.06,f'{typ} [{l:.2f}, {r:.2f}]',ha='center',fontsize=10,color=color)
                score=float(a['scores'][s,k,2]);outcome='정상 판정' if col==0 else '정상 FP를 오탐'
                ax.set_title(f'현재 파형 k={k} | M 점수 {score:.3f} → {outcome}',color='#17805c' if col==0 else '#bd3b35',fontsize=13)
                ax.text(.98,.61,f"C {a['scores'][s,k,0]:.3f}\nP {a['scores'][s,k,1]:.3f}\nM {score:.3f}\nPM {a['scores'][s,k,3]:.3f}",transform=ax.transAxes,ha='right',bbox=dict(facecolor='white',alpha=.9,edgecolor='#ddd'),fontsize=10)
        ax=axs[2,col]
        ax.plot(np.arange(1028),amp[1,:,0],color='#334e68',lw=.8)
        ax.plot(np.arange(1028),amp[1,:,1],color='#9c6a28',lw=.8,ls='--')
        ax.axvspan(lo,hi,color='#3978b7',alpha=.18)
        ax.set_xlim(0,1027);ax.set_ylim(0,1.05);ax.set_xlabel('현재 CIR 전체 tap (파란 영역: 위 확대 범위)');ax.set_ylabel('|CIR|')
    fig.text(.05,.025,'P·M은 저장된 반사실 민감도 진단의 지원구간이며, 보정된 신뢰구간이 아닙니다.\n실제 VALID·선택·FP 교체 없음. GT 참조는 그림 평가에만 사용. E1-02·E2 미실행.',fontsize=11)
    fig.savefig(OUT/(route+'_CIR.png'),dpi=160);plt.close(fig)
    records.append({'case':case,'k':k,'j':j,'raw_reference_tap':raw,'past_raw_reference_tap':prev,'injected_history_tap':prev+2,'time':float(a['t'][k]),'history_age_s':float(a['history_age'][s0,k]),'nominal':bounds[0],'injected':bounds[1],'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})
(OUT/'EVIDENCE.json').write_text(json.dumps({'scope':'saved counterfactual diagnosis visualization; not E1-02 or E2','selection':'earliest per route with current and previous raw==reference, nominal M flag 0 and M_FP_2.0 flag 1','checks':'raw/reference equality, same P, M shift exactly 2 taps, all four scores and flags reproduced from saved intervals','step_m':STEP_M,'examples':records},ensure_ascii=False,indent=2),encoding='utf-8')
print(OUT)
print(json.dumps([{k:r[k] for k in ['case','k','j','nominal','injected']} for r in records],ensure_ascii=False))
