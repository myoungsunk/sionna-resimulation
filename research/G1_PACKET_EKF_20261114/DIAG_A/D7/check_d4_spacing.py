import json,sys
from pathlib import Path
import numpy as np
def f(x): return [float(y) for y in np.percentile(x[x>1e-8],[0,25,50,75,95,100])]
r=Path("/diag/diag003_work/results")
for path in sorted(r.glob("*/D4_PACKET_WINDOW.npz")):
 with np.load(path) as a:
  d=np.diff(a["distance_m"]); y=np.abs((np.diff(a["pose"][:,2])+np.pi)%(2*np.pi)-np.pi)
  meta=json.loads(path.with_name("D4_SPATIAL.json").read_text())
  print(path.parent.name, "dist_nonzero",f(d),"yaw_deg_nonzero",f(np.degrees(y)), list(meta["distance_variogram"]["bins"][0].keys()))
