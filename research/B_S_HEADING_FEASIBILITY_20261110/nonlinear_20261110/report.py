from runtime import *
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=ROOT.parent
read=lambda f:list(csv.DictReader(f.open(encoding='utf-8-sig')))
labels=read(p/'s_width_sweep_rows.csv');old=read(p/'s_width_sweep_summary.csv')
data=[];checks=[]
for route in ['R2','R4','R5']:
 a=dict(np.load(ROOT/(route+'_SCAN.npz')));rows=[r for r in labels if r['route']==route]
 assert len(rows)==len(a['t'])
 for key in ['minimum_residual','linear_minimum','widths','curve','half','target']:
  assert np.isfinite(a[key]).all(),(route,key)
 assert (a['widths']>=0).all() and (a['half']>0).all()
 for k,r in enumerate(rows):
  assert int(r['k'])==k and abs(float(r['t'])-a['t'][k])<1e-9
  data.append(dict(r,linear=float(a['linear_minimum'][k]),nonlinear=float(a['minimum_residual'][k]),widths=a['widths'][k]))
 checks.append(dict(route=route,parity=a['parity'].tolist(),refined=int(a['refined'].sum()),refinement_decision_changes=int(a['refine_changed'].sum())))
assert len(data)==3136 and len({(r['route'],r['k']) for r in data})==3136
policies=a['policy_names'].tolist();results=[];differences=[]
for route in ['ALL','R2','R4','R5']:
 rr=data if route=='ALL' else [r for r in data if r['route']==route]
 mask=np.array([int(r['accepted'])==1 for r in rr]);dh=np.array([float(r['S_increment_heading_se']) for r in rr]);ds=np.array([float(r['abs_full_clean_s_at_B']) for r in rr]);good=mask&(dh< -1e-10);bad=mask&(dh>1e-10);normal=mask&(ds<=.03)
 for j,policy in enumerate(policies):
  rejects={method:np.array([r[method]>r['widths'][j]+1e-12 for r in rr]) for method in ['linear','nonlinear']}
  for method,reject in rejects.items():
   rec=dict(route=route,policy=policy,method=method,helpful_total=int(good.sum()),helpful_protected=int((good&~reject).sum()),harmful_total=int(bad.sum()),harmful_detected=int((bad&reject).sum()),normal_total=int(normal.sum()),normal_protected=int((normal&~reject).sum()),rejected=int((mask&reject).sum()),net_heading_se=float(-dh[mask&reject].sum()),changed_vs_linear=int((mask&(reject!=rejects['linear'])).sum()))
   results.append(rec)
   if method=='linear':
    ref=next(o for o in old if o['route']==route and o['xy']=='False' and o['policy']==policy)
    assert rec['helpful_protected']==int(ref['helpful_protected']) and rec['harmful_detected']==int(ref['harmful_rejected']) and rec['normal_protected']==int(ref['clean_03_protected'])
  if route=='ALL':
   for r,l,n in zip(rr,rejects['linear'],rejects['nonlinear']):
    if l!=n:differences.append(dict(route=r['route'],k=r['k'],t=r['t'],accepted=r['accepted'],policy=policy,linear_reject=int(l),nonlinear_reject=int(n),linear_min=r['linear'],nonlinear_min=r['nonlinear'],width=r['widths'][j],S_increment_heading_se=r['S_increment_heading_se']))
def write(name,rs):
 if not rs:return
 with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rs[0]);w.writeheader();w.writerows(rs)
write('COMPARISON.csv',results);write('CHANGED_DECISIONS.csv',differences)
(ROOT/'CHECKS.json').write_text(json.dumps(dict(routes=checks,linear_reproduction='PASS',row_join='PASS',new_guard=False,new_recursive_run=False),indent=2))
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False})
fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
for method,style in [('linear','--o'),('nonlinear','-s')]:
 rr=[r for r in results if r['route']=='ALL' and r['method']==method and (r['policy']=='current' or r['policy'].startswith('width'))]
 for ax,key,total,title in [(axs[0],'normal_protected','normal_total','RF 정상 보호'),(axs[1],'helpful_protected','helpful_total','유익한 S 보호')]:
  ax.plot([100*(1-r[key]/r[total]) for r in rr],[100*r['harmful_detected']/r['harmful_total'] for r in rr],style,label='선형' if method=='linear' else '실제 비선형',alpha=.8)
  ax.set(xlabel=title+' 실패율 (%)',ylabel='해로운 S 검출률 (%)');ax.grid(alpha=.2);ax.legend()
fig.suptitle('동일 B OFF prior · 위치 고정 · gyro 95% 범위와 S 지지 집합 교차\n폭 100→75→50→25→10→0% | 분모: 정상 1,743 / 유익 1,735 / 해로움 1,390')
fig.savefig(ROOT/'COMPARISON.png',dpi=170)
print(json.dumps([r for r in results if r['route']=='ALL'],indent=2))
