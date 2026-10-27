"""Render fixed-scope figures and Korean report from validated output tables."""
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent;F=R/'figures';F.mkdir(exist_ok=True)
plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.22,'figure.dpi':125,'savefig.dpi':155})
CASES=['R2_aA_m45','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0'];BIAS=['B0','L2'];colors=['#334155','#ea580c','#0891b2']
s=pd.read_csv(R/'ALL_METRICS.csv');al=pd.read_csv(R/'M3PRE_ALIGNMENT.csv');rp=pd.read_csv(R/'M2PRE_PACKETS.csv.gz');ps=pd.read_csv(R/'ALL_PASS_METRICS.csv');act=pd.read_csv(R/'ACTIVATION.csv')
def save(fig,name):fig.savefig(F/name,bbox_inches='tight');plt.close(fig)
# All cases, both biases, common scales within row; all 9 windows shown.
fig,ax=plt.subplots(2,5,figsize=(20,7),sharex=True,sharey='row',layout='constrained')
for col,c in enumerate(CASES):
    for bias,ls in [('B0','-'),('L2','--')]:
        d=al[(al.case==c)&(al.bias==bias)&(al.arm=='MB')&(al.dof==2)&(al.pass_id==1)].sort_values(['T_pre','T_post']);x=np.arange(len(d));labels=[f'{a}/{b}' for a,b in zip(d.T_pre,d.T_post)]
        ax[0,col].plot(x,abs(d.et_filter_end_cm),ls,color=colors[0],alpha=.8,label='Before '+bias);ax[0,col].plot(x,abs(d.et_aligned_end_cm),ls,color=colors[1],marker='o',ms=3,label='Aligned '+bias)
        ax[1,col].plot(x,d.sigma_dt_cm,ls,marker='o',ms=3,color=colors[2],label=bias)
    ax[0,col].set_title(c);ax[1,col].axhline(3,color='crimson',ls=':');ax[1,col].set_xticks(x,labels,rotation=60);ax[1,col].set_xlabel('Pre / post window (s)');ax[1,col].set_ylim(bottom=0);ax[0,col].set_ylim(bottom=0)
ax[0,0].set_ylabel('First-pass end |e_t| (cm)');ax[1,0].set_ylabel('Conditional tangent sigma (cm)');ax[0,0].legend(fontsize=8);ax[1,0].legend(fontsize=8);fig.suptitle('M3-pre: translation-only alignment (first pass; B0 solid / L2 dashed)');save(fig,'F1_M3_alignment.png')
fig,axes=plt.subplots(2,5,figsize=(19,7),sharey=True,layout='constrained')
for i,b in enumerate(BIAS):
 for j,c in enumerate(CASES):
    a=axes[i,j]
    for arm,shift,color in [('BB',-.17,colors[0]),('MB',.17,colors[1])]:
        for gi,g in enumerate(['near','mid','far']):
            v=rp[(rp.case==c)&(rp.bias==b)&(rp.arm==arm)&(rp['T']==10)&(rp.grp==g)&rp.valid].ratio.to_numpy()
            if len(v)>=30:
                q=np.quantile(v,[.1,.25,.5,.75,.9]);a.vlines(gi+shift,q[0],q[-1],color=color);a.vlines(gi+shift,q[1],q[-2],color=color,lw=5);a.plot(gi+shift,q[2],'o',color=color,ms=4,label=arm if gi==0 else None)
            else:a.text(gi+shift,.9,'NA',transform=a.get_xaxis_transform(),ha='center',fontsize=8,color=color)
    a.set_xlim(-.5,2.5);a.set_yscale('log');a.set_xticks(range(3),['<1.5','1.5–4','>=4']);a.set_title(c+' '+b);a.axhline(1,color='gray',ls=':');a.set_xlabel('GT horizontal distance (m)')
