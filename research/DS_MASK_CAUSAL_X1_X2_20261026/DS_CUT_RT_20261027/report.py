from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
p=Path(__file__).resolve().parent
assert json.loads((p/'GATE.json').read_text())['status']=='PASS'
a=pd.read_csv(p/'DECOMPOSITION.csv');base=pd.read_csv(p.parent/'DS_TANGENT_LEDGER_20261027/STEP0_STATS.csv');rows=[]
for (case,bias,state),q in a.groupby(['case','bias','state']):
 b=base[(base.case==case)&(base.bias==bias)&(base.state==state)&(base.source=='E1')].set_index('arm');q=q.set_index('arm');row=dict(case=case,bias=bias,state=state)
 for metric,old,new,scale in [('beta','beta_bias_deg','beta_bias',1),('heading','heading_bias_deg','psi_bias',1),('et','et_bias_cm','et_bias',1),('er','er_bias_cm','er_bias',1)]:
  g0=float(b.loc['A1',old]-b.loc['A0',old]);g=float(q.loc['A1',new]-q.loc['A0',new]);valid=abs(g0)>=(.01 if metric in ['beta','heading'] else 1e-10);fm=1-abs(g)/abs(g0) if valid else np.nan
  row.update({metric+'_G_E1':g0,metric+'_G_CUT_RT':g,metric+'_f_magnitude':fm,metric+'_f_signed':1-g/g0 if valid else np.nan,metric+'_sign_flip':bool(g*g0<0),metric+'_decision':'undefined' if not valid else 'support' if fm>=.7 else 'partial' if fm>=.3 else 'insufficient'})
 rows.append(row)
r=pd.DataFrame(rows);r.to_csv(p/'GAP_REDUCTIONS.csv',index=False)
checks=json.loads((p/'CHECKS.json').read_text());assert all(x['pass_check'] for x in checks)
def table(df):
 out=['| '+' | '.join(df.columns)+' |','| '+' | '.join(['---']*len(df.columns))+' |']
 for row in df.itertuples(index=False,name=None):out.append('| '+' | '.join(f'{v:.4f}' if isinstance(v,float) else str(v) for v in row)+' |')
 return '\n'.join(out)
cols=['case','bias','beta_G_E1','beta_G_CUT_RT','beta_f_magnitude','beta_decision','heading_G_E1','heading_G_CUT_RT','heading_f_magnitude','heading_decision','et_G_E1','et_G_CUT_RT']

print(r[r.state=='x'][cols].to_string(index=False));print('checks',len(checks))
