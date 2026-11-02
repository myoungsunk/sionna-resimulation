"""Three-observer IEEE figures and exact comparison tables from frozen outputs."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter
from PIL import Image
OUT=Path(__file__).resolve().parent;OLD=OUT.parent/'lut_observer_swap_20261102'
assert json.loads((OUT/'RESULT_CHECKS.json').read_text())['status']=='EXECUTION_AND_SELF_CHECK_COMPLETED'
d=pd.read_csv(OUT/'ALL_SCORES_108.csv');assert len(d)==108
stages=['LOS_EKF','MULTIPATH_EKF','PROPOSED_MB_VAR'];routes=['R2','R4','R5'];biases=['B0','L0','L1','L2'];observers=['LUT_original','LUT_fixed','SourceFFD']
stage_en=dict(LOS_EKF='LoS EKF',MULTIPATH_EKF='Multipath EKF',PROPOSED_MB_VAR='Multipath MB_VAR')
stage_ko=dict(LOS_EKF='LOS 일반 EKF',MULTIPATH_EKF='다중경로 일반 EKF',PROPOSED_MB_VAR='다중경로 MB_VAR')
route_en=dict(R2='Loop',R4='Zigzag',R5='Serpentine');route_ko=dict(R2='순환',R4='지그재그',R5='사행')
ob_en=dict(LUT_original='LUT (original)',LUT_fixed='LUT (pole repair)',SourceFFD='SourceFFD')
ob_ko=dict(LUT_original='수정 전 LUT',LUT_fixed='수정 후 LUT',SourceFFD='SourceFFD')
plt.rcParams.update({'font.family':'Times New Roman','font.size':9,'axes.labelsize':9,'axes.titlesize':9,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':9,'axes.linewidth':.6,'pdf.fonttype':42,'ps.fonttype':42})
qa=[]
for metric,ylabel,filename in [('head_rmse','Heading RMSE (deg)','F01_HEADING_IEEE'),('xy_rmse_cm','XY RMSE (cm)','F02_XY_IEEE'),('nees_pose','Mean pose NEES (3D)','F03_POSE_NEES_IEEE')]:
    fig,axs=plt.subplots(3,3,figsize=(7.16,6.3));fig.subplots_adjust(left=.105,right=.985,bottom=.075,top=.90,wspace=.27,hspace=.37)
    for row,stage in enumerate(stages):
        rd=d[d.stage==stage];lo=float(rd[metric].min());hi=float(rd[metric].max())
        for col,route in enumerate(routes):
            ax=axs[row,col]
            for j,ob in enumerate(observers):
                sub=d[(d.stage==stage)&(d.route==route)&(d.observer==ob)].set_index('bias');vals=sub.loc[biases,metric].to_numpy()
                color=['#DB9248','#4C8656','#2C648C'][j]
                if metric=='nees_pose':ax.plot(range(4),vals,label=ob_en[ob],color=color,ls=['--','-.','-'][j],marker=['s','^','o'][j],markersize=3.5,lw=1)
                else:ax.bar(np.arange(4)+(j-1)*.25,vals,.235,label=ob_en[ob],color=color,hatch=['///','..',''][j],edgecolor='black',linewidth=.4)
            if metric=='nees_pose':
                ax.set_yscale('log');ax.set_ylim(min(lo,3)*.75,max(hi,3)*1.35);ax.axhline(3,color='.4',ls=':',lw=.7)
                low,high=ax.get_ylim();ticks=[v for v in [1,2,3,5,10,20,50,100,200] if low<=v<=high]
                ax.set_yticks(ticks,[str(v) for v in ticks]);ax.yaxis.set_minor_formatter(NullFormatter())
            else:ax.set_ylim(0,hi*1.14)
            ax.set_xticks(range(4),biases);ax.grid(axis='y',lw=.4,color='.86');ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
            ax.text(.03,.96,f'({chr(97+row*3+col)})',transform=ax.transAxes,va='top',fontsize=8)
            if row==0:ax.set_title(route_en[route],pad=5)
            if col==0:ax.set_ylabel(stage_en[stage]+'\n'+ylabel)
            if row==2:ax.set_xlabel('Gyro-bias condition')
    fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.995),ncol=3,frameon=False,columnspacing=1.)
    fig.canvas.draw();rr=fig.canvas.get_renderer()
    for ax in axs.flat:
        for tx in [ax.xaxis.label,ax.yaxis.label,ax.title,*ax.get_xticklabels(),*ax.get_yticklabels()]:
            if tx.get_visible() and tx.get_text():
                bb=tx.get_window_extent(rr);assert bb.x0>=0 and bb.y0>=0 and bb.x1<=fig.bbox.x1+1 and bb.y1<=fig.bbox.y1+1,(filename,tx.get_text())
    fig.savefig(OUT/(filename+'.pdf'));fig.savefig(OUT/(filename+'.png'),dpi=600);plt.close(fig)
    im=Image.open(OUT/(filename+'.png'));size=im.size;im.thumbnail((1200,1200));im.save(OUT/(filename+'_preview.png'))
    qa.append(dict(filename=filename,size_inches=[7.16,6.3],png_pixels=size,dpi=600,font='Times New Roman',pdf_fonttype=42,text_bounds_pass=True))

def pooled(s):
    w=s.n_score.to_numpy();r=dict(n_conditions=len(s),n_scored_packets=int(w.sum()))
    for key in ['head_rmse','xy_rmse_cm']:r[key]=float(np.sqrt(np.average(s[key]**2,weights=w)))
    for key in ['nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95']:r[key]=float(np.average(s[key],weights=w))
    return r
pool=pd.DataFrame([dict(stage=st,observer=ob,**pooled(d[(d.stage==st)&(d.observer==ob)])) for st in stages for ob in observers]);pool.to_csv(OUT/'POOLED_SCORES_9.csv',index=False)
r5pool=pd.DataFrame([dict(stage=st,observer=ob,**pooled(d[(d.stage==st)&(d.observer==ob)&(d.route=='R5')])) for st in stages for ob in observers]);r5pool.to_csv(OUT/'R5_POOLED_SCORES_9.csv',index=False)
counts=[]
for st in stages:
    p=d[d.stage==st].pivot(index=['case','bias'],columns='observer',values=['head_rmse','xy_rmse_cm','nees_pose'])
    r=dict(stage=st)
    for key in ['head_rmse','xy_rmse_cm','nees_pose']:
        delta=p[(key,'LUT_fixed')]-p[(key,'LUT_original')];r[key+'_lower']=int((delta<-1e-12).sum());r[key+'_equal']=int((abs(delta)<=1e-12).sum());r[key+'_higher']=int((delta>1e-12).sum())
    counts.append(r)
pd.DataFrame(counts).to_csv(OUT/'FIX_VS_ORIGINAL_CHANGE_COUNTS.csv',index=False)

text='''# LUT 극점 수정 전·후와 SourceFFD 비교

질문 ID: `DLP-ANCHORB-LUT-POLE-FIX-20261102`. Anchor B=(10,0,2.65)m, 태그 높이 0.45m, mount 0°. 순환(R2)·지그재그(R4)·사행(R5) × B0/L0/L1/L2(0/0.01/0.05/0.20 °/s), 단일 장면·seed 0. 새 실행은 수정 후 LUT 36개다. 수정 전 LUT 36개를 먼저 재실행해 상태·공분산·적용 R·gate를 원 기록과 대조했다. SourceFFD는 앞서 재현 검사를 통과한 36개 원 기록을 재채점하고 입력·코드 해시 일치를 확인해 사용했다.

## 수정 내용과 유지 조건

수정은 관측함수의 편파 s와 그 상태 Jacobian에만 적용했다. 기존 scalar LUT의 2°·4° 링을 사용해 heading별 Cartesian 2차 다항식을 구했다. 이때 좌표는 앵커에 대한 수평 변위 u,v를 높이 차 h·tan(2°)로 나눈 qx,qy다. heading은 기존 2° 간격으로 주기 선형 보간한다. θ≤1°에서는 이 다항식을 쓰고, 1–2°에서는 정상 2–4° 셀을 아래로 연장한 함수와 5차 smoothstep으로 연결한다. θ는 수직축에서의 각도다. θ≥2°에서는 기존 함수·Jacobian을 그대로 호출한다. 연결 가중치의 미분까지 Jacobian에 포함한다.

원 LUT 파일·거리 관측행·10m 기반 모델·RF 관측·센서 입력·초기 상태/공분산·4상태·Q·평균 보정값·분산표·gate 규칙을 유지했다. SourceFFD 전계나 예측값, RF·참값·성과 지표를 극점 근사 학습에 사용하지 않았다. MB_VAR의 보정 평균은 기존 packet별 frozen donor이며 재학습하지 않았다. 분산은 기존대로 이전 posterior의 앵커 수평 거리에서 조회한다. 추정 상태가 바뀌면 실제 R와 gate mask는 달라질 수 있지만 규칙은 동일하다.

첫 구현은 오염된 0–2° 원 구간과 혼합해 경계 Jacobian 검사에서 실패했다. `../lut_pole_fix_20261102`에 실패 계약과 결과를 보존했다. 필터 실행 전에 중단했으며 성능 수치는 생성하지 않았다. 현재 구현은 정상 2–4° 셀 연장값으로 연결한다. 사전 허용오차를 완화하지 않고 통과한 뒤 실행했다. 사후 성능 튜닝은 하지 않았다.

## 지표와 평가 구간

t≥30s의 모든 시점을 사용하며 관측 거부 시점도 포함한다. 조건별 평가 수는 순환 829, 지그재그 592, 사행 1,265개다. heading RMSE는 래핑한 각도 오차, XY RMSE는 2차원 위치 오차의 제곱합 평균 제곱근이다. 표의 NEES는 오차 e와 대응 공분산 P에 대해 eᵀP⁻¹e를 시점별로 계산한 뒤 평균한 값이다. heading/XY/pose NEES는 각각 ψ / [x,y] / [x,y,ψ]를 사용하며 bias 상태는 제외한다. 내부 각도 단위는 rad, 표시는 °다. ψ는 heading이다. pose NEES는 위치–heading 교차 공분산을 포함한다. 단일 seed의 상관된 시간 표본이므로 NEES 차원 기준값 1/2/3만으로 일관성 통과를 판정하지 않는다.

## 전체 12조건 집계

각 조건의 평가 제곱오차를 합쳐 RMSE를 구하고 NEES는 평가 시점 수로 가중했다. 조건별 RMSE를 단순 평균한 값이 아니다.

| 구성 | 관측함수 | heading RMSE (°) | XY RMSE (cm) | heading NEES | XY NEES | pose NEES | pose 95% 포함률 |
|---|---|---:|---:|---:|---:|---:|---:|
'''
for _,r in pool.iterrows():text+='| '+stage_ko[r.stage]+' | '+ob_ko[r.observer]+' | '+' | '.join(f'{r[k]:.4f}' for k in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose'])+f' | {r.pose_cov95*100:.2f}% |\n'
text+='\n## 사행 경로에서의 수정 효과\n\n'
for st in stages:
    q=r5pool[r5pool.stage==st].set_index('observer')
    text+='- '+stage_ko[st]+': 수정 전 → 수정 후 → SourceFFD 순서로 '
    text+='; '.join(label+' '+ ' → '.join(f'{q.loc[ob,key]:.4f}' for ob in observers) for key,label in [('head_rmse','heading RMSE (°)'),('xy_rmse_cm','XY RMSE (cm)'),('nees_pose','pose NEES')])+'.\n'
text+='\n## 전체 조건별 수치\n\n각 칸은 **수정 전 LUT / 수정 후 LUT / SourceFFD** 순서다. NEES가 작아진 것만으로 공분산 일관성이 확보됐다고 해석하지 않는다.\n'
for st in stages:
    text+='\n### '+stage_ko[st]+'\n\n| 경로 | bias | heading RMSE ° | XY RMSE cm | heading NEES | XY NEES | pose NEES |\n|---|---|---:|---:|---:|---:|---:|\n'
    for rt in routes:
      for b in biases:
        q=d[(d.stage==st)&(d.route==rt)&(d.bias==b)].set_index('observer')
        text+='| '+route_ko[rt]+' | '+b+' | '+' | '.join(' / '.join(f'{q.loc[ob,key]:.4f}' for ob in observers) for key in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose'])+' |\n'
text+='\n## IEEE 그림\n\n각 그림의 행은 LOS 일반 EKF·다중경로 일반 EKF·다중경로 MB_VAR이고 열은 순환·지그재그·사행이다. x축은 B0/L0/L1/L2다. 같은 행의 y축 범위는 경로 간 동일하다. NEES는 로그 축이며 점선 3은 pose 차원 기준값으로, 통계적 통과 경계가 아니다.\n\n'
for fn,cap in [('F01_HEADING_IEEE','Heading RMSE'),('F02_XY_IEEE','XY RMSE'),('F03_POSE_NEES_IEEE','Pose NEES')]:text+=f'![[03_Research/EKF/2026-11-01 논문 초안/figures/{OUT.name}/{fn}.png|1000]]\n\n{cap}. PDF 및 600 dpi PNG, 폭 7.16 inch, Times New Roman.\n\n'
pc=json.loads((OUT/'PRECHECK_RESULTS.json').read_text());rc=json.loads((OUT/'RESULT_CHECKS.json').read_text());usage=pd.read_csv(OUT/'GATE_VARIANCE_AND_CAP_USAGE.csv')
text+='## 검증과 해석 범위\n\n'
text+=f'사전 중앙 차분 {pc["fd_samples"]}개에서 최대 미분 차이 {pc["fd_max_abs"]:.3e}, 실제 수정 구간 prior의 차분 {rc["actual_cap_fd_count"]}개에서 최대 차이 {rc["actual_cap_fd_max_abs"]:.3e}. θ≥2° 함수·Jacobian 차이는 정확히 0이며, 실제 수정 구간을 방문하지 않은 실행은 원 LUT 상태·공분산과 정확히 같다. 정확한 수직축에서 접근 방향별 값의 범위는 0이며 수평 거리 1μm에서 최대 범위 {pc["pole_1um_max_range"]:.3e}다. 1°/2° 경계의 양쪽 함수·미분 검사도 통과했다. heading LUT 절점에서의 기존 구간별 선형 보간 미분 경계는 남는다.\n\n'
text+='실제 수정 prior 수 합계: '+', '.join(f'{rt} {int(usage[usage.case.str.startswith(rt)].n_modified_prior.sum())}' for rt in routes)+'. gate·분산 변경 수는 `GATE_VARIANCE_AND_CAP_USAGE.csv`에 보존했다. 수정에 따른 재귀 경로의 간접 변화는 수정 구간 밖에서도 남을 수 있다.\n\n'
text+='모든 공분산의 양의 정부호, NEES 선형계/Cholesky 대조, 이전 posterior 분산 조회, 저장 HPH 및 gate를 검사했다. 원 입력과 소스 해시는 실행 전후 일치했다. 자체 검사이며 독립 감사가 아니다. 비교는 기존 한 장면·seed 0의 사후 수정 검증이다. θ≥2°의 기존 LUT 보간·고정 거리 차이는 유지되므로 SourceFFD와 완전한 동등성을 주장하지 않는다. 새로운 환경, 최적 근사, 공분산 보정의 일반적 성공 또는 원고 채택으로 확대하지 않는다. 원본 LUT·결과·원고를 덮어쓰지 않았다.\n\n'
text+='계약 `CONTRACT.json`; 검사 `PRECHECK_RESULTS.json`, `RESULT_CHECKS.json`; 전체 108행 `ALL_SCORES_108.csv`; 조건별 3종 대조 `THREE_OBSERVERS_36.csv`; 새 상태·공분산·J·입력·혁신·R·gate는 각 `LUT_fixed.npz`; 극점 계수 `CARTESIAN_CAP_COEFFICIENTS.npz`. 실행 관리 종료는 `MANAGED_FINISH.json`.\n'
(OUT/'00 수정 전후 비교.md').write_text(text,encoding='utf-8');(OUT/'FIGURE_FORMAT_QA.json').write_text(json.dumps(qa,indent=2),encoding='utf-8')
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='OUTPUT_HASHES.json'}
(OUT/'OUTPUT_HASHES.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
print('POOLED_ALL_12');print(pool.to_string(index=False));print('R5_ONLY');print(r5pool.to_string(index=False));print(pd.DataFrame(counts).to_string(index=False))