axes[0,0].legend();axes[0,0].set_ylabel('|Accumulated XY update on fixed tangent| / sigma');axes[1,0].set_ylabel('Dimensionless ratio');fig.suptitle('M2-pre T=10 s: median, interquartile bar, p10–p90 whisker (t >= 30 s)');save(fig,'F2_M2_consistency.png')
for method,variants,fname in [('M1',['M1-0','M1-a','M1-b','M1-c','M1-d','M1-e'],'F3_M1_scores.png'),('M2',['M2-0','M2-1','M2-2','M2-3'],'F5_M2_scores.png')]:
 fig,axes=plt.subplots(3,5,figsize=(19,10),sharex=True,sharey='row',layout='constrained')
 for col,c in enumerate(CASES):
    for bias,ls,colr in [('B0','-',colors[0]),('L2','--',colors[1])]:
        d=s[(s.case==c)&(s.bias==bias)&(s.arm=='MB')&(s.method==method)].set_index('variant').loc[variants]
        for row,(key,scale) in enumerate([('heading_rmse_deg',1),('range_rmse_cm',1),('xy_rmse_m',100)]):axes[row,col].plot(range(len(d)),d[key]*scale,ls,marker='o',color=colr,label=bias)
    axes[0,col].set_title(c)
    for row in range(3):axes[row,col].set_ylim(bottom=0)
    axes[2,col].set_xticks(range(len(variants)),[v.split('-')[1] for v in variants]);axes[2,col].set_xlabel('Variant (0 = OFF)')
 for row,lab in enumerate(['MB heading RMSE (deg)','MB anchor-range RMSE (cm)','MB XY RMSE (cm)']):axes[row,0].set_ylabel(lab)
 for row,(key,scale) in enumerate([('heading_rmse_deg',1),('range_rmse_cm',1),('xy_rmse_m',100)]):axes[row,0].set_ylim(0,float(s[(s.method==method)&(s.arm=='MB')][key].max())*scale*1.08)
 axes[0,0].legend();fig.suptitle(method+' absolute MB performance, t >= 30 s; common y-scale per metric');save(fig,fname)
# Examples fixed before plotting: a, k=1, B0; retain complete multi-pass record.
manifest=json.loads(Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2/research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text());cm={c['id']:c for c in manifest['cases']};passes=pd.read_csv(R.parent/'pass_rs_azimuth/P2_PASSES_GT.csv')
fig,axes=plt.subplots(3,2,figsize=(15,9),sharex='col',layout='constrained')
for col,c in enumerate(['R4_aB_m0','R5_aA_m0']):
 for stage,name,label,color in [('M1_OFF','M1-0_MB','OFF',colors[0]),('M1_SWEEP','M1-a_MB','M1-a',colors[1]),('M2_SWEEP','M2-1_MB','M2 k=1',colors[2])]:
    z=dict(np.load(R/stage/f'{c}_B0.npz'));j=list(z['names']).index(name);t=z['t_s'];gt=z['truth_scoring_only'];xy=z['x'][:,j,:2];rad=gt[:,:2]-np.array(cm[c]['anchor'])[:2];d=np.linalg.norm(rad,axis=1);ut=np.column_stack([-rad[:,1],rad[:,0]])/d[:,None];et=np.einsum('ni,ni->n',ut,xy-gt[:,:2])*100;psi=np.rad2deg((z['x'][:,j,2]-gt[:,2]+np.pi)%(2*np.pi)-np.pi)
    if label=='OFF':axes[0,col].plot(t,d,color=colors[0]);axes[0,col].axhline(1.5,ls=':',color='gray')
    axes[1,col].plot(t,et,label=label,color=color,lw=1.2);axes[2,col].plot(t,psi,color=color,lw=1.2)
 for p in passes[(passes.case==c)&(passes.bias=='B0')].itertuples():
    for row in range(3):axes[row,col].axvspan(p.start_s,p.end_s,color='orange',alpha=.12)
 for row in range(3):axes[row,col].axvline(30,color='gray',ls=':')
 axes[0,col].set_title(c+' B0 / MB');axes[2,col].set_xlabel('Time (s)');axes[1,col].legend(fontsize=9)
axes[0,0].set_ylabel('GT horizontal distance (m)');axes[1,0].set_ylabel('Signed tangent error (cm)');axes[2,0].set_ylabel('Signed heading error (deg)');fig.suptitle('Fixed examples: full record; shaded GT pass intervals; scoring starts at 30 s');save(fig,'F4_pass_timeseries.png')
# Tables and narrative, retaining paired conditions rather than pooled results.
def table(df):
    d=df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):d[c]=d[c].map(lambda v:'NA' if pd.isna(v) else f'{v:.4f}')
    return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in d.itertuples(index=False,name=None))
