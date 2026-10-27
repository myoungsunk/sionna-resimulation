from common import *
from helpers import cache_inputs
from decompose import arrays,metric_rows
import traceback
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
class AzimuthProvider:
 def __init__(self,model,donors,specs):self.model=model;self.donors=donors;self.specs=specs;self.k=0
 def batch(self,x,case):
  self.model.gt=np.stack([self.donors[s['donor']][self.k] for s in self.specs]);self.model.modes=['CUT_AZ']*len(x);self.model.explicit=None;self.k+=1
  return self.model.batch(x,case)
def main():
 assert json.loads((ROOT/'B_GATE.json').read_text())['status']=='PASS';preserve();_,model=models()
 cache=[r for r in cache_inputs() if r[0]['id'] in PRIMARY]
 # Function parity against archived GT-donor CUT_AZ: no new GT replay.
 audit=[]
 for case,bias,inp,ref,mask in cache:
  prev=load(PREVIOUS/'C'/f'{case["id"]}_{bias}.npz');check('GT_control_ids',prev['pose_id'],ref['pose_id'],0);check('GT_control_times',prev['t_s'],ref['t_s'],0)
  jj=[list(prev['names']).index('CUT_AZ_'+str(a)) for a in [0,1]]
  X=prev['prior'][:,jj].reshape(-1,4);truth=np.repeat(prev['truth_scoring_only'],2,axis=0);maxh=maxH=0.
  for start in range(0,len(X),48):
   S.stopcheck();xx=X[start:start+48];model.gt=truth[start:start+48];model.modes=['CUT_AZ']*len(xx);model.explicit=None;h,H=model.batch(xx,case)
   maxh=max(maxh,float(abs(h-prev['h'][:,jj].reshape(-1,2)[start:start+48]).max()));maxH=max(maxH,float(abs(H-prev['H'][:,jj].reshape(-1,2,4)[start:start+48]).max()))
  check('GT_provider_h',maxh,0,1e-12);check('GT_provider_H',maxH,0,1e-12);audit.append(dict(case=case['id'],bias=bias,n=len(X),h_max=maxh,H_max=maxH));S.event('TRANSFER_GT_PROVIDER_PASS',case=case['id'],bias=bias)
 write('TRANSFER_PROVIDER_GATE.json',dict(status='PASS',conditions=audit))
 specs=[dict(name=f'R{alpha}_AZ_{donor}',alpha=alpha,donor=donor) for alpha in [0,1] for donor in ['BB','MB']]
 scores=[];metrics=[];donor_records=[]
 for case,bias,inp,ref,mask in cache:
  donors={'BB':ref['prior'][:,0].copy(),'MB':ref['prior'][:,4].copy()};proxy=AzimuthProvider(model,donors,specs)
  out=E.replay(case,inp,proxy,specs,mask);assert proxy.k==len(inp['t'])
  scores.extend(E.score('TRANSFER',case,bias,inp,out,specs,0));pd.DataFrame(scores).to_csv(ROOT/'TRANSFER_SCORES.csv',index=False)
  z=dict(t_s=inp['t'],truth_scoring_only=ref['truth_scoring_only'],**out);a,_,_,_=arrays(z,case);metrics.extend(metric_rows(a,case,bias,[s['name'] for s in specs],[s['alpha'] for s in specs]));pd.DataFrame(metrics).to_csv(ROOT/'TRANSFER_DECOMPOSITION.csv',index=False)
  donor_records.append(dict(case=case['id'],bias=bias,source=str(E1/'E1'/f'{case["id"]}_{bias}.npz'),field='prior',BB_index=0,MB_index=4,packet_count=len(inp['t']),same_packet=True))
  write('TRANSFER_DONORS.json',donor_records);write('TRANSFER_CHECKS.json',S.checks);S.event('TRANSFER_CASE_PASS',case=case['id'],bias=bias)
 base=pd.read_csv(E1/'SCORES.csv');old=pd.read_csv(PREVIOUS/'C_SCORES.csv');ratios=[];cells=[]
 for (case,bias),gg in pd.DataFrame(scores).groupby(['case','bias']):
  g=gg.set_index('arm');orig=base[(base.stage=='E1')&(base.case==case)&(base.bias==bias)].set_index('alpha');eBB=float(orig.loc[0,'heading_bias_deg']);eMB=float(orig.loc[1,'heading_bias_deg']);Ge=eMB-eBB
  q={name:float(g.loc[name,'heading_bias_deg']) for name in g.index};Gc=q['R1_AZ_MB']-q['R0_AZ_BB'];forward=q['R0_AZ_MB']-q['R0_AZ_BB'];backward=q['R1_AZ_MB']-q['R1_AZ_BB']
  rec=dict(case=case,bias=bias,E1_BB=eBB,E1_MB=eMB,control_BB=q['R0_AZ_BB'],control_MB=q['R1_AZ_MB'],BB_control_minus_E1=q['R0_AZ_BB']-eBB,MB_control_minus_E1=q['R1_AZ_MB']-eMB,G_E1=Ge,G_control=Gc,forward_deg=forward,backward_deg=backward)
  for name,den in [('E1',Ge),('control',Gc)]:
   ok=abs(den)>=.01;fr=forward/den if ok else None;br=backward/den if ok else None
   rec['forward_ratio_'+name]=fr;rec['backward_ratio_'+name]=br;rec['sufficiency_'+name]=bool(fr>=.7 and br>=.7) if ok else None
  rec['denominator_disagreement']=rec['sufficiency_E1']!=rec['sufficiency_control'];ratios.append(rec)
  for alpha in [0,1]:
   for donor in ['GT','BB','MB']:
    row=old[(old.case==case)&(old.bias==bias)&(old.arm==f'CUT_AZ_{alpha}')].iloc[0] if donor=='GT' else g.loc[f'R{alpha}_AZ_{donor}']
    cells.append(dict(case=case,bias=bias,range_alpha=alpha,azimuth_source=donor,heading_bias_deg=float(row['heading_bias_deg']),heading_rmse_deg=float(row['heading_rmse_deg']),provenance='reused C CUT_AZ' if donor=='GT' else 'new frozen-prior transplant'))
 pd.DataFrame(ratios).to_csv(ROOT/'TRANSFER_RATIOS.csv',index=False);pd.DataFrame(cells).to_csv(ROOT/'TRANSFER_SIX_CELLS.csv',index=False)
 preserve();write('TRANSFER_GATE.json',dict(status='PASS',conditions=6,new_replay_cells=24,reused_GT_cells=12));S.event('TRANSFER_COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:write('TRANSFER_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
