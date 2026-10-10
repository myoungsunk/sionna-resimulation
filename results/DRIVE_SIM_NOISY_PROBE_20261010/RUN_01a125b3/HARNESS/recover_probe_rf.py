"""Exact offline reconstruction of receiver innovations; no RF solver or filter replay."""
import argparse,json,time
from pathlib import Path
import numpy as np
import body_controls as C
from qclean_uwb.drivesim import observation as O
p=argparse.ArgumentParser();p.add_argument('--batch',choices=['existing7','new5'],required=True);a=p.parse_args();existing={x['case'] for x in json.loads((C.B/'CASES.json').read_text())};start=time.time();count=0;maxima={'power':0.,'s':0.,'range':0.};failures=[]
for casefolder in C.OUT.iterdir():
 case=casefolder.name
 if (case in existing)!=(a.batch=='existing7'):continue
 poses,full,los,groups=C.casepack(case)
 for folder in casefolder.iterdir():
  if not (folder/'RF_PACKETS.npz').exists():continue
  gi,d,seed,snr=[int(x[1:]) if x.startswith(('g','d','s')) and not x.startswith('snr') else int(x[3:]) for x in folder.name.split('_')]
  z=np.load(folder/'RF_PACKETS.npz');ids=z['pose_id'];var=float(z['noise_variance']);rng=np.random.default_rng(np.random.SeedSequence([20261010,int(case[1]),0 if '_aA_' in case else 1,d,seed,snr,int(ids[0]),811]));noise=np.sqrt(var/2)*(rng.standard_normal((3,257,2))+1j*rng.standard_normal((3,257,2)))
  hf=np.asarray(full[ids]).copy();hl=np.asarray(los[ids]).copy();hf[:,:,:,0]+=noise;hl[:,:,:,0]+=noise;obs=O.observe(hf,C.freq,None,None,threshold=O.detection_threshold(var))
  for key,actual,expected in [('power',obs['power'],np.column_stack([z['P1_firstpath'],z['P2_firstpath']])),('s',obs['s'],z['s_firstpath']),('range',obs['range_m'],z['range_m'])]:
   finite=np.isfinite(actual)&np.isfinite(expected);err=float(np.max(abs(actual[finite]-expected[finite]))) if finite.any() else 0.;maxima[key]=max(maxima[key],err)
   if not np.array_equal(np.isfinite(actual),np.isfinite(expected)) or err>1e-12:failures.append({'folder':str(folder),'key':key,'difference':err})
  if not np.array_equal(obs['index'],z['selected_tap']):failures.append({'folder':str(folder),'key':'tap'})
  path=folder/'RF_RAW_RECONSTRUCTED.npz';assert not path.exists();np.savez_compressed(path,H_full_TX0_noisy=hf[:,:,:,0],H_los_TX0_noisy=hl[:,:,:,0],thermal_innovation_TX0=noise,CIR_amplitude_full=abs(O.cir_batch(hf[:,:,:,0])),CIR_amplitude_los=abs(O.cir_batch(hl[:,:,:,0])),freqs_hz=C.freq,pose_id=ids,time_rf_s=z['time_rf_s'],noise_variance=var,reconstruction_status=np.array('offline deterministic recovery, exact seed stream; not new RF; compare RF_PACKETS'),TX_port=np.array(0),RX_port_order=np.array(['LP_plus45','LP_minus45']))
  count+=1
r={'passed':not failures,'recovered_packet_groups':count,'max_abs_difference':maxima,'failures':failures,'seconds':time.time()-start,'method':'identical saved noise seed and frozen H; no estimator or solver invocation; old RF_PACKETS retained'};(C.J/f'RAW_RF_RECOVERY_{a.batch}.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True);assert r['passed']
