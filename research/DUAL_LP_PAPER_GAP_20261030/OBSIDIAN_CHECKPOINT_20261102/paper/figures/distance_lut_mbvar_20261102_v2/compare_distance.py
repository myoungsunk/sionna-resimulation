"""Compare exactly the 12 MB_VAR condition pairs. No filter execution."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
OUT=Path(__file__).resolve().parent
assert json.loads((OUT/'RESULT_CHECKS.json').read_text(encoding='utf-8'))['new_runs']==12
d=pd.read_csv(OUT/'ALL_SCORES_36.csv');assert len(d)==36
routes=['R2','R4','R5'];biases=['B0','L0','L1','L2'];obs=['LUT_fixed','LUT_distance','SourceFFD']
en={'LUT_fixed':'LUT (pole repair)','LUT_distance':'LUT (+distance)','SourceFFD':'SourceFFD'}
ko={'LUT_fixed':'기존 수정 LUT','LUT_distance':'거리 반영 LUT','SourceFFD':'SourceFFD'}
ren={'R2':'Loop','R4':'Zigzag','R5':'Serpentine'}
rko={'R2':'순환','R4':'지그재그','R5':'사행'}
metrics=['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose']
assert not d.duplicated(['case','bias','observer']).any()
assert np.isfinite(d[metrics].to_numpy()).all()
assert all(len(d[(d.route==r)&(d.observer==o)])==4 for r in routes for o in obs)

def pooled(s):
    w=s.n_score.to_numpy();v=dict(n_conditions=len(s),n_scored_packets=int(w.sum()))
    for key in ['head_rmse','xy_rmse_cm']:v[key]=float(np.sqrt(np.average(s[key]**2,weights=w)))
    for key in ['nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95']:v[key]=float(np.average(s[key],weights=w))
    return v
pool=pd.DataFrame([dict(observer=o,**pooled(d[d.observer==o])) for o in obs]);pool.to_csv(OUT/'POOLED_SCORES_3.csv',index=False)
rp=pd.DataFrame([dict(route=r,observer=o,**pooled(d[(d.observer==o)&(d.route==r)])) for r in routes for o in obs]);rp.to_csv(OUT/'ROUTE_POOLED_SCORES_9.csv',index=False)
wide=d.pivot(index=['case','route','bias'],columns='observer',values=metrics);wide.columns=[f'{a}_{b}' for a,b in wide.columns];wide.reset_index().to_csv(OUT/'THREE_OBSERVERS_12.csv',index=False)

plt.rcParams.update({'font.family':'Times New Roman','font.size':9,'axes.labelsize':9,'axes.titlesize':9,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':9,'axes.linewidth':.6,'pdf.fonttype':42,'ps.fonttype':42})
qa=[]
def export(fig,axes,name,sz):
    fig.canvas.draw();rr=fig.canvas.get_renderer()
    for ax in np.asarray(axes).flat:
      for tx in [ax.xaxis.label,ax.yaxis.label,ax.title,*ax.get_xticklabels(),*ax.get_yticklabels()]:
        if tx.get_visible() and tx.get_text():
          bb=tx.get_window_extent(rr);assert bb.x0>=0 and bb.y0>=0 and bb.x1<=fig.bbox.x1+1 and bb.y1<=fig.bbox.y1+1,(name,tx.get_text())
    fig.savefig(OUT/(name+'.pdf'));fig.savefig(OUT/(name+'.png'),dpi=600);plt.close(fig)
    im=Image.open(OUT/(name+'.png'));px=im.size;im.thumbnail((1350,1350));im.save(OUT/(name+'_preview.png'))
    qa.append(dict(file=name,font='Times New Roman',size_inches=sz,png_pixels=px,dpi=600,pdf_fonttype=42,text_bounds_pass=True))

def panel(ax,metric,route,dof=None):
    for j,o in enumerate(obs):
      sub=d[(d.route==route)&(d.observer==o)].set_index('bias');vals=sub.loc[biases,metric].to_numpy()
      ax.bar(np.arange(4)+(j-1)*.25,vals,.235,label=en[o],color=['#D79A4B','#4D895B','#326B92'][j],hatch=['///','..',''][j],edgecolor='black',linewidth=.4)
    hi=max(float(d[metric].max()),dof or 0)
    ax.set_ylim(0,hi*1.15);ax.set_xticks(range(4),biases);ax.grid(axis='y',color='.86',lw=.4);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
    if dof:ax.axhline(dof,color='.3',ls=':',lw=.8)

for metric,ylabel,name in [('head_rmse','Heading RMSE (deg)','F01_HEADING_IEEE'),('xy_rmse_cm','XY RMSE (cm)','F02_XY_IEEE')]:
    fig,axs=plt.subplots(1,3,figsize=(7.16,2.65));fig.subplots_adjust(left=.085,right=.985,bottom=.20,top=.77,wspace=.24)
    for j,r in enumerate(routes):
      panel(axs[j],metric,r);axs[j].set_title(f'({chr(97+j)}) {ren[r]}');axs[j].set_xlabel('Gyro-bias condition')
    axs[0].set_ylabel(ylabel);fig.legend(*axs[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.995),ncol=3,frameon=False,columnspacing=1.)
    export(fig,axs,name,[7.16,2.65])
fig,axs=plt.subplots(3,3,figsize=(7.16,6.3));fig.subplots_adjust(left=.10,right=.985,bottom=.075,top=.90,wspace=.24,hspace=.38)
for i,(metric,label,dof) in enumerate([('nees_heading','Mean heading NEES (1D)',1),('nees_xy','Mean XY NEES (2D)',2),('nees_pose','Mean pose NEES (3D)',3)]):
  for j,r in enumerate(routes):
    ax=axs[i,j];panel(ax,metric,r,dof);ax.text(.025,.96,f'({chr(97+3*i+j)})',transform=ax.transAxes,va='top')
    if i==0:ax.set_title(ren[r])
    if j==0:ax.set_ylabel(label)
    if i==2:ax.set_xlabel('Gyro-bias condition')
fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.995),ncol=3,frameon=False,columnspacing=1.)
export(fig,axs,'F03_NEES_COMPONENTS_IEEE',[7.16,6.3])
(OUT/'FIGURE_FORMAT_QA.json').write_text(json.dumps(qa,indent=2),encoding='utf-8')

lines=['# 실제 거리 반영 LUT · 기존 수정 LUT · SourceFFD — MB_VAR 비교','',
'질문 ID: `DLP-ANCHORB-DISTANCE-LUT-MBVAR-20261102`. Anchor B, 높이 차 2.2 m, mount 0°, 순환(R2)·지그재그(R4)·사행(R5) × B0/L0/L1/L2(0/0.01/0.05/0.20 °/s). 기존 RF·센서 seed 0를 유지했다. 새 거리 LUT MB_VAR 12개를 실행했으며, 거리 개입을 끈 기준선 12개를 먼저 재현했다. SourceFFD는 앞서 재현 검사를 통과한 저장 결과를 재채점했다.','',
'## 개입과 통제','',
'기존 2° 스칼라 LUT의 각 격자점에 같은 FFD bank로 계산한 `실제 거리 처리 s − 10 m 처리 s`를 더했다. s는 두 수신 포트 전력 차이를 전력 합으로 나눈 무차원 편파 지표다. 수직축에 대한 각도를 θ, 높이 차를 h라고 하면 실제 거리는 h/cos(θ)다. 이번 고정 높이 조건에서만 이 관계를 사용한다. Hann 창·IFFT·첫 경로 tap 선택은 기존 처리를 그대로 썼다. 각도 보간 간격은 2°이며, 기존 1°/2° Cartesian 극점 처리 절차를 수정된 2°/4° 링에도 동일하게 적용했다. 위치·방향 Jacobian은 보정된 격자 함수의 미분과 기하 연쇄법칙으로 계산했다. 거리 관측식과 그 Jacobian은 그대로다.','',
'이는 SourceFFD 함수를 필터에서 직접 호출하는 교체가 아니다. 필요한 격자점만 결정적으로 생성·캐시하고 스칼라 격자를 보간한다. 합성 기하와 bank만으로 격자값을 만들며 RF 관측·참값·성능은 생성 입력으로 쓰지 않는다. 완전한 사전 계산표 배포나 실시간 속도 검증은 수행하지 않았다. 생성된 모든 점은 `DISTANCE_CORRECTION_NODES.npz`로 보존했다.','',
'관측·센서 입력, 상태 [x,y,ψ,gyro bias], 초기 상태·공분산, Q, 고정 MB 보정 평균과 분산표, self gate 임계값을 유지했다. ψ는 heading이다. 이전 posterior의 수평 앵커 거리로 분산을 조회하는 규칙도 유지했다. 경로가 달라져 실현된 R 및 gate 배열은 달라질 수 있으며 `GATE_R_EFFECTS.csv`에 기록했다. 보정 평균을 재추정하거나 관측 잔차 중심을 다시 맞추지 않았다.','',
'## 전체 12조건 합산','',
'평가 표본은 t≥30 s이며 거부된 관측 시점도 포함한다. RMSE는 합산 제곱오차로, NEES는 동일 표본의 평균으로 집계했다. heading·XY·pose NEES의 차원은 각각 1·2·3이다. pose는 x,y,ψ를 포함하고 gyro bias는 제외한다.','',
'| 관측모델 | heading RMSE (°) | XY RMSE (cm) | heading NEES | XY NEES | pose NEES |','|---|---:|---:|---:|---:|---:|']
for _,v in pool.iterrows():lines.append(f"| {ko[v.observer]} | {v.head_rmse:.6f} | {v.xy_rmse_cm:.6f} | {v.nees_heading:.6f} | {v.nees_xy:.6f} | {v.nees_pose:.6f} |")
lines+=['','## 경로별 네 bias 합산','','| 경로 | 관측모델 | heading RMSE (°) | XY RMSE (cm) | heading NEES | XY NEES | pose NEES |','|---|---|---:|---:|---:|---:|---:|']
for _,v in rp.iterrows():lines.append(f"| {rko[v.route]} ({v.route}) | {ko[v.observer]} | {v.head_rmse:.6f} | {v.xy_rmse_cm:.6f} | {v.nees_heading:.6f} | {v.nees_xy:.6f} | {v.nees_pose:.6f} |")
lines+=['','## 조건별 수치','','| 경로 | bias | 관측모델 | heading RMSE (°) | XY RMSE (cm) | heading NEES | XY NEES | pose NEES |','|---|---|---|---:|---:|---:|---:|---:|']
for r in routes:
 for b in biases:
  for o in obs:
   v=d[(d.route==r)&(d.bias==b)&(d.observer==o)].iloc[0]
   lines.append(f'| {rko[r]} | {b} | {ko[o]} | {v.head_rmse:.6f} | {v.xy_rmse_cm:.6f} | {v.nees_heading:.6f} | {v.nees_xy:.6f} | {v.nees_pose:.6f} |')
lines+=['','## 불확실도 확인','','아래 비율은 오차が各차원의 명목 95% 타원체/구간 안에 들어간 시점 비율이다. 단일 seed의 상관된 시계열이므로 독립 표본 기반 일관성 합격률로 해석하지 않는다.','','| 관측모델 | heading 포함 비율 | XY 포함 비율 | pose 포함 비율 |','|---|---:|---:|---:|']
for _,v in pool.iterrows():lines.append(f'| {ko[v.observer]} | {100*v.head_cov95:.2f}% | {100*v.xy_cov95:.2f}% | {100*v.pose_cov95:.2f}% |')
lines+=['','## 그림','',
'heading·XY는 지표당 독립 파일이며 각 경로 패널에 B0/L0/L1/L2를 배치하고 조건별 세 막대로 표시했다. NEES 그림은 heading·XY·pose를 나누었다. 점선 1·2·3은 각 차원의 명목 기준이며 통계적 합격 경계가 아니다. PDF는 벡터, PNG는 600 dpi, Times New Roman 9 pt, 폭 7.16 inch다.','',
'![[F01_HEADING_IEEE.png|1000]]','','![[F02_XY_IEEE.png|1000]]','','![[F03_NEES_COMPONENTS_IEEE.png|1000]]','',
'## 검증·한계','',
'격자 생성에 대한 독립 SourceFFD 수치 대조, 거리 개입을 끈 기준선 12개 상태·공분산·R·gate 재현, 합성 상태와 실제 모든 prior에서 Jacobian 차분 검사, 관측식·HPH·gate·이전 posterior 분산 조회 검사를 수행했다. 입력 파일의 실행 전후 해시 불변도 검사했다. 기준과 실제 오차는 `MATH_GATE.json`, `BASELINE_PARITY_12.csv`, `RESULT_CHECKS.json` 및 `ACTUAL_PRIOR_FD.csv`에 있다. 자체 검산이며 독립 감사나 모델 채택이 아니다.','',
'2° 스칼라 보간과 극점 근사는 계속 남는다. 실제 거리 보정을 포함해도 SourceFFD의 세밀한 전계 보간·첫 경로 분기 및 미분과 완전히 같아지는 것은 아니다. 이 한 장면·seed의 관측모델 개입 결과를 일반 성능 우월성이나 NEES 일관성 통과로 확대하지 않는다. 초기 v1은 UTF8 계약 파일을 기본 cp949로 읽는 준비 단계에서 실패했으며 수치 실행 전이었다. 별도 폴더에 보존했고 v2는 명시적 UTF8만 적용했다.','',
'실행 종료와 관리 프로세스 해제 상태는 `MANAGED_FINISH.json`, 실행 로그는 `REPLAY_stdout.log` 및 `REPLAY_stderr.log`, 출력 해시는 `OUTPUT_HASHES.json`에 보존한다. 원고에는 자동 반영하지 않았다.']
(OUT/'00 거리 반영 LUT MB_VAR 비교.md').write_text('\n'.join(lines).replace('오차が各차원의','오차가 각 차원의'),encoding='utf-8')
print(pool.to_string(index=False));print(rp.to_string(index=False));print('FIGURES_AND_TABLES_COMPLETE')
