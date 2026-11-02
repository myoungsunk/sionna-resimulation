"""Tables and IEEE-sized figures from the completed observer-swap run."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter
from matplotlib import font_manager
from PIL import Image
OUT=Path(__file__).resolve().parent
assert json.loads((OUT/'RESULT_CHECKS.json').read_text())['status']=='EXECUTION_AND_SELF_CHECK_COMPLETED'
d=pd.read_csv(OUT/'ALL_SCORES_72.csv');pair=pd.read_csv(OUT/'PAIRED_COMPARISON_36.csv')
assert len(d)==72 and len(pair)==36
stages=['LOS_EKF','MULTIPATH_EKF','PROPOSED_MB_VAR'];routes=['R2','R4','R5'];biases=['B0','L0','L1','L2']
route_en=dict(R2='Loop',R4='Zigzag',R5='Serpentine');route_ko=dict(R2='순환',R4='지그재그',R5='사행')
stage_en=dict(LOS_EKF='LoS EKF',MULTIPATH_EKF='Multipath EKF',PROPOSED_MB_VAR='Multipath MB_VAR')
stage_ko=dict(LOS_EKF='LOS 일반 EKF',MULTIPATH_EKF='다중경로 일반 EKF',PROPOSED_MB_VAR='다중경로 MB_VAR')
plt.rcParams.update({'font.family':'Times New Roman','font.size':9,'axes.labelsize':9,'axes.titlesize':9,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':9,'axes.linewidth':.6,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none'})
qa=[]
for metric,ylabel,filename in [('head_rmse','Heading RMSE (deg)','F01_HEADING_IEEE'),('xy_rmse_cm','XY RMSE (cm)','F02_XY_IEEE'),('nees_pose','Mean pose NEES (3D)','F03_POSE_NEES_IEEE')]:
    fig,axs=plt.subplots(3,3,figsize=(7.16,6.3));fig.subplots_adjust(left=.105,right=.985,bottom=.075,top=.90,wspace=.29,hspace=.37)
    for row,stage in enumerate(stages):
        rowdata=d[d.stage==stage];ymax=float(rowdata[metric].max())
        ymin=float(rowdata[metric].min())
        for col,route in enumerate(routes):
            ax=axs[row,col]
            for j,observer in enumerate(['SourceFFD','LUT']):
                sub=d[(d.stage==stage)&(d.route==route)&(d.observer==observer)].set_index('bias')
                vals=sub.loc[biases,metric].to_numpy()
                if metric=='nees_pose':
                    ax.plot(np.arange(4),vals,label=observer,color=['#2C648C','#B96616'][j],linestyle=['-','--'][j],marker=['o','s'][j],markersize=3.5,linewidth=1.1)
                else:
                    ax.bar(np.arange(4)+(j-.5)*.36,vals,.34,label=observer,color=['#2C648C','#E4A25B'][j],hatch=['','///'][j],edgecolor='black',linewidth=.4)
            if metric=='nees_pose':
                ax.set_yscale('log');ax.axhline(3,color='.3',linestyle=':',linewidth=.75,zorder=0)
                ax.set_ylim(min(ymin,3)*.75,max(ymax,3)*1.35)
                lo,hi=ax.get_ylim()
                ticks=[v for v in [1,2,3,5,10,20,50,100,200] if lo<=v<=hi]
                ax.set_yticks(ticks,[str(v) for v in ticks]);ax.yaxis.set_minor_formatter(NullFormatter())
            else:ax.set_ylim(0,ymax*1.13)
            ax.set_xticks(range(4),biases);ax.grid(axis='y',which='major',linewidth=.4,color='.85');ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
            ax.text(.03,.96,f'({chr(97+row*3+col)})',transform=ax.transAxes,ha='left',va='top',fontsize=8)
            if row==0:ax.set_title(route_en[route],pad=5)
            if col==0:ax.set_ylabel(stage_en[stage]+'\n'+ylabel)
            if row==2:ax.set_xlabel('Gyro-bias condition')
    fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.995),ncol=2,frameon=False)
    fig.savefig(OUT/(filename+'.pdf'));fig.savefig(OUT/(filename+'.png'),dpi=600)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();clipped=[]
    for ax in axs.flat:
        for tx in [ax.xaxis.label,ax.yaxis.label,*ax.get_xticklabels(),*ax.get_yticklabels(),ax.title]:
            if tx.get_text() and tx.get_visible():
                box=tx.get_window_extent(renderer);canvas=fig.bbox
                if box.x0<0 or box.y0<0 or box.x1>canvas.x1+1 or box.y1>canvas.y1+1:clipped.append(tx.get_text())
    assert not clipped,(filename,clipped)
    qa.append(dict(name=filename,size_inches=list(fig.get_size_inches()),png_pixels=list(Image.open(OUT/(filename+'.png')).size),dpi=600,font=font_manager.findfont('Times New Roman'),pdf_fonttype=42,clipped_text=clipped,scales='Shared within stage row; NEES logarithmic' if metric=='nees_pose' else 'Shared within stage row, linear zero baseline'))
    plt.close(fig)
(OUT/'FIGURE_FORMAT_QA.json').write_text(json.dumps(qa,indent=2))

# Pooled scored-point metrics, explicitly weighted by sample count, not average RMSE.
pool=[]
for (stage,observer),s in d.groupby(['stage','observer']):
    w=s.n_score.to_numpy();r=dict(stage=stage,observer=observer,n_conditions=len(s),n_scored_packets=int(w.sum()))
    for k in ['head_rmse','xy_rmse_cm']:r[k]=float(np.sqrt(np.average(s[k]**2,weights=w)))
    for k in ['nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95']:r[k]=float(np.average(s[k],weights=w))
    pool.append(r)
pd.DataFrame(pool).to_csv(OUT/'POOLED_SCORES_6.csv',index=False)
counts=[]
for stage,s in pair.groupby('stage'):
    r=dict(stage=stage,n_conditions=len(s))
    for k in ['head_rmse','xy_rmse_cm','nees_pose']:
        delta=s[k+'_delta_LUT_minus_SourceFFD'];r[k+'_LUT_lower']=int((delta<0).sum());r[k+'_LUT_higher']=int((delta>0).sum())
    counts.append(r)
pd.DataFrame(counts).to_csv(OUT/'CHANGE_COUNTS.csv',index=False)
def table(s):
    lines=['| 경로 | bias | heading °: SourceFFD → LUT | XY cm: SourceFFD → LUT | heading NEES: SourceFFD → LUT | XY NEES: SourceFFD → LUT | pose NEES: SourceFFD → LUT |',
           '|---|---|---:|---:|---:|---:|---:|']
    for route in routes:
        for bias in biases:
            r=s[(s.route==route)&(s.bias==bias)].iloc[0]
            vals=[f'{r[k+"_SourceFFD"]:.4f} → {r[k+"_LUT"]:.4f}' for k in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose']]
            lines.append('| '+route_ko[route]+' | '+bias+' | '+' | '.join(vals)+' |')
    return '\n'.join(lines)
par=pd.read_csv(OUT/'SOURCE_BASELINE_PARITY.csv')
text='''# Anchor B 관측함수만 교체한 재귀 비교 — SourceFFD 대 원 LUT

질문 ID: `DLP-ANCHORB-LUT-OBSERVER-SWAP-20261102`.

## 실행 범위와 통제

Anchor B (10,0,2.65) m, 태그 높이 0.45 m, 장착각 0°. 순환(R2)·지그재그(R4)·사행(R5) 경로 × B0/L0/L1/L2(0/0.01/0.05/0.20 °/s). 기존 3단계에 맞춰 LOS 일반 EKF, 다중경로 일반 EKF, 다중경로 MB_VAR를 각각 계산했다. SourceFFD 기준선 재현 36개를 모두 통과한 뒤 원 LUT 실행 36개를 수행했다.

**개입은 관측함수 h와 Jacobian H의 교체뿐이다.** 원 10 m·2° LUT를 사용했고, 극점 수정 후보는 적용하지 않았다. 센서 입력·seed 0·초기 상태/공분산·4상태·Q·거리 관측 오프셋·RF 관측·gate 규칙·보정 평균·분산표를 유지했다. MB_VAR 보정 평균은 기존 packet별 frozen donor 값을 그대로 사용했으며 LUT에 맞춰 재학습하거나 재중심화하지 않았다.

MB_VAR의 분산은 원 코드대로 이전 posterior의 수평 앵커 거리로 조회한다. 관측함수가 바뀌면 상태 경로도 달라지므로 실제 조회 거리·추가분산·gate 수용 여부는 달라질 수 있다. 규칙을 동일하게 유지한 것이며 SourceFFD의 R 시계열이나 mask를 강제로 복사한 대조는 아니다. 각각 `GATE_AND_VARIANCE_CHANGES.csv`와 LUT trace에 보존했다.

평가는 t≥30 s의 모든 시점이며 관측을 거부한 시점도 포함한다. 경로별 평가 수는 순환 829, 지그재그 592, 사행 1,265개다. heading RMSE는 래핑한 방향 오차, XY RMSE는 2차원 위치 오차의 제곱합 평균 제곱근이다.

## NEES 정의

오차를 e, 대응하는 추정 공분산을 P라 할 때 NEES=eᵀP⁻¹e다. heading NEES는 heading 한 성분(1차원), XY NEES는 [x,y](2차원), pose NEES는 [x,y,heading](3차원)을 사용한다. 표의 값은 평가 시점별 NEES의 평균이며 자이로 bias 성분은 포함하지 않는다. 각각의 차원 기준값은 1/2/3이지만, 단일 seed의 상관된 시간 표본이므로 그 기준값만으로 일관성 통과/실패를 판정하지 않는다. NEES 감소를 오차 개선과 같은 뜻으로 쓰지 않는다. 원 heading/XY 95% 포함률과 추가 pose 포함률도 CSV에 보존했다.

## 12조건을 평가 시점 수로 가중한 전체 비교

아래 집계는 경로별 RMSE를 단순 평균하지 않았다. 각 조건의 평가 제곱오차를 합산해 RMSE를 계산하고 NEES는 평가 시점 수로 가중했다. 네 bias는 같은 장면의 반복 조건이므로 독립 실험 12회나 표본 오차 추정으로 해석하지 않는다.

| 방법 | 관측함수 | heading RMSE (°) | XY RMSE (cm) | heading NEES | XY NEES | pose NEES |
|---|---|---:|---:|---:|---:|---:|
'''
pooldf=pd.DataFrame(pool)
for stage in stages:
    for observer in ['SourceFFD','LUT']:
        r=pooldf[(pooldf.stage==stage)&(pooldf.observer==observer)].iloc[0]
        text+='| '+stage_ko[stage]+' | '+observer+' | '+' | '.join(f'{r[k]:.4f}' for k in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose'])+' |\n'
text+='\n각 값의 조건별 차이는 아래 표와 `PAIRED_COMPARISON_36.csv`에서 확인한다. 양의 delta는 LUT 값이 더 크다는 뜻이며, NEES의 크고 작음을 성능 우열로 자동 판정하지 않는다.\n'
text+='''
## 확인된 차이

- LOS 일반 EKF: 전체 heading RMSE 0.4646→0.6486°, XY RMSE 4.1868→5.9877 cm. heading과 XY가 각각 12조건 중 8조건에서 증가했다. pose NEES는 12조건 모두 증가했다.
- 다중경로 일반 EKF: heading RMSE 1.9928→2.0623°로 증가했고 12조건 모두 같은 방향이었다. XY 전체 집계는 18.6716→17.6640 cm로 감소했으나, 조건별로는 5조건 감소·7조건 증가했다. 경로별 표본 수와 오차 크기를 합산한 결과이므로 전체 집계와 조건 수의 방향이 다를 수 있다.
- 다중경로 MB_VAR: heading RMSE 0.9592→0.9611°로 비슷하지만 XY는 6.0725→6.3316 cm, pose NEES는 4.7178→16.4929로 증가했다. heading은 7조건 감소·5조건 증가, XY는 5조건 감소·7조건 증가였다. pose NEES는 12조건 모두 증가했다.
- 사행 경로 MB_VAR: 네 bias 모두 LUT의 heading RMSE가 작아졌지만 pose NEES는 B0 2.4436→35.6191, L0 2.4334→4.9051, L1 2.3970→44.4656, L2 2.3623→19.3280으로 증가했다. heading RMSE 감소만으로 필터의 공분산이 적절해졌다고 해석할 수 없다.
- MB_VAR의 전체 pose 95% 포함률은 84.24%→71.94%였다. 이번 결과에서 LUT 교체가 전반적인 공분산 신뢰성을 개선했다는 근거는 없다. 이 포함률은 상관된 시간 표본의 기술 통계이며 독립 반복 실험에 대한 검정 결과가 아니다.

따라서 원 LUT로 교체하면 모든 성능이 동일해지거나 일괄 개선된다고 볼 수 없다. MB_VAR는 두 관측함수 모두에서 다중경로 일반 EKF보다 전체 heading·XY RMSE가 작았지만, LUT 교체 후 공분산 지표의 변화는 별도로 다뤄야 한다. 차이의 원인을 극점·거리 의존성·보정값 불일치 중 하나로 이번 실행만으로 분리하지 않는다.
'''
for stage in stages:text+='\n## '+stage_ko[stage]+' — 전체 12조건\n\n'+table(pair[pair.stage==stage])+'\n'
text+='\n## IEEE 형식 그림\n\n'
for name,caption in [('F01_HEADING_IEEE','그림 1. 관측함수에 따른 heading RMSE. 각 행은 LOS 일반 EKF·다중경로 일반 EKF·다중경로 MB_VAR이며, 각 열은 순환·지그재그·사행 경로다. x축 B0/L0/L1/L2는 자이로 bias 0/0.01/0.05/0.20 °/s다. 같은 행의 세 경로는 동일 y축 범위를 사용한다.'),('F02_XY_IEEE','그림 2. 같은 조건의 XY RMSE. 행·열·x축 의미는 그림 1과 같다.'),('F03_POSE_NEES_IEEE','그림 3. [x,y,heading] 3차원 평균 pose NEES. y축은 로그 척도이고 점선은 차원 기준값 3이다. 신뢰구간이나 통계 검정의 통과 경계가 아니다. 단일 seed·시간 상관 때문에 실험 간 불확실도 오차막대는 제공하지 않는다.')]:
    text+=f'![[03_Research/EKF/2026-11-01 논문 초안/figures/lut_observer_swap_20261102/{name}.png|1000]]\n\n{caption}\n\n'
text+='''## 검증·해석 범위

기존 `diag_mbvar.run`과 센서 생성기·채점기를 그대로 재사용했다. SourceFFD 36개 경로에서 상태 X·공분산 P·실제 R·수용 mask를 기준 기록과 대조했다. NEES의 선형계 풀이와 Cholesky 백색화 계산을 대조했고 모든 공분산의 양의 정부호성을 확인했다. 원 코드와 입력 데이터의 실행 전후 SHA256이 일치했다. 이 검사는 동일 에이전트의 자체 검사이며 독립 감사가 아니다.

관측함수 교체 후 frozen 평균·분산표가 LUT에 최적화되어 있다는 보장은 없다. 이번 질문은 그 재학습 효과를 포함하지 않는다. 결과는 기존 한 장면·한 seed의 회고적 관측함수 대조에 한정한다. 새 환경, 실측, 제안 방법의 채택 또는 공분산 일관성 확보로 확대하지 않는다. 기존 원고와 기존 결과는 수정하거나 덮어쓰지 않았다.

계약·입력 해시: `CONTRACT.json`. 실행 및 검사: `RESULT_CHECKS.json`, `SOURCE_BASELINE_PARITY.csv`. 전체 수치: `ALL_SCORES_72.csv`, `PAIRED_COMPARISON_36.csv`. 상태·공분산·입력·평균·R·혁신·gate: 각 LUT NPZ. 전 시점 오차와 NEES: `PACKET_ERRORS_AND_NEES.csv.gz`. 관리 실행의 종료 상태는 `MANAGED_FINISH.json`에 기록한다.
'''
text+=f'\nSourceFFD 재현 최대 차이: X {par.X_max_abs.max():.3e}, P {par.P_max_abs.max():.3e}, R {par.R_max_abs.max():.3e}, gate 불일치 {int(par.gate_mismatch.sum())}건.\n'
(OUT/'00 결과 비교.md').write_text(text,encoding='utf-8')
print(pooldf.to_string(index=False));print(pd.DataFrame(counts).to_string(index=False))
hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in OUT.iterdir() if f.is_file() and f.name!='OUTPUT_HASHES.json'}
(OUT/'OUTPUT_HASHES.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
