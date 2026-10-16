"""S0-only versioned pole candidate validation. Zero old-source changes."""
import hashlib, json, pathlib, sys
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"POLE_LUT_SINGULARITY_20261016"))
from pole_lut_fix import candidate_pole_consistent_table
BASE=pathlib.Path(__file__).resolve().parents[2]
SRC=BASE/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy"
ORIGINAL="711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079"
EXPECTED="e6db187d2b8f0507ab588affb0bae66d26d2b778ce9244c36154342800f33f0b"
def sha(x):
 h=hashlib.sha256()
 with open(x,"rb") as f:
  for b in iter(lambda:f.read(2**20),b""):h.update(b)
 return h.hexdigest()
def go(ok,name):
 if not ok:raise AssertionError(name)
 print("PASS",name,flush=True)
go(SRC.exists(),"original_lut_present")
go(sha(SRC)==ORIGINAL,"original_lut_sha")
s=np.load(SRC,allow_pickle=False)
go(s.shape==(46,180,180) and s.dtype==np.float64,"dtype_shape")
new=candidate_pole_consistent_table(s)
go(np.array_equal(new[1:],s[1:]),"exact_offpole")
go(not np.array_equal(new[0],s[0]),"theta0_changed")
go(np.isfinite(new).all() and np.max(abs(new))<=1+1e-12,"physical_range")
go(np.max(abs(new[0]-np.roll(new[0],180,axis=0)))==0,"azimuth_periodic")
out=pathlib.Path("s0_pole_candidate");out.mkdir(exist_ok=True)
target=out/"hs_lut_pole_corrected_candidate.npy"
np.save(target,new,allow_pickle=False)
go(sha(target)==EXPECTED,"candidate_sha")
(out/"S0_FINAL.json").write_text(json.dumps({"status":"AUDITED_CANDIDATE_NUMERIC_PASS","original_sha256":ORIGINAL,"candidate_sha256":sha(target),"offpole_bit_exact":True,"production_approved":False},indent=2))
print("S0_FINISHED; no RF/FFD regeneration or recursive scientific claims")
