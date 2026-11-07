import json,csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
B=Path(__file__).resolve().parent;O=B/'results';A=B/'analysis'
rows=json.loads((O/'SUMMARY.json').read_bytes())['rows']
with (A/'SENSITIVITY_AGGREGATE.csv').open() as f:sens=list(csv.DictReader(f))
fig,axes=plt.subplots(2,4,figsize=(15,7),layout='constrained')
levels=['B0','L0','L1','L2'];colors={'fn':'#2475b0','fp':'#d64b40','both':'#8056a7'}
for j,lv in enumerate(levels):
 ax=axes[0,j]
 for gate,style in [(False,'--'),(True,'-')]:
  r=sorted([r for r in rows if r['group']=='rf' and r['level']==lv and r['gated']==gate],key=lambda r:r['tau'])
  ax.plot([v['tau'] for v in r],[v['heading_rmse_deg'] for v in r],style+'o',label='RF + NIS' if gate else 'RF only')
 for name,color in [('s4','#555555'),('heading','#2a9456'),('dr','#999999')]:
  v=next(r for r in rows if r['group']=='baseline' and r['level']==lv and r['name']==name)
  ax.axhline(v['heading_rmse_deg'],color=color,linestyle=':',label=name)
 ax.set(title=f'{lv}: RF contamination selection',xlabel='|Full - LoS| threshold',ylabel='Heading RMSE (deg)',yscale='log');ax.grid(alpha=.2)
 if j==0:ax.legend(fontsize=7)
 ax=axes[1,j]
 for kind in ('fn','fp','both'):
  for pattern,style in [('iid','-'),('burst','--')]:
   r=sorted([r for r in sens if r['level']==lv and r['kind']==kind and r['pattern']==pattern],key=lambda r:float(r['rate']))
   ax.plot([float(v['rate'])*100 for v in r],[float(v['heading_median']) for v in r],style+'o',color=colors[kind],label=kind.upper()+' '+pattern)
 ax.set(title=f'{lv}: injected decision errors',xlabel='Nominal conditional error probability (%)',ylabel='Heading RMSE (deg)',yscale='log');ax.grid(alpha=.2)
 if j==0:ax.legend(fontsize=7,ncol=2)
fig.suptitle('PALO-GAP-002 | R2 seed0 diagnostic, not independent generalization\nSensitivity: median of 5 artificial error seeds; correlated RF/time samples',fontsize=12)
fig.savefig(A/'RF_AND_ERROR_SENSITIVITY.png',dpi=170)
fig.savefig(A/'RF_AND_ERROR_SENSITIVITY.pdf')
plt.close(fig)
print('PLOTS_SAVED')
