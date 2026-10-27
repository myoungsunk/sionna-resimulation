from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent;P=R.parent/'DS_GEOMETRY_PHYSICAL_20261027';F=R/'figures';F.mkdir(exist_ok=True)
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
def table(df):
 def fmt(x):
  if isinstance(x,(float,np.floating)):return '—' if pd.isna(x) else f'{x:.6f}'
  return str(x)
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
b=pd.read_csv(R/'B_INTERACTIONS.csv');moves=pd.read_csv(R/'B_POSITION_MOVEMENT.csv');decomp=pd.read_csv(R/'B_ALL_ARMS_DECOMPOSITION.csv');tr=pd.read_csv(R/'TRANSFER_RATIOS.csv');cells=pd.read_csv(R/'TRANSFER_SIX_CELLS.csv');necessity=pd.read_csv(P/'C_GAP_REDUCTIONS.csv')
assert len(decomp)==210 and len(tr)==6 and len(cells)==36
end=b[(b.alpha==1)&b.case.isin(PRIMARY)].copy();end['description']=np.where(~end.shares_interpretable,'비가산/작은 분모: 몫 해석 제외',np.where((end.s_const>=.7)&(end.s_var<=.3),'상수 성분의 기술적 몫 ≥0.7',np.where((end.s_var>=.7)&(end.s_const<=.3),'변동 성분의 기술적 몫 ≥0.7','두 성분의 기술적 몫 함께 보고')))
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':170})
fig,axes=plt.subplots(2,3,figsize=(14,8),layout='constrained')
for col,case in enumerate(PRIMARY):
 for arm,color in [('FULL','#333333'),('CONST','#27689b'),('VAR','#c58436')]:
  for bias,ls,marker in [('B0','-','o'),('L2','--','x')]:
   g=moves[(moves.case==case)&(moves.bias==bias)&(moves.arm==arm)].sort_values('alpha')
   axes[0,col].plot(g.alpha,g.delta_tangential_cm,color=color,ls=ls,marker=marker,label=arm+' '+bias)
   axes[1,col].plot(g.alpha,g.delta_heading_deg,color=color,ls=ls,marker=marker,label=arm+' '+bias)
 axes[0,col].set_title(case);axes[0,col].set_ylabel('Mean tangential shift from BB (cm)');axes[1,col].set_ylabel('Heading bias change from BB (deg)');axes[1,col].set_xlabel('alpha')
 for ax in axes[:,col]:ax.axhline(0,color='gray',lw=.5);ax.grid(alpha=.2)
axes[0,0].legend(fontsize=8,ncol=2);fig.suptitle('B: constant / varying range correction; paired B0/L2');fig.savefig(F/'B_component_sweep.png');plt.close(fig)
fig,axes=plt.subplots(2,3,figsize=(14,7),layout='constrained')
for col,case in enumerate(PRIMARY):
 for row,bias in enumerate(['B0','L2']):
  g=cells[(cells.case==case)&(cells.bias==bias)];ax=axes[row,col]
  for alpha,color in [(0,'#27689b'),(1,'#b65e28')]:
   gg=g[g.range_alpha==alpha].set_index('azimuth_source').loc[['GT','BB','MB']]
   ax.plot(range(3),gg.heading_bias_deg,'o-',color=color,label='range alpha='+str(alpha))
  ax.set_title(case+' / '+bias);ax.set_xticks(range(3),['GT donor','BB prior','MB prior']);ax.set_ylabel('Heading signed bias (deg)');ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Azimuth transplant: fixed donor, zero azimuth derivative in all six cells');fig.savefig(F/'TRANSFER_six_cells.png');plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
for ax,den in zip(axes,['E1','control']):
 x=np.arange(len(tr));ax.bar(x-.18,tr['forward_ratio_'+den],width=.36,label='BB receives MB azimuth',color='#27689b');ax.bar(x+.18,tr['backward_ratio_'+den],width=.36,label='MB receives BB azimuth',color='#b65e28');ax.axhline(.7,color='gray',ls='--');ax.set_xticks(x,tr.case+'\n'+tr.bias,rotation=25,ha='right');ax.set_ylabel('Directed shift / gap');ax.set_title('Denominator: '+den);ax.legend(fontsize=8)
fig.suptitle('Sufficiency ratios: both directions >=0.7 required; denominator sensitivity explicit');fig.savefig(F/'TRANSFER_ratios.png');plt.close(fig)
move_end=moves[(moves.alpha==1)&moves.case.isin(PRIMARY)].copy()
close=[]
def nullable_bool(x):
 if pd.isna(x):return None
 return x.lower()=='true' if isinstance(x,str) else bool(x)
