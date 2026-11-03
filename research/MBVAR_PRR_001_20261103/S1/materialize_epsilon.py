"""Generate evaluator-only epsilon = z_s - h_s(x_true) - mu_s. No runtime imports these files."""
import json
import numpy as np
import parity as p
def main():
 root=p.cache.parent/'evaluator_epsilon_r1';root.mkdir(exist_ok=True)
 receipts={}
 for route in ('R4','R5'):
  for bias in ('B0','L2'):
   truth_npz=p.cache.parent/'evaluator_truth'/f'{route}_aB_m0_{bias}.npz'
   assert p.b.sha(truth_npz)==p.lock['evaluator_truth/'+truth_npz.name]
   with np.load(truth_npz) as truth:
    gt=np.column_stack((truth['truth'],np.zeros(len(truth['t']))));ids=truth['pose_id']
    h=np.concatenate([p.b.model.batch(gt[k:k+48],p.spec,gradient=False)[0] for k in range(0,len(gt),48)])
   for ch in ('Full','Native_LoS'):
    key=f'{route}_aB_m0_{bias}_{ch}';pk=p.read(key);assert np.array_equal(ids,pk['pose_id'])
    eps=pk['z'][:,1]-h[:,1]-pk['muMB'][:,1];assert np.isfinite(eps).all()
    path=root/(key+'.npz');np.savez_compressed(path,pose_id=ids,htruth_s=h[:,1],epsilon_s=eps)
    receipts[path.name]=p.b.sha(path)
 (p.s/'EPSILON_INPUTS.json').write_text(json.dumps(receipts,indent=2))
if __name__=='__main__':main()
