"""Read-only provenance of B mean mismatch, using archived E1 arrays only."""
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'DS_NONLINEAR_E1_E4_20261027_01a1775b'/'E1'
rows=[]
for f in sorted(OLD.glob('*_B0.npz')):
 with np.load(f) as b,np.load(OLD/(f.stem[:-2]+'L2.npz')) as l:
  db=b['mu'][:,4,0]-b['mu'][:,0,0];dl=l['mu'][:,4,0]-l['mu'][:,0,0];mb=b['acc'][:,0];ml=l['acc'][:,0]
  rows.append(dict(case=f.stem[:-3],B0_accepted=int(mb.sum()),L2_accepted=int(ml.sum()),mask_differences=int((mb!=ml).sum()),delta_mu_max_difference_m=float(abs(db-dl).max()),c_B0=float(db[mb].mean()),c_L2=float(dl[ml].mean()),c_difference_m=float(db[mb].mean()-dl[ml].mean())))
if __name__=='__main__':pd.DataFrame(rows).to_csv(ROOT/'B_MASK_AUDIT.csv',index=False)