for _,r in tr.iterrows():
 br=end[(end.case==r['case'])&(end.bias==r['bias'])].iloc[0];nc=necessity[(necessity.case==r['case'])&(necessity.bias==r['bias'])&(necessity['mode']=='CUT_ALL')].iloc[0]
 close.append(dict(case=r['case'],bias=r['bias'],verification='COMPLETED',necessity_f_magnitude=nc.f_magnitude,B_s_const=br.s_const,B_s_var=br.s_var,B_interaction_ratio=br.I_bias_normalized,sufficiency_E1=nullable_bool(r.sufficiency_E1),sufficiency_control=nullable_bool(r.sufficiency_control),denominator_disagreement=bool(r.denominator_disagreement)))
pd.DataFrame(close).to_csv(R/'PRIMARY_CLOSURE.csv',index=False)
lines=['# 주 분석 6조건: B 성분 분리와 방위각 이식','', '**주 분석 6조건의 지정된 검증을 완료로 닫는다. 검증 완료와 가설 지지는 구분한다.**','', '적용 범위는 R2_aA_m45, R4_aA_m0, R4_aB_m0의 B0/L2 쌍이다. B0/L2를 독립 반복으로 세지 않는다. GT·다른 Arm의 frozen prior를 이용한 오프라인 개입으로, 배포 가능한 알고리즘이나 통계적 유의성을 주장하지 않는다.','', '[실행 전 정의](PROTOCOL.md) · [조건별 완료 상태](PRIMARY_CLOSURE.csv)','', '## 1. B: 상수·변동 보정 성분','', '각 case × bias의 자기 BASE 수용 집합에서 c를 계산했다. B0/L2 c 동일성은 검산에서 제거했고, mean(v|A_B)=0 및 alpha0/1 대조 재현은 유지했다. B0/L2 차이와 mask 차이는 기술값으로 남겼다.','',table(pd.read_csv(R/'B_PAIRED_DESCRIPTIVE.csv')),'','상수 c는 range 평균 보정에 더해지는 값이다. 관측 innovation에서는 z−h−mu이므로 양의 c는 보정된 range를 줄인다.','', '### Heading bias 변화에서 각 성분이 차지하는 몫(기술)','',table(end[['case','bias','delta_FULL','delta_CONST','delta_VAR','s_const','s_var','I_bias_normalized','description']]),'','분모가 작거나 정규화 상호작용>0.3이면 몫을 해석하지 않는다. 음의 몫/1보다 큰 몫은 상쇄 또는 넘침을 나타낼 수 있으며 숨기지 않는다.','', '### 상수 성분이 만드는 접선 이동','', '아래 값은 GT 접선축에서 CONST/VAR/FULL 위치와 E1 BB 위치의 차이를 투영한 평균 signed 이동이다. 궤적 전체가 같은 벡터만큼 평행 이동한다는 뜻은 아니다. 예상한 4–9cm 범위에 맞춰 값을 선택하지 않았다.','',table(move_end[['case','bias','arm','delta_tangential_cm','FULL_tangential_cm','tangential_fraction','delta_beta_deg','delta_phi_deg','delta_radial_cm']]),'','![성분별 sweep](figures/B_component_sweep.png)','', '[Arm×alpha 전체 beta/phi/접선/반경 bias 표](ALL_DECOMPOSITION.md) · [전체 수치](B_ALL_ARMS_DECOMPOSITION.csv) · [직접 투영 검산](B_MOVEMENT_CHECKS.json)','', '## 2. 방위각 이식: 충분성','', '각 packet에서 E1 BB 또는 MB의 **prior 위치**로 방위각을 정했다. 두 안테나는 동일한 방향 벡터를 사용하고, 수신 Arm의 앙각·거리·Heading은 유지했다. 모든 셀에서 donor 방위각 미분은 0이다. GT 두 셀은 기존 CUT_AZ를 재사용했으며, 신규 replay는 6조건×4셀=24개다.','', '동일 Jacobian 조건의 자기 donor 대조군은 자연 갱신 E1과 다를 수 있다. 따라서 G_E1 및 G_control과 두 방향 비율을 모두 보고한다. 두 분모가 다른 판정을 내면 충분성 결론에 그 차이를 명시한다.','',table(tr[['case','bias','G_E1','G_control','forward_deg','backward_deg','forward_ratio_E1','backward_ratio_E1','forward_ratio_control','backward_ratio_control','sufficiency_E1','sufficiency_control']]),'', '![여섯 셀](figures/TRANSFER_six_cells.png)','', '![충분성 비율](figures/TRANSFER_ratios.png)','', '### E1과 대조군의 차이','',table(tr[['case','bias','E1_BB','control_BB','BB_control_minus_E1','E1_MB','control_MB','MB_control_minus_E1']]),'', '### 조건별 결론','']
for r in close:
 s='작은 분모가 있어 해당 충분성 판정 불가' if r['sufficiency_E1'] is None or r['sufficiency_control'] is None else '두 분모 기준 모두 양방향 충분성 지지' if r['sufficiency_E1'] and r['sufficiency_control'] else '분모에 따라 판정이 달라 무조건적인 충분성 결론 보류' if r['denominator_disagreement'] else '양방향 0.7 기준의 충분성은 지지되지 않음'
 lines.append(f'- {r["case"]}/{r["bias"]}: 검증 완료. {s}. 필요성 f_magnitude={r["necessity_f_magnitude"]:.6f}.')
