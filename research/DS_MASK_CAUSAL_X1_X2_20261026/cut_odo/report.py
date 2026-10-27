from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
p=Path(__file__).resolve().parent
assert json.loads((p/'GATE.json').read_text())['status']=='PASS'
a=pd.read_csv(p/'DECOMPOSITION.csv');base=pd.read_csv(p.parent/'DS_TANGENT_LEDGER_20261027/STEP0_STATS.csv');rows=[]
for (case,bias,state),q in a.groupby(['case','bias','state']):
 b=base[(base.case==case)&(base.bias==bias)&(base.state==state)&(base.source=='E1')].set_index('arm');q=q.set_index('arm');row=dict(case=case,bias=bias,state=state)
 for metric,old,new,scale in [('beta','beta_bias_deg','beta_bias',1),('heading','heading_bias_deg','psi_bias',1),('et','et_bias_cm','et_bias',1),('er','er_bias_cm','er_bias',1)]:
  g0=float(b.loc['A1',old]-b.loc['A0',old]);g=float(q.loc['A1',new]-q.loc['A0',new]);valid=abs(g0)>=(.01 if metric in ['beta','heading'] else 1e-10);fm=1-abs(g)/abs(g0) if valid else np.nan
  row.update({metric+'_G_E1':g0,metric+'_G_CUT_ODO':g,metric+'_f_magnitude':fm,metric+'_f_signed':1-g/g0 if valid else np.nan,metric+'_sign_flip':bool(g*g0<0),metric+'_decision':'undefined' if not valid else 'support' if fm>=.7 else 'partial' if fm>=.3 else 'insufficient'})
 rows.append(row)
r=pd.DataFrame(rows);r.to_csv(p/'GAP_REDUCTIONS.csv',index=False)
checks=json.loads((p/'CHECKS.json').read_text());assert all(x['pass_check'] for x in checks)
def table(df):
 out=['| '+' | '.join(df.columns)+' |','| '+' | '.join(['---']*len(df.columns))+' |']
 for row in df.itertuples(index=False,name=None):out.append('| '+' | '.join(f'{v:.4f}' if isinstance(v,float) else str(v) for v in row)+' |')
 return '\n'.join(out)
cols=['case','bias','beta_G_E1','beta_G_CUT_ODO','beta_f_magnitude','beta_decision','heading_G_E1','heading_G_CUT_ODO','heading_f_magnitude','heading_decision','et_G_E1','et_G_CUT_ODO']
text='''# CUT_ODO 결과\n\n주 분석 여섯 조건의 α0/1 oracle replay 완료. B0/L2는 쌍이며 독립 표본으로 세지 않는다.\n\n## 정확히 차단한 경로\n\n원래 원호 전파는 a=gyro−b_g dt, d=ds sinc(a/2)[cos(ψ+a/2),sin(ψ+a/2)]이다. 위치식의 시작 ψ만 이전 packet의 GT ψ로 교체했다. 추정 Heading 자체의 전파와 측정은 그대로 유지했다. 위치식의 ∂/∂ψ=0으로 하고 F/G에 맞춰 공분산을 다시 계산했다. gyro 및 b_g가 a를 통해 위치로 전달되는 경로는 남는다. 따라서 이 결과는 시작 Heading→주행 위치 경로의 개입이며 모든 방향 오차를 제거한 전파가 아니다.\n\nmask=A_B, 편파 평균과 R, 거리·gyro 관측 입력, 초기 상태는 원래 값이다. 기존 h_s는 추정 상태를 사용한다. 평가 표본은 t≥30 s 모든 packet이다.\n\n## Posterior gap 결과\n\nG=bias(α1)−bias(α0). 각도는 도, e_t는 cm. f_magnitude=1−|G_cut|/|G_E1|이며 각도 분모 최소 .01°. 0.7/0.3은 운영 기준이다. 음수는 gap 확대를 뜻한다.\n\n'''+table(r[r.state=='x'][cols])+'''\n\n## 해석 한계\n\n각도 gap 감소 여부와 부호 반전은 GAP_REDUCTIONS.csv에 함께 기록했다. 공분산과 후속 측정 gain도 달라지는 oracle 개입이므로 유일한 원인이나 배포 가능한 해결책으로 해석하지 않는다. 감소하지 않아도 남아 있는 gyro-bias→위치 경로를 포함한 모든 주행 적분 가설을 기각할 수 없다.\n\n## 검증\n\n차단 OFF 여섯 조건 α0/1에서 x/P/prior/Pprior/h/H/K/mu/R/nu/acc를 E1과 1e-10 이내로 검산한 뒤에만 CUT을 실행했다. 수정 상태 Jacobian은 유한차분과 1e-8 이내로 일치했고 Heading 평균 전파 보존을 확인했다. 입력 해시는 실행 전후 동일했다. 모든 검산 '''+str(len(checks))+'''개 PASS.\n\n- [고정 프로토콜](PROTOCOL.md)\n- [gap·감소율·부호 반전](GAP_REDUCTIONS.csv)\n- [Heading RMSE·bias·std·NEES·95%·range·XY 지표](SCORES.csv)\n- [prior/posterior 기하 분해](DECOMPOSITION.csv)\n- [검산](CHECKS.json)\n\nCUT_RT 및 추가 replay는 실행하지 않았다.\n'''
(p/'RESULTS_KO.md').write_text(text,encoding='utf-8');print(r[r.state=='x'][cols].to_string(index=False));print('checks',len(checks))
