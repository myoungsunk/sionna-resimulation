from pathlib import Path
import csv,json,math,gzip
from collections import defaultdict
B=Path(r'D:/SLAM_bot/artifacts/EKF3_P0_VERIFY_20261013_01a132b7/DIAGNOSTICS_701b8d2')
O=B/'OUTPUT_D0_D4_SEED0'
def rows(p):
 with (gzip.open(p,'rt',newline='') if str(p).endswith('.gz') else p.open(newline='')) as f:return list(csv.DictReader(f))
groups=defaultdict(list)
for r in rows(O/'D0_D1_METRICS.csv'):groups[(r['channel'],r['range_model'],r['arm'])].append(r)
pooled=[]
for (ch,model,arm),rs in groups.items():
 n=sum(int(r['n']) for r in rs)
 rec=dict(channel=ch,model=model,arm=arm,n=n)
 for out,col in [('heading_rmse_deg','rmse_heading_deg'),('xy_rmse_m','rmse_xy_m')]:rec[out]=math.sqrt(sum(int(r['n'])*float(r[col])**2 for r in rs)/n)
 pooled.append(rec)
ranges=defaultdict(list)
for r in rows(O/'D4_RANGE_RESIDUAL_BY_DISTANCE.csv'):ranges[(r['channel'],r['correction'])].append(r)
rpool=[]
for (ch,model),rs in ranges.items():
 n=sum(int(r['n']) for r in rs);rpool.append(dict(channel=ch,model=model,n=n,rms_m=math.sqrt(sum(int(r['n'])*float(r['rms_residual_m'])**2 for r in rs)/n)))
pol=rows(O/'D3_FLAT_FFD_MP_AND_POLARIZATION.csv.gz');pol=[r for r in pol if r['channel']=='full']
polres={}
for k in ['e_s_mp','s_tap_selection_effect','s_channel_interference_same_tap','e_flat_m','e_ffd_m','e_mp_m','e_range_B_full_m']:
 a=[float(r[k]) for r in pol if r[k] and math.isfinite(float(r[k]))];mean=sum(a)/len(a)
 polres[k]={'n':len(a),'mean':mean,'rms':math.sqrt(sum(x*x for x in a)/len(a)),'sd':math.sqrt(sum((x-mean)**2 for x in a)/len(a))}
res=dict(aggregation='sample-weighted pooled RMSE; evaluation t>=30s',one_step=pooled,range_residual=rpool,polarization=polres,scientific_PASS=False)
(B/'D04_POOLED_SUMMARY.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))