summary=['## 결과 요약','', '방위각 이식은 주 분석 6조건 모두에서 양방향 0.7 기준을 충족했다. E1 분모와 동일한 방위각 미분 규칙을 적용한 대조군 분모 사이에 판정 불일치는 없었다. 단, 같은 미분 규칙이라는 뜻이지 전체 Jacobian의 수치가 같다는 뜻은 아니다.','', '| 경로 | 이식 양방향 비율 범위: 대조군 gap 기준 | CONST 접선 이동 / FULL 접선 이동 |','| --- | --- | --- |']
for case in PRIMARY:
 gg=tr[tr.case==case];rat=np.r_[gg.forward_ratio_control,gg.backward_ratio_control];mm=move_end[move_end.case==case];cc=mm[mm.arm=='CONST'].delta_tangential_cm;ff=mm[mm.arm=='FULL'].delta_tangential_cm
 summary.append(f'| {case} | {100*rat.min():.2f}–{100*rat.max():.2f}% | {cc.min():.2f}~{cc.max():.2f} cm / {ff.min():.2f}~{ff.max():.2f} cm |')
summary+=['','R2_m45는 상수 성분이 접선 이동을 크게 만들고 변동 성분이 일부 상쇄한다. R4 두 경로는 상수 성분만으로 FULL의 접선 이동을 재현하지 못한다. R4_aA의 Heading 성분 몫은 상호작용 30% 초과로 해석에서 제외한다.','', 'R4_aA의 E1 gap 기준 이식 비율은 약 2.6–2.8로 과대 재현된다. 동일 미분 규칙의 대조군 gap에서는 약 0.96–1.01이다. 따라서 E1 수치와 정확히 같아졌다고 표현하지 않는다.','']
lines[6:6]=summary
lines+=['','이식은 방위각 경로를 통한 개입의 충분성을 진단한다. 다른 경로의 부재나 유일 원인, 실환경 일반화를 증명하지 않는다.','', '## 3. 별도 트랙 및 범위 종료','', '- R2_aA_m0, R2_aB_m0, R5_aB_m0: 현재 위치→편파 차단만으로 설명되지 않음. 별도 트랙으로 이관하며 이번 주 분석 결론을 보류하는 조건으로 삼지 않는다.','- 첫 질문: 같은 R2에서 마운트에 따라 기전이 갈리는 이유는 무엇인가? 이번 작업에서는 추가 replay를 실행하지 않았다.','- R5_aA_m0: 기존 gate 진단 트랙. 이번 주 분석 6조건에 포함하지 않는다.','- B는 기존 정의의 14조건 전체를 계산했지만 충분성 검정과 완료 선언의 적용 범위는 주 분석 6조건으로 한정한다.','', '## 4. 검산과 보존','', '- B: mean(v|A_B)≤1e-12m, CONST/VAR alpha0 및 FULL alpha1의 E1 trace 재현≤1e-10.','- GT donor provider의 h/H를 기존 CUT_AZ 전 시점에서≤1e-12로 검산했다.','- 공분산 대칭/PSD 및 거절 시 상태 불변 검산을 유지했다.','- 원본 frozen 결과는 수정하지 않았고, 별도 결과 폴더에 저장했다.','- 추적된 Python bytecode는 다음 패키지에서 제외한다. 원래 실행 manifest의 캐시 항목은 명시적 제외 기록으로 설명한다.','']
(R/'RESULTS_KO.md').write_text('\n'.join(lines),encoding='utf-8')
detail=['# Arm × alpha 오차 bias','', '각도 deg, 위치 cm. t>=30 전체 packet, 거절 포함. phi는 기술적 상대각 오차이며 단독으로 편파 관측 전체를 뜻하지 않는다.','']
for (case,bias),g in decomp.groupby(['case','bias'],sort=False):
 detail+=['## '+case+' / '+bias,'',table(g.sort_values(['arm','alpha'])[['arm','alpha','psi_bias','beta_bias','phi_bias','et_bias','er_bias']]),'']
(R/'ALL_DECOMPOSITION.md').write_text('\n'.join(detail),encoding='utf-8')
(R/'CLOSURE.json').write_text(json.dumps(dict(status='PRIMARY_SIX_VERIFICATION_COMPLETED',primary_conditions=close,secondary_track=['R2_aA_m0','R2_aB_m0','R5_aB_m0'],first_secondary_question='Why do R2 mechanisms differ by mount?',no_further_replay=True),indent=2),encoding='utf-8')
print('Final synthesis written')