md=['# 앵커 통과 구간의 접선 오차 완화: 세 방법 실행 결과','', '> **결론: 현재 고정 기준에서는 채택 가능한 방법이 없습니다.** M3-pre는 No-Go로 통합을 실행하지 않았고, M2-pre는 Go였지만 실제 M2 replay는 No-Go였습니다. M1도 모든 강도에서 No-Go입니다.','', '## 1. 요약','', '| 방법 | 사전검사 | 실제 실행 | 채택 판정 |\n|---|---|---|---|\n| M1 접선 range gain 축소 | 별도 gate 없음 | OFF + a–e, 10조건 × BB/MB | No-Go: 모든 변형에서 주 case 성공 0/3 |\n| M2 누적 접선 갱신 제한 | Go; T=10초 선택 | OFF + k=1,2,3, 10조건 × BB/MB | No-Go: 모든 k에서 주 case 성공 0/3 |\n| M3 구간 정렬 | No-Go; 2D 정렬 360행, 3D 진단 360행 | fixed-lag 통합 미실행 | 공통 창에서 주 case 2/3 + R5 유지 조건 미충족 |','',table(pd.read_csv(R/'METHOD_DECISIONS.csv')),'','기술적 실행 성공과 채택 판정을 구분합니다. B0/L2는 같은 RF의 쌍이며 독립 표본 두 개로 세지 않았습니다. 주 분석은 R2_aA_m45, R4_aA_m0, R4_aB_m0의 세 case 그룹입니다. R4의 두 앵커 조건을 독립 route 두 개로 일반화하지 않습니다.','', '## 2. 실행과 검산','', '- 기준 브랜치: `research/ds-x1-x2-results-20261026`, 기준 commit `a6315bbbca54aa9c7d8ae4ab26183d8d94b51ec9`.\n- 원문은 `PROTOCOL.md`, 승인한 수정 및 수치 정의는 `DEFINITIONS.md`, M2 개입은 `M2_REPLAY_DEFINITIONS.md`에 고정했습니다.\n- M1/M2 OFF 모두 E1의 전체 상태·공분산·h/H/K·혁신·평균·R·mask를 허용차 1e-10 안에서 재현했습니다.\n- 저장 trace 독립 검산 3,840개 통과: gain 투영, 상태 갱신, Joseph 공분산, 대칭/PSD, 거리 switch, rolling 정보량·누적량·gamma 및 점수 재현. 입력 해시 255개를 실행 후 재확인했습니다.\n- M1/M2 helper는 exit 0으로 자연 종료했으며 process/supervisor/job 부재와 소유 참조 해제를 확인했습니다.\n- 최초 pre 계산은 마지막 집계에서 pandas `.T` 참조 오류로 exit 1이었습니다. 원본 코드와 `PRE_FAILURE.json`을 보존하고, `finalize_pre.py`로 저장된 결과만 다시 집계·검산했습니다. 정렬 최적화나 필터를 재실행하지 않았습니다.\n- 모든 변경은 새 `azimuth_methods/` 안에 저장합니다. 기존 산출물, Q, 학습 결과, 편파 평균/R 및 A_B는 보존했습니다. M1-e만 사전 정의대로 근거리 Rrr을 4배로 합니다.','', '## 3. M3-pre: 고정 궤적의 평행이동 정렬','', '회전을 고정한 2D 평행이동만 Go 판정에 사용했습니다. 단일 앵커 주위 회전은 range를 보존하므로 3DOF는 미식별 진단이며, 유사역행렬로 유한 접선 불확실성을 만들지 않았습니다.','', '![M3 정렬](figures/F1_M3_alignment.png)','', '각 패널은 첫 통과의 9개 창 조합입니다. 전·후 오차는 창 끝 시점이 달라지므로 창 사이의 직접 개선 비교보다 동일 창의 전후 비교를 읽어야 합니다. R4_aB는 일부 창에서 오차를 크게 줄이지만 조건부 σ가 3 cm를 넘습니다. 다른 주 case에서도 오차 감소와 불확실성 조건을 동시에 만족하지 못했습니다.','']
a=al[(al.arm=='MB')&(al.dof==2)&(al.pass_id==1)].groupby(['case','bias']).agg(best_reduction=('reduction','max'),min_sigma_cm=('sigma_dt_cm','min')).reset_index();md += [table(a),'',table(pd.read_csv(R/'M3PRE_DECISIONS.csv')),'','R5 결과는 모든 통과·B0/L2를 포함한 원표에서 보존합니다. 9개 공통 창 조합 중 어느 것도 R5의 12개 pass×bias 셀 모두를 만족하지 못했습니다. 따라서 fixed-lag 통합 gate를 닫았습니다. **이는 이 고정 궤적 평행이동 진단의 실패이며 모든 윈도우 추정 방법의 불가능성을 뜻하지 않습니다.**','', '## 4. M2-pre와 M2 replay','', '순간 range 접선 감도는 0이므로 창 끝 추정 접선축을 세계좌표에 고정하고 2D 정보행렬 역행렬을 투영했습니다. 이 값은 동역학과 시간상관을 생략한 상수 평행이동 surrogate입니다. 엄밀한 혁신 검정통계로 해석하지 않습니다.','', '![누적량 분포](figures/F2_M2_consistency.png)','',table(pd.read_csv(R/'M2PRE_DECISIONS.csv')),'','T=10초에서 R2_aA_m45와 R4_aB_m0의 MB near 중앙값이 mid·far의 두 배를 넘었습니다(B0/L2 모두). R4_aA는 t≥30초 near 표본 부족으로 NA입니다. 신호의 **상대 대비가 크다는 것과 |S|/σ가 k를 실제로 넘는 것은 다릅니다.**','', '![M2 성능](figures/F5_M2_scores.png)','', 'M2는 range와 편파 gain의 XY 접선 성분을 함께 제한하고 ψ/b_g 행은 유지했습니다. 이전 누적량이 이미 경계 밖인 경우 되돌리는 갱신을 허용합니다. 창과 축이 움직이므로 어느 γ∈[0,1]로도 경계 안에 넣을 수 없는 packet도 있습니다. 이때는 |S|를 최소화하는 끝값을 사용했으며 `infeasible_accepted`로 기록했습니다. 이 방법은 모든 시점에 경계를 강제하는 hard constraint가 아닙니다.','']
md += [table(act[(act.method=='M2')&(act.variant=='M2-1')&(act.arm=='MB')][['case','bias','n_accepted','active_accepted','active_scoring','infeasible_accepted']]),'', 'k=2·3은 여러 조건에서 전혀 작동하지 않아 OFF와 같습니다. k=1은 R2 MB Heading을 일부 개선하지만 주 기준을 만족하지 못하고 R4_aA를 악화시켰습니다. R4_aA의 k=1 개입은 전부 30초 이전이며, 그 영향이 이후 평가 구간에 남습니다. R5_aA에서도 scoring 중 새 개입은 0회입니다. 사전 대비만으로 재귀 필터에서의 효과를 보장할 수 없었습니다.','', '## 5. M1: range gain의 접선 성분 축소','', 'a: λ=0.5,D=1.5m; b: λ=0.25,D=1.5m; c: λ=0,D=1.5m; d: λ=0.5,D=2.5m; e: D=1.5m에서 Rrr×4. 모든 switch는 자기 prior 추정 거리입니다.','', '![M1 성능](figures/F3_M1_scores.png)','', 'R2_aA_m45에서는 b/c가 MB Heading 손상 gap의 절반 이상을 회복하고 거리 개선을 유지합니다. 그러나 같은 방법을 BB에 적용하면 Heading RMSE가 10% 넘게 악화하여 기준⑤를 통과하지 못합니다. R4_aA에서는 모든 M1 변형이 Heading RMSE를 악화시킵니다. R4_aB에서는 d만 Heading을 조금 줄이지만 목표 회복량과 사후 접선 오차 감소를 충족하지 못합니다. Rrr 전체를 키운 대조 e도 해법이 아니었습니다.','']
compact=s[(s.method=='M1')&(s.arm=='MB')][['case','bias','variant','heading_rmse_deg','range_rmse_cm','xy_rmse_m']];md += [table(compact),'', '### 기준별 판정','', '① Heading 회복, ② range 개선 80% 유지, ③ post mean(|e_t|)와 mean(|β̃|) 감소, ④ XY/Heading NEES 악화≤10%, ⑤ BB Heading 악화≤10%. false는 고정 기준 미충족이며 통계적 유의성 판정이 아닙니다.','',table(pd.read_csv(R/'M1_DECISIONS.csv')[['variant','case','bias','criterion1','criterion2','criterion3','criterion4','criterion5']]),'',table(pd.read_csv(R/'M2_DECISIONS.csv')[['variant','case','bias','criterion1','criterion2','criterion3','criterion4','criterion5']]),'', '## 6. 통과 시계열과 R5 재노출','', '![통과 사례](figures/F4_pass_timeseries.png)','', '고정 사례 R4_aB B0와 R5_aA B0에 OFF, M1-a, M2 k=1을 겹쳤습니다. 결과가 가장 좋아 보이는 변형을 골라 그린 그림이 아닙니다. 주황 구간은 GT 통과, 수직 점선은 평가 시작 30초입니다. R5에서는 세 차례 통과를 모두 표시했습니다.','', 'R5의 pass별 post 통계는 `ALL_PASS_METRICS.csv`, 기준별 판정은 `M1_ROBUSTNESS.csv`와 `M2_ROBUSTNESS.csv`에 있습니다. 전역 Heading 점수는 pass별 점수로 바꾸지 않았으며, ③만 각 pass의 post 창에서 평가합니다. 아래는 OFF/M1-a/M2-k1의 MB post mean(|e_t|)입니다.','']
show=ps[ps.case.str.startswith('R5')&(ps.arm=='MB')&ps.variant.isin(['M1-0','M1-a','M2-1'])][['case','bias','pass_id','variant','valid_post','post_length_s','mean_abs_et_cm','mean_abs_beta_deg']];md += [table(show),'', '## 7. 해석 한계와 다음 단계','', '- 이번 결과는 고정 A_B, 기존 시뮬레이션 RF와 주행 궤적의 탐색적 비교입니다. 자연 gate나 독립 데이터의 성능으로 일반화하지 않습니다.\n- T와 창 선택은 같은 trace를 보고 한 것이므로 독립 검증이 아닙니다. B0/L2를 독립 반복으로 세지 않습니다.\n- M3의 상대 posterior 궤적에는 이미 편파·Heading 정보가 포함됩니다. 정렬 Fisher는 궤적 모양이 정확하다는 조건부 불확실성이며, 순수 range-only 전역 관측성을 증명하지 않습니다.\n- M2의 제한은 동역학에 의한 접선 이동 전체가 아니라 측정 갱신의 누적량에만 작용합니다. 또한 gain의 직접 ψ행을 바꾸지 않습니다.\n- 현 기준을 완화하거나 새 R/Q/Heading prior로 추가 실험하지 않았습니다. **세 방법 모두 현 설정에서 채택 보류**로 닫습니다. 다음 실험을 정한다면 R2의 MB 개선과 BB 손상의 차이, 초기 통과의 누적 제한 작동 시점, 고정 궤적 가정의 한계를 먼저 검토할 근거가 있습니다.','', '## 산출물 안내','', '`CHECKS.json`은 검산 묶음, `INPUT_LOCK.json`/`M1_INPUT_LOCK.json`/`M2_INPUT_LOCK.json`은 입력 고정, `OUTPUT_SHA256.json`은 최종 산출물 해시입니다. 원본 trace는 M1_OFF/M1_SWEEP/M2_OFF/M2_SWEEP 폴더에 있습니다. 소스 실행 순서는 prechecks.py → finalize_pre.py → run_m1.py → run_m2.py → analyze_results.py → render_report.py입니다. prechecks.py의 마지막 집계 오류는 위에 명시한 그대로 보존되어 있어, 기존 저장 결과를 finalize_pre.py로 마무리합니다.','']
(R/'RESULTS_KO.md').write_text('\n'.join(md),encoding='utf-8');print('Rendered 5 figures and report')

