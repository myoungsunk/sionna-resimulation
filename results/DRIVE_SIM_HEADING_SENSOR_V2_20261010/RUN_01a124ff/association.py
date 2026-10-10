from pathlib import Path
import json,time
import numpy as np,pandas as pd
from scipy.stats import rankdata
from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score
J=Path('/job');OUT=J/'ASSOCIATION';OUT.mkdir(exist_ok=True)
def corr(a,b):
 a=a-a.mean(axis=-1,keepdims=True);b=b-b.mean(axis=-1,keepdims=True);den=np.sqrt((a*a).sum(axis=-1)*(b*b).sum(axis=-1));return np.divide((a*b).sum(axis=-1),den,out=np.full(np.shape(den),np.nan),where=den>0)
def main():
 start=time.time();data=pd.concat([pd.read_csv(p) for p in sorted((J/'LABELS').glob('*.csv.gz'))],ignore_index=True);cols=[c for c in data if c.startswith(('D','P','K_'))];data=data[data.available];rows=[];linear=[];rng=np.random.default_rng(20261010)
 for route in ['R2','R4','R5']:
  test=data[data.route==route];train=data[data.route!=route]
  for col in cols:
   station=test.groupby('station_group')[[col,'heading_error_deg','correct_5deg','K_distance','K_slope_per_rad']].mean();station=station.loc[:,~station.columns.duplicated()].replace([np.inf,-np.inf],np.nan).dropna();x=station[col].to_numpy();y=station.heading_error_deg.to_numpy();z=station.correct_5deg.to_numpy();idx=rng.integers(0,len(x),(1000,len(x)));cp=corr(x[idx],y[idx]);rs=corr(rankdata(x)[idx],rankdata(y)[idx]);controls=np.c_[np.ones(len(station)),station.K_distance,station.K_slope_per_rad];rx=x-controls@np.linalg.lstsq(controls,x,rcond=None)[0];ry=y-controls@np.linalg.lstsq(controls,y,rcond=None)[0]
   rows.append({'route':route,'feature':col,'unit':'station means; headings and seeds clustered','n_station':len(x),'pearson_station':float(corr(x,y)),'pearson_ci_low':float(np.nanquantile(cp,.025)),'pearson_ci_high':float(np.nanquantile(cp,.975)),'spearman_station':float(corr(rankdata(x),rankdata(y))),'spearman_ci_low':float(np.nanquantile(rs,.025)),'spearman_ci_high':float(np.nanquantile(rs,.975)),'correct_fraction_association_station':float(corr(x,z)),'partial_pearson_distance_slope_descriptive':float(corr(rx,ry)),'bootstrap_replicates':1000,'not_causal':True})
   a=train[[col,'heading_error_deg']].replace([np.inf,-np.inf],np.nan).dropna();b=test[[col,'heading_error_deg']].replace([np.inf,-np.inf],np.nan).dropna();mu=a[col].mean();sd=a[col].std();xx=(a[col]-mu)/sd if sd>0 else np.zeros(len(a));coef=np.linalg.lstsq(np.c_[np.ones(len(a)),xx],a.heading_error_deg,rcond=None)[0];pred=coef[0]+coef[1]*((b[col]-mu)/sd if sd>0 else np.zeros(len(b)));linear.append({'held_out_route':route,'feature':col,'train_mean':mu,'train_std':sd,'linear_intercept':coef[0],'linear_slope_per_training_sd':coef[1],'held_out_mae_deg':mean_absolute_error(b.heading_error_deg,pred),'held_out_rmse_deg':np.sqrt(mean_squared_error(b.heading_error_deg,pred)),'held_out_r2':r2_score(b.heading_error_deg,pred),'not_probability_calibration':True})
 pd.DataFrame(rows).to_csv(OUT/'STATION_ASSOCIATION_CI.csv',index=False);pd.DataFrame(linear).to_csv(OUT/'LINEAR_HELD_OUT.csv',index=False);risk=[]
 for route in ['R2','R4','R5']:
  p=pd.read_csv(J/'RELIABILITY'/f'{route}_HELD_OUT_PREDICTIONS.csv.gz');y=p.correct_5deg.astype(int).to_numpy()
  for col in [c for c in p if c.startswith('q_')]:
   q=p[col].to_numpy();accepted=q>=.5;high=q>=.9;risk.append({'route':route,'model':col,'available_n':len(p),'accepted_at_half':int(accepted.sum()),'false_accept_fraction_at_half':float((1-y[accepted]).mean()) if accepted.any() else None,'high_confidence_n':int(high.sum()),'high_confidence_false_accept_fraction':float((1-y[high]).mean()) if high.any() else None,'no_match_ambiguity_excluded_before_this_table':True})
 pd.DataFrame(risk).to_csv(OUT/'FALSE_ACCEPT.csv',index=False);(OUT/'STATUS.json').write_text(json.dumps({'state':'completed','seconds':time.time()-start,'bootstrap_unit':'station within held-out route; not independent environments','constant_prevalence_calibration_slope':'not identifiable; ignore regression slope for prevalence model'},indent=2));print('completed association',time.time()-start,flush=True)
if __name__=='__main__':main()
