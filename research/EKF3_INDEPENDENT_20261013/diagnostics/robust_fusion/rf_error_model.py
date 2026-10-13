"""Frozen learned constant RF mean and Gaussian scale; joint block Huber."""
import json,hashlib
from pathlib import Path
import numpy as np

def load_models(structure):
 structure=Path(structure);gate=json.loads((structure/'RF_RESIDUAL_STRUCTURE_GATE.json').read_text())
 p=structure/'RF_TRAINING_MOMENTS.json'
 assert hashlib.sha256(p.read_bytes()).hexdigest()==gate['output_sha256'][p.name]
 result={}
 for r in json.loads(p.read_text()):
  cov=np.diag(np.diag(r['total_empirical_covariance']))
  if np.linalg.eigvalsh(cov).min()<=0:raise RuntimeError('Invalid trained covariance; no floor')
  result[(r['heldout_route'],r['channel'],r['range_model'])]=(np.array(r['mean']),cov)
 return result,{'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'off_diagonal':'ZERO_UNVALIDATED','total_scale':'diagonal of ddof=1 training residual covariance','loss':'block Huber whitened residual norm','delta':1.345,'mean':'constant outer-route training mean','full_likelihood_equality_claimed':False,'scientific_PASS':False}
