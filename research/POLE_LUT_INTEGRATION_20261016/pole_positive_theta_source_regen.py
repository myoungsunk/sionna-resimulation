"""Source-FFD regeneration of pole theta=0 layer, when original banks exist.

This code is NOT considered run/validated until both 248MB LP banks with
the exact frozen SHA-256 values are supplied. It never overwrites the original.
For a positive epsilon polar angle, azimuth is well defined; map the response
to the theta=0 LUT layer as a limiting approximation. Vary epsilon and verify
numerical convergence before scientific acceptance.
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy"
SRC=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
BANK_DIGEST={
 "LP_plus45_bank.npz":"b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
 "LP_minus45_bank.npz":"39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"}
ORIG_LUT_SHA="711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079"

def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--bank-dir",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True)
 p.add_argument("--epsilon-deg",type=float,default=.02)
 p.add_argument("--canary-only",action="store_true")
 a=p.parse_args()
 if not(0<a.epsilon_deg<=.1):raise ValueError("REQUIRE_POSITIVE_SMALL_ANGLE_0_0p1")
 if sha(ORIGINAL)!=ORIG_LUT_SHA:raise RuntimeError("ORIGINAL_LUT_SHA_MISMATCH")
 s=np.load(ORIGINAL,allow_pickle=False)
 if s.shape!=(46,180,180):raise RuntimeError("ORIGINAL_LUT_SHAPE_CHANGED")
 for name,digest in BANK_DIGEST.items():
  f=a.bank_dir/name
  if not f.exists():raise FileNotFoundError("SOURCE_BANK_MISSING:"+str(f))
  if sha(f)!=digest:raise RuntimeError("SOURCE_FFD_BANK_SHA_MISMATCH:"+name)
 sys.path.insert(0,str(SRC))
 from qclean_uwb.drivesim.pattern_apply import Bank
 from qclean_uwb.drivesim.hs_lut import los_s_direct
 banks=[]
 for name in BANK_DIGEST:
  with np.load(a.bank_dir/name,allow_pickle=False) as f:
   banks.append(Bank({k:f[k] for k in f.files}))
 if not np.array_equal(banks[0].freqs_hz,banks[1].freqs_hz):
  raise RuntimeError("RX_TX_FREQUENCIES_NOT_IDENTICAL")
 az=np.arange(-180,180,2,dtype=float)
 src=s.copy()
 if a.canary_only:
  samples=[(x,y) for x in az[::18] for y in az[::18]]
 else:
  samples=[(x,y) for x in az for y in az]
 for counter,(pt,pr) in enumerate(samples):
  j=int((pt+180)/2);k=int((pr+180)/2)
  src[0,j,k]=los_s_direct(banks,a.epsilon_deg,pt,pr,measure="fp")
  if counter and counter%3600==0:print(json.dumps({"done":counter,"of":len(samples)}),flush=True)
 if not a.canary_only:
  if not np.array_equal(src[1:],s[1:]):raise RuntimeError("ORIGINAL_NONPOLE_LAYER_CHANGED")
  if np.isnan(src).any():raise RuntimeError("POLE_NAN")
  if max(abs(src[0].ravel()))>1+1e-10:raise RuntimeError("POL_RATIO_OUT_OF_RANGE")
  if a.out.resolve()==ORIGINAL.resolve():raise RuntimeError("ORIGINAL_LUT_OVERWRITE_FORBIDDEN")
  a.out.parent.mkdir(parents=True,exist_ok=True)
  np.save(a.out,src)
 meta={"status":"SOURCE_FFD_GENERATED_LIMIT_CANARY" if a.canary_only else "SOURCE_FFD_THETA_POSITIVE_LAYER_GENERATED_UNCALIBRATED",
    "theta_eps_deg":a.epsilon_deg,"original_sha":sha(ORIGINAL),
    "ffd_banks":BANK_DIGEST,"n_tested":len(samples),
    "candidate_sha":sha(a.out) if not a.canary_only else None,
    "scientific_pass":False,
    "requires":["epsilon convergence sweep across independent original FFD banks",
       "9519 complex LoS ratio/Jacobian validation",
       "held-out clean LoS and Full recursive filtering",
       "independent 3D FFD convention audit"]}
 if not a.canary_only:
  a.out.with_suffix(".manifest.json").write_text(json.dumps(meta,indent=2)+"\n")
 print(json.dumps(meta,indent=2))
if __name__=="__main__":main()
