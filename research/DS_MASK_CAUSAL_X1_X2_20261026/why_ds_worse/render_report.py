"""Static diagnostic figures; append intervention figures and report after verification."""
from pathlib import Path
import sys,json
sys.dont_write_bytecode=True
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import diagnostics as D
R=Path(__file__).resolve().parent;F=R/'figures';F.mkdir(exist_ok=True)
plt.rcParams.update({'font.size':9,'axes.grid':True,'grid.alpha':.2,'savefig.dpi':155})
COL={'BB':'#334155','MB':'#dc5b16'};cases=list(D.CASES);cases=[c for c in cases if (R.parent/'e1_e4/E1'/f'{c}_B0.npz').exists()]
def save(fig,name):fig.savefig(F/name,bbox_inches='tight');plt.close(fig)
def table(df):
    df=df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):df[c]=df[c].map(lambda v:'NA' if pd.isna(v) else f'{v:.4f}')
    return '| '+' | '.join(df.columns)+' |\n|'+'|'.join(['---']*len(df.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in df.itertuples(index=False,name=None))
def plots0():
    bins=pd.read_csv(R/'D1_RANGE_ERR_BY_BIN.csv');post=pd.read_csv(R/'D2_ABS_TANGENT_BY_PASS.csv')
    for tag,cs in [('primary',D.PRIMARY),('auxiliary',[c for c in cases if c not in D.PRIMARY])]:
        fig,ax=plt.subplots(2,len(cs),figsize=(4.1*len(cs),7),sharex=True,sharey='row',layout='constrained');centers=[.25,.75,1.25,1.75,2.5,3.5,5,7,9]
        for col,c in enumerate(cs):
            for arm in ['BB','MB']:
                for bias,style in [('B0','-'),('L2','--')]:
                    dd=bins[(bins.case==c)&(bins.bias==bias)&(bins.arm==arm)&(bins.scope=='all')&(bins.bin!='near')]
                    for row,key in enumerate(['mean_er_m','mean_elat_m']):ax[row,col].plot(centers,dd[key]*100,style,marker='o',ms=3,color=COL[arm],label=arm+' '+bias)
            ax[0,col].set_title(c)
            for row in range(2):ax[row,col].axhline(0,color='gray',lw=.8);ax[row,col].set_xscale('log');ax[row,col].axvspan(.1,1.5,color='gold',alpha=.08)
            ax[1,col].set_xlabel('GT horizontal distance bin (m)');ax[1,col].set_xticks([.25,1,3,9],['0.25','1','3','>=8'])
        # Establish full shared bounds after all data are plotted.
        for row,key in enumerate(['mean_er_m','mean_elat_m']):
            v=bins[(bins.case.isin(cs))&(bins.scope=='all')&(bins.bin!='near')][key].dropna()*100;lo,hi=v.min(),v.max();pad=max((hi-lo)*.1,.1);ax[row,0].set_ylim(lo-pad,hi+pad)
        ax[0,0].set_ylabel('Mean model-range error (cm)');ax[1,0].set_ylabel('Mean e_r * r_3D / d proxy (cm)');ax[0,0].legend(fontsize=8);fig.suptitle('D1 accepted packets, all time; B0 solid / L2 dashed; empty bins remain gaps');save(fig,'F1_range_'+tag+'.png')
    fig,ax=plt.subplots(2,4,figsize=(17,8),layout='constrained')
    for axis,c in zip(ax.flat,cases):
        for arm,shift in [('BB',-.08),('MB',.08)]:
            for bias,style in [('B0','-'),('L2','--')]:
                q=post[(post.case==c)&(post.bias==bias)&(post.arm==arm)].sort_values('pass_id');axis.plot(q.pass_id+shift,q.delta_et_cm,style,marker=('o' if bias=='B0' else 's'),color=COL[arm],label=arm+' '+bias)
                for row in q[~q.valid].itertuples():axis.text(row.pass_id,.95,'NA',transform=axis.get_xaxis_transform(),ha='center',fontsize=8)
        axis.axhline(0,color='gray');axis.set_title(c);axis.set_xlabel('Pass number');axis.set_ylabel('Post mean e_t - pre mean e_t (cm)');axis.set_xticks(sorted(post[post.case==c].pass_id.unique()));axis.set_xlim(.7,post[post.case==c].pass_id.max()+.3)
    ax.flat[0].legend(fontsize=8);ax.flat[-1].set_visible(False);fig.suptitle('D2 signed change of each arm itself, not MB minus BB; per-case y scales');save(fig,'F2_pass_tangent.png')
    series=pd.read_csv(R/'D3_SERIES.csv.gz');q=series[(series.case=='R2_aA_m45')&(series.bias=='B0')];p=D.PASSES[(D.PASSES.case=='R2_aA_m45')&(D.PASSES.bias=='B0')&(D.PASSES.pass_id==1)].iloc[0];q=q[(q.t_s>=p.start_s-10)&(q.t_s<=p.end_s+10)]
    fig,ax=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained');ax[0].plot(q.t_s,q.c_m*100,color='#0284c7',label='c = mu_MB - mu_BB');ax[0].set_ylabel('Correction difference (cm)');ax[0].legend()
    for arm in ['BB','MB']:ax[1].plot(q.t_s,q['er_'+arm+'_m']*100,color=COL[arm],label=arm);ax[2].plot(q.t_s,q['Ft_'+arm+'_cm'].cumsum(),color=COL[arm],label=arm)
    ax[1].set_ylabel('Model-range residual (cm)');ax[2].set_ylabel('Cumulative range F_t (cm)');ax[2].set_xlabel('Time (s)')
    for a in ax:a.axvspan(p.start_s,p.end_s,color='gold',alpha=.12);a.axhline(0,color='gray',lw=.8)
    ax[1].legend();ax[2].legend();fig.suptitle('D3 fixed example R2_aA_m45 B0, first expanded pass; rejected residuals are gaps');save(fig,'F3_forcing_example.png')
def plots1():
    scores=pd.read_csv(R/'REPLAY_SCORES.csv');arms=['OFF_BB','OFF_MB']+[f'{k}_{d:.1f}' for d in [1.,1.5,2.5] for k in ['NEAR_ONLY','FAR_ONLY']]+['ORACLE0_BB','ORACLE0_MB','C_MEAN0','C_MEANONLY','C_FLIP','C_PERM_MEDIAN'];labels=['BB','MB','N1','F1','N1.5','F1.5','N2.5','F2.5','O|BB','O|MB','Mean0','Const','Flip','Perm']
    extra_est=sorted(a for a in scores.arm.unique() if a.startswith('FAR_EST_'));arms+=extra_est;labels+=['EST'+a.split('_')[-1] for a in extra_est]
    for tag,cs in [('primary',D.PRIMARY),('auxiliary',[c for c in cases if c not in D.PRIMARY])]:
        fig,ax=plt.subplots(2,len(cs),figsize=(5*len(cs),8),sharey='row',layout='constrained');maxima=[0,0]
        for col,c in enumerate(cs):
            for bias,sty,color,shift in [('B0','-','#334155',-.08),('L2','--','#dc5b16',.08)]:
                sub=scores[(scores.case==c)&(scores.bias==bias)].set_index('arm');perm=sub[sub.index.str.startswith('C_PERM_')]
                for row,key,scale in [(0,'heading_rmse_deg',1),(1,'xy_rmse_m',100)]:
                    vals=np.array([sub.loc[a,key] if a!='C_PERM_MEDIAN' else perm[key].median() for a in arms])*scale;ax[row,col].plot(np.arange(len(arms))+shift,vals,sty,marker='o',ms=3,color=color,label=bias);ax[row,col].vlines(arms.index('C_PERM_MEDIAN')+shift,perm[key].quantile(.1)*scale,perm[key].quantile(.9)*scale,color=color,lw=3);maxima[row]=max(maxima[row],vals.max(),perm[key].max()*scale)
                    ax[row,col].axhline(sub.loc['OFF_BB',key]*scale,color='#8b8b8b',ls=sty,lw=.8);ax[row,col].axhline(sub.loc['OFF_MB',key]*scale,color='#0891b2',ls=sty,lw=.8);ax[row,col].set_xticks(range(len(arms)),labels,rotation=65);ax[row,col].set_xlabel('N/F: GT distance split; O: oracle; Perm: median + p10–p90')
            ax[0,col].set_title(c)
        for row in range(2):ax[row,0].set_ylim(0,maxima[row]*1.08)
        ax[0,0].set_ylabel('Heading RMSE (deg)');ax[1,0].set_ylabel('XY RMSE (cm)');ax[0,0].legend();fig.suptitle('T1–T3 t >= 30 s; gray BB / cyan MB baseline; B0 solid / L2 dashed');save(fig,'F4_interventions_'+tag+'.png')

def report():
    s=pd.read_csv(R/'REPLAY_SCORES.csv');g=pd.read_csv(R/'GAP_METRICS.csv');h=pd.read_csv(R/'HYPOTHESIS_SUMMARY.csv');bins=pd.read_csv(R/'D1_RANGE_ERR_BY_BIN.csv');f=pd.read_csv(R/'D3_FORCING.csv');post=pd.read_csv(R/'D2_ABS_TANGENT_BY_PASS.csv');perm=pd.read_csv(R/'T3_PERM_SUMMARY.csv');dd=pd.read_csv(R/'HYPOTHESIS_DECISIONS.csv');gate=json.loads((R/'T1_EST_GATE.json').read_text());ver=json.loads((R/'VERIFY_CHECKS.json').read_text());dcheck=json.loads((R/'D_CHECKS.json').read_text())
    text=['# Δs 보정은 왜 BASE보다 나빠지는가','', '> 판정은 고정된 운영 기준에 따른 이번 데이터의 결과입니다. 기술적 분해와 개입 결과를 분리하며, 여러 모델 오차 중 유일 원인을 확정하지 않습니다.','', '## 1. 가설별 판정','',table(h),'', 'SUPPORT는 주 3개 case 중 최소 2개에서 B0/L2가 모두 기준을 만족했다는 뜻입니다. NOT_SUPPORT는 해당 예측 미충족이며 가설 전체의 불가능성을 증명하지 않습니다. W5만은 R 변경이라는 구체적 전제가 실제로 없으므로 그 설명을 배제합니다. D1/D3 행은 기술 후보, T1/T2/T3 행은 개입 판정입니다.','', '### 결과가 가리키는 차이','', '- **손상이 집중되는 구간:** D=2.5m의 거리 분할은 주3case 모두 조건을 만족합니다. 그러나 D1에서 근거리 평균 잔차 절댓값이 증가한 것은 R4_aA 하나뿐이고 RMS는 모두 개선됩니다. 따라서 근거리 구간의 중요성과 근거리 range 오보정은 같은 주장이 아닙니다.\n- **R2_m45:** 순서 섞기만으로는 gap이 약33–35% 줄어 50% 기준에 못 미칩니다. 통과 평균 제거 효과가 더 크며, oracle0|BB는 Heading RMSE를 약20% 악화시킵니다.\n- **R4 두 case:** 순서 섞기는 gap을 중앙값 약74–81% 줄입니다. 통과 평균 제거는 효과가 작고, 상수만 남긴 경우는 BB에 가까워집니다. 느린 잔차 자체보다 보정의 시간·기하 배치가 중요하다는 해석과 부합합니다.\n- **상쇄 가설의 범위:** R4_aA oracle 악화9.7–9.9%는 사전10% 기준 미달이며, 반올림해 지지로 바꾸지 않습니다. W3는 R2만 지지하고 전체2/3기준은 미충족입니다.\n- **부호 반전:** 원문 delta_e_t 기준 W4는 R2_m45/R4_aA에서 지지됩니다. R4_aB는 접선 gap은 뒤집혀도 각 arm의 post−pre 변화량은 양수로 남습니다. 이 차이를 주·보조 판정으로 구분합니다.','', '## 2. 실행 계약과 검산','', f'- 기준 commit: `2ee731336fc2b37ffcd67f96a07bdaf3dccc2898`, 브랜치 `research/ds-x1-x2-results-20261026`.\n- 14조건, 고정 A_B. CONTROL 4개 arm + T1–T3 31개 arm을 조건마다 실행했습니다. T1-est 대상 D: {gate["eligible_D"]}.\n- D0–D4 검산 {len(dcheck["checks"])}개, 저장 trace 독립 검산 {len(ver["checks"])}개 통과. OFF_BB/MB와 ORACLE_BB/MB 각각 E1 재현 허용차 1e-10.\n- 원측정·mu·R·mask, 거리 switch, seed별 순열 분포, oracle 목표, 최적 joint gain, Joseph 공분산, 대칭/PSD, 전체 점수와 pass 점수를 검산했습니다.\n- 기존 산출물/Q/학습/편파 평균/R 보존. T4는 R 차이 0으로 생략. 새 통계·코드·trace·그림은 이 폴더 안에만 저장합니다.','', '### 정의와 학습 근거','', 'range 오차는 기하학적 거리 대신 h_r(GT)=3D거리−0.5315983906250129 m를 기준으로 했습니다. D1/D4는 전체 시간의 accepted packet이며 D1 scoring(t≥30) 표도 별도 포함합니다. posterior 오차는 거절 packet을 포함합니다. 초기 통과는 t<30이어도 개입·통과 통계에 포함됩니다.','', '편파 평균/R 학습 라벨은 GT 위치·Heading에서 SourceFFD를 평가한 측정 잔차입니다. held route를 제외하고 test와 중복되는 위치도 제외했습니다. BASE posterior를 학습 정답으로 사용한 것이 아닙니다. 현재 predict_one은 q=diag(2e-5·|ds|, radians(0.015)²·dt, 0)의 고정 제어잡음을 운동모델로 전파합니다. 따라서 W3의 “Q가 BASE 궤적에 맞춰 학습됐다”는 설명은 코드 근거가 없습니다.','', '## 3. D1: 근거리 range 오차','', '![주 분석 거리 잔차](figures/F1_range_primary.png)','', '![보조 거리 잔차](figures/F1_range_auxiliary.png)','', 'e_lat=e_r·r_3D/d는 거리 감도에 따른 증폭 대용값이며 실제 접선 위치 오차가 아닙니다. 앵커 바로 근처에서는 1/d 때문에 커지므로 이를 위치 오차로 직접 해석하지 않습니다. 빈 bin은 보간하지 않았습니다.','',table(bins[(bins.scope=='all')&(bins.bin=='near')][['case','bias','arm','n','mean_er_m','rms_er_m','mean_elat_m']]),'', '## 4. D2·D3: 접선 변화와 3항 분해','', '![통과별 각 arm의 접선 변화](figures/F2_pass_tangent.png)','', '그림은 |오차|가 아니라 각 arm 자체의 signed post−pre 변화입니다. BB를 뺀 gap과 구별합니다. R5의 세 통과를 모두 포함하고 유효 post가 부족한 통과는 NA로 남겼습니다.','', '![고정 사례의 forcing](figures/F3_forcing_example.png)','', '정확한 분해는 −K_M c + (K_M−K_B)ν_B − K_M(h_M−h_B)입니다. 마지막 항은 이미 달라진 prior 위치에 대한 반응을 포함합니다. 주 결과는 공통 GT축, 비교 결과는 공통 BB prior축이며 각 arm 자기 축의 합도 별도 열로 제공합니다. 자기 축의 차이를 세 항의 효과로 섞지 않았습니다.','']
    ff=f[(f.segment=='expanded')&(f.frame=='GT')&(f.direction=='tangent')&(f.pass_id==1)];text += [table(ff[['case','bias','F_BB_cm','F_MB_cm','correction_cm','gain_difference_cm','prediction_difference_cm','sign_relation','opposite_similar','tau_BB_s','tau_MB_s']]),'', '주 분석에서는 보정항과 예측 차이항이 반대 부호이며 크기가 비슷합니다. 이는 접선축에 투영했을 때 복원 방향의 성분이 상당함을 보여줍니다. 그 사실만으로 “복원이 접선으로 새는 것이 유일 원인”이라고 확정하지 않습니다. gain과 예측은 이전 상태에 의존하므로 장부 항을 독립 개입 효과처럼 해석할 수 없습니다. 창 경계는 소수8자리 시간으로 고정했으므로 이전 탐색적 계산과 경계 packet 포함 여부가 다를 수 있습니다.','', '### R2_aB 별도 기술값','',table(ff[ff.case=='R2_aB_m0'][['bias','F_BB_cm','F_MB_cm','correction_cm','gain_difference_cm','prediction_difference_cm','tau_BB_s','tau_MB_s']]),'',table(post[post.case=='R2_aB_m0'][['bias','arm','pass_id','pre_cm','post_cm','delta_et_cm','valid']]),'', 'R2_aB의 D1 near 값은 위 표에, 전체 거리 bin과 D3 전·중·후/창밖 분해는 원 CSV에 보존합니다. 주 3개 case의 결론에 이 보조 조건을 포함하지 않습니다.','', '## 5. T1–T3 개입 결과','', '![주 분석 개입 성능](figures/F4_interventions_primary.png)','', '![보조 조건 개입 성능](figures/F4_interventions_auxiliary.png)','', '회색은 BB, 청록은 MB 기준선입니다. B0/L2를 평균하지 않았으며 Perm은 20 seed 중앙값과 p10–p90입니다. 고정 A_B와 GT switch의 oracle 진단이므로 실제 배포 성능과 구별합니다.','', '### T1: 거리 분할','',table(pd.read_csv(R/'T1_EST_GATE_DECISIONS.csv')),'', f'T1-est는 같은 D에서 주2/3 case의 B0/L2가 모두 기준을 만족할 때만 실행하도록 했습니다. 대상 D={gate["eligible_D"]}. 빈 목록이면 T1-est는 미실행입니다.','', '### 추정 거리 switch 후속 결과','', '추정 거리 2.5 m 밖에서만 보정한 FAR_EST_2.5는 주 6조건에서 Heading bias gap을 86.2–96.0% 줄이고 range RMSE 개선량을 79.8–112.5% 유지했습니다. R4_aB의 Heading RMSE는 BB보다 약0.01° 높게 남습니다. 이는 고정 A_B에서의 결과이며 자연 gate 또는 새 데이터의 성능을 입증하지 않습니다.','',table(s[s.arm.str.startswith('FAR_EST_')][['case','bias','arm','heading_rmse_deg','heading_bias_deg','range_rmse_cm','xy_rmse_m']]),'',table(g[g.arm.str.startswith('FAR_EST_')][['case','bias','f_bias_magnitude','f_tangent_magnitude','range_retention']]),'', '추정 거리 switch는 이번 데이터에서의 실사용 후보 검사입니다. 자연 gate와 독립 경로 검증을 하지 않았으므로 배포 채택으로 확정하지 않습니다.','', '### T2: 모델 기준 oracle','']
    qq=s[s.arm.isin(['OFF_BB','OFF_MB','ORACLE0_BB','ORACLE0_MB'])];text += [table(qq[['case','bias','arm','heading_rmse_deg','heading_bias_deg','range_rmse_cm','xy_rmse_m']]),'', 'ORACLE0|BB 악화는 해당 배경에서 보정 range를 정확하게 만드는 개입이 손상을 준다는 관찰입니다. 다른 오차와의 상쇄라는 설명과 부합하지만, 특정 편파 편향이나 Q/R이 그 상대였다는 것을 단독으로 식별하지 않습니다. ORACLE0|BB와 ORACLE0|MB는 확장창 밖 c와 그로 인해 달라진 상태 이력을 포함해 비교됩니다. 확장창 밖은 모두 원거리가 아니므로 T1 FAR_ONLY와 동일 개입으로 취급하지 않습니다.','', '### T3: 순서·평균·부호 교란','',table(perm[perm.metric=='f_bias_magnitude'][['case','bias','n','median','p10','p90','minimum','maximum','n_ge_half']]),'',table(dd[dd.stage.str.startswith('T3_FLIP')][['case','bias','hypothesis','stage','result','value','note']]),'', 'C_PERM은 창 안 c의 분포와 평균을 보존합니다. C_MEAN0/MEANONLY는 각 조건·각 통과의 자기 A_B 확장창 평균을 사용합니다. 기존 component_azimuth의 전역 c 평균과 달리 창 밖 보정은 MB 그대로이므로 수치를 직접 같은 성분 몫으로 합산하지 않습니다. W4 주 판정은 원문 D2의 각 arm delta_e_t(post−pre) 부호 반전과 BB 대비 Heading bias 이동 반전을 함께 봅니다. 접선도 BB 대비 gap으로 보는 보조 판정은 W4_AUX로 구분합니다. DECISION_CLARIFICATION.md에 원문 대응을 명시했습니다. 모든 seed 결과는 T3_PERM_SEEDS.csv에 있습니다.','', '### 기존 전역 성분 분리와 비교','',table(pd.read_csv(R/'T3_GLOBAL_COMPONENT_COMPARISON.csv').loc[lambda x:x.case.isin(D.PRIMARY)][['case','bias','definition','heading_rmse_deg','heading_bias_deg','xy_rmse_m']]),'', '기존 FULL_1과 이번 OFF_MB 점수가 일치함을 검산했습니다. 전역 상수/변동과 통과별 상수/변동은 적용 영역과 평균이 다르므로 동일 실험으로 취급하지 않습니다.','', '## 6. D4와 해석 한계','', 'D4 회귀는 sin/cos Heading, 상대방위, world-y, 거리와 sign(dy_GT/dt)를 사용했습니다. 마지막 항은 지그재그 위상 대용변수입니다. 상관이 큰 변수가 섞이므로 계수/rank/조건수/R²를 함께 저장했습니다. 통과 블록이 1–3개라 CI와 유의성 판정은 하지 않았습니다. 높은 R²를 원인 증거로 쓰지 않습니다.','', 'B0/L2는 동일 RF의 쌍입니다. R4 두 앵커 case를 서로 독립인 물리적 route로 세지 않습니다. 이 결과는 현 시뮬레이션 RF·필터·고정 mask에 한정됩니다. W1–W4 운영 예측이 미충족이어도 다른 형태의 모델 불일치·시간상관·기하 의존성이 모두 배제되는 것은 아닙니다.','', '## 산출물','', 'PROTOCOL.md / INPUT_LOCK.json / REPLAY_INPUT_LOCK.json / CHECKS.json / OUTPUT_SHA256.json에서 정의·입력·검산·산출 해시를 확인할 수 있습니다. CONTROL과 INTERVENTIONS 폴더에는 원 trace, T1/T2/T3_SCORES.csv에는 점수, GAP_METRICS.csv에는 분자·분모·부호와 감소율이 있습니다. HYPOTHESIS_DECISIONS.csv는 조건별 판정, HYPOTHESIS_SUMMARY.csv는 B0/L2 쌍을 묶은 주 case 판정입니다.','']
    (R/'RESULTS_KO.md').write_text('\n'.join(text),encoding='utf-8')
if __name__=='__main__':
    plots0()
    if (R/'VERIFY_CHECKS.json').exists():plots1();report();print('All figures and report rendered')
    else:print('D0-D4 figures rendered; replay report pending')




