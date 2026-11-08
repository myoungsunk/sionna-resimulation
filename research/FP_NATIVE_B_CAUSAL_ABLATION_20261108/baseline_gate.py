#!/usr/bin/env python3
"""Native/B recursive parity gate before any new ablation; no evaluator access."""
import argparse,json,traceback
from pathlib import Path
from fp_ns_ablation import load_original_replay,identical_input_condition,json_dump,rehash
from replay_evidence import replay_checkpoint,baseline_parity

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--routes',nargs='+',default=['R2','R4','R5'],choices=['R2','R4','R5']);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    r45,core,online,model,hashes=load_original_replay(a.repo.resolve());checks={}
    try:
        for route in a.routes:
            case=route+'_B0_Full_10';on=r45.data(case,'online.npz')
            B,n,zN,zB=identical_input_condition(on,r45,case)
            controls={k:on[k] for k in ['ds','gy','dt']};controls['x0']=on['x0'][:3]
            traces={}
            for arm,z in [('NN',zN),('BB',zB)]:
                packet=dict(on);packet['z']=z
                print('BASELINE_START',route,arm,flush=True)
                traces[arm]=replay_checkpoint(a.out/(route+'_'+arm+'.npz'),packet,controls,core,online,model,r45.SPEC,hashes)
            checks[route]=baseline_parity(case,on,traces['NN'],traces['BB'],r45.ROOT/'R45_RUN_001'/(route+'_TRACE.npz'))
            json_dump(a.out/(route+'_PASS.json'),dict(status='PASS',checks=checks[route]))
            print('BASELINE_PASS',route,max(checks[route].values()),flush=True)
        files={p.name:rehash(p) for p in a.out.glob('*.npz')}
        json_dump(a.out/'BASELINE_PASS.json',dict(status='PASS',routes=a.routes,checks=checks,source_hashes=hashes,checkpoint_sha256=files,truth_access=False,tolerance=1e-10))
    except BaseException as e:
        json_dump(a.out/'FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
if __name__=='__main__':main()
