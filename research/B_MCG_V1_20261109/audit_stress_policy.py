"""Evaluate the predeclared tau grid on the fixed R5 clean-return witness.

No profile is refit, no threshold is selected, and no policy is changed here.
This prevents a tau=3 regression result being generalized to other candidates.
"""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from experiment import context,packet_for,config_for,read_npz
from mcg import weights
from stress_source import action_comparison,save,clean_json


def main(a):
    parent=json.loads((a.stress/'SOURCE_STRESS_SUMMARY.json').read_text())
    current_sha=hashlib.sha256(Path(__file__).with_name('mcg.py').read_bytes()).hexdigest()
    assert parent['implementation_sha256']==current_sha
    rows=json.loads((a.stress/'R5_SOURCE_STRESS.json').read_text())['rows']
    row=next(r for r in rows if r['name']=='COHERENT_WRONG_HISTORY_IDEAL_RETURN')
    r45,core,online,model,hashes=context()
    packet,_,_=packet_for(r45,'R5','B_FROZEN',a.archives)
    tr=read_npz(a.archives/'R5/R5_B_FROZEN.npz')
    ht=read_npz(a.model_truth/'R5_htruth.npz');k=row['k'];truth=ht['truth'][k]
    x=np.r_[truth,0.]+np.array([.1,-.1,.05,0.]);P=np.diag([.01,.01,np.radians(5)**2,np.radians(.1)**2])
    h,H=model.batch(x[None],r45.SPEC);h=h[0];H=H[0]
    z=ht['htruth'][k]+packet['muMB'][k]
    score={'status':row['profile_status'],'reason':row['profile_reason'],
        'valid_channels':np.asarray(row['valid_channels'],bool),'scores':np.asarray(row['scores'])}
    report={'scope':'Fixed-source-model clean-return witness, predeclared tau sensitivity, not calibration.',
        'route':'R5','k':k,'implementation_sha256':current_sha,
        'fixed_profile_scores':score['scores'],'legacy_current_gate':row['legacy_current_gate'],'rows':[]}
    for tau in [1.5,2.,3.,4.]:
        cfg=config_for(tau);beta,status=weights(score,cfg)
        actual=action_comparison(x,P,h,H,z,packet['muMB'][k],tr['Reff'][k],beta,truth,row['legacy_current_gate'])
        report['rows'].append({'tau':tau,'beta':beta,'status':status,'actual':actual})
    save(a.out,report)
    print(json.dumps(clean_json({'fixed_profile_scores':score['scores'],'rows':[{'tau':r['tau'],'beta':r['beta'],
        'lost_beneficial_gain_ratio_heading_xy':r['actual']['lost_beneficial_gain_ratio']} for r in report['rows']]})))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--model-truth',type=Path,required=True);p.add_argument('--stress',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
