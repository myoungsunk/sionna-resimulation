import pathlib,hashlib,json,subprocess,io,sys
import numpy as np,pandas as pd,joblib
from sklearn import __version__ as sklearn_version
base=pathlib.Path("/mnt/d/codex/MBVAR_PRR_001_20261103")
root=base/"research/MBVAR_PRR_001_20261103"
out=root/"A0_R3_REFIT"
old=pathlib.Path("/mnt/d/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849")
cache=pathlib.Path("/mnt/d/codex/MBVAR_PRR_001_20261103_inputs")
src=old/"p2"
rev="902ddcaf0f8e59734bb8026d3bcdc36eab506a27"
def sha(b):return hashlib.sha256(b).hexdigest()
def gitfile(path):return subprocess.check_output(["git","-c","safe.directory=*","-C",str(base),"show",rev+":"+path])
lock=json.loads((out/"TRAINING_LOCK.json").read_bytes())
native_lock=json.loads((out/"NATIVE_LOCK.json").read_bytes())
for f,h in native_lock.items():assert sha((out/f).read_bytes())==h
manifest_path="research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
manifest=json.loads((src/manifest_path).read_bytes())
featurepath=old/"p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz"
assert sha(featurepath.read_bytes())==lock["features_sha256"]
feature=pd.read_csv(featurepath)
cols=lock["columns"];existing=cols[:16];offsets=[-8,-4,-2,-1,1,2,4,8]
assert cols[16:]==["ds_%+d"%i for i in offsets]
tables=[]
for case in manifest["cases"]:
 samples=json.loads((src/case["samples_path"]).read_bytes())
 ids=np.array([s["pose_id"] for s in samples])
 H=np.load(src/case["full_path"],mmap_mode="r",allow_pickle=False)
 delta={o:[] for o in offsets}
 sf=[]
 for start in range(0,len(ids),128):
  h=np.array(H[start:start+128,:,:,0],dtype=np.complex128)
  nf=h.shape[1];nt=4*nf
  window=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
  cir=np.fft.ifft(h*window[None,:,None],n=nt,axis=1)*nf
  amp=np.abs(cir);power=amp**2
  ii=np.arange(len(h));strong_port=amp.max(axis=1).argmax(axis=1)
  strong=amp[ii,:,strong_port]
  fp=(strong>=.3*strong.max(axis=1)[:,None]).argmax(axis=1)
  pol={}
  for off in [0]+offsets:
   ind=fp+off;ok=(ind>=0)&(ind<nt)
   pp=power[ii,np.clip(ind,0,nt-1)]
   den=pp.sum(axis=1)
   pol[off]=np.where(ok&(den>0),(pp[:,0]-pp[:,1])/np.where(den>0,den,1),np.nan)
  for off in offsets:delta[off].append(pol[off]-pol[0])
  sf.append(pol[0])
 f=feature[(feature.case==case["id"])&(feature.channel=="full")].set_index("pose_id",verify_integrity=True).loc[ids]
 assert np.nanmax(abs(np.concatenate(sf)-f.s_fp.to_numpy()))<1e-9
 df=pd.DataFrame({c:f[c].to_numpy() for c in existing})
 for o in offsets:df["ds_%+d"%o]=np.concatenate(delta[o])
 df["e_r"]=f.e_r.to_numpy();df["case"]=case["id"];df["route"]=case["route"];df["channel"]="full";df["pose_id"]=ids
 tables.append(df)
ft=pd.concat(tables,ignore_index=True)
result=dict(python=sys.version,sklearn=sklearn_version,native_hashes_verified=True,training={},full={},native={})
for route in ["R4","R5"]:
 case=route+"_aB_m0";tr=ft[ft.route!=route]
 hashes=dict(n=len(tr),ordered_keys=sha(tr[["case","channel","pose_id"]].to_csv(index=False).encode()),ordered_X_f64=sha(tr[cols].to_numpy(dtype="<f8").tobytes()),ordered_y_f64=sha(tr.e_r.to_numpy(dtype="<f8").tobytes()))
 result["training"][route]=dict(expected=lock["fit"][route],observed=hashes,match=hashes==lock["fit"][route])
 assert hashes==lock["fit"][route]
 model=joblib.load(out/(case+"_refit.joblib"))
 expected_params=dict(max_iter=200,learning_rate=.05,max_leaf_nodes=15,l2_regularization=1.,random_state=0)
 assert all(model.get_params()[k]==v for k,v in expected_params.items())
 full=ft[ft.case==case].set_index("pose_id",verify_integrity=True)
 reference=pd.read_csv(cache/"refit_reference"/(case+"_MR_SERIES.csv.gz"))
 for bias in ["B0","L2"]:
  raw=cache/"research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL"/(case+"_"+bias+".npz")
  with np.load(raw,allow_pickle=False) as z:
   ids=z["pose_id"];m=list(z["names"]).index("OFF_MB");mu=z["mu"][:,m,0]
  ref=reference[reference.bias==bias]
  assert np.array_equal(ref.pose_id,ids)
  x=full.loc[ids]
  prediction=model.predict(x[cols])
  implied=x.e_r.to_numpy()-ref.MU_R_EXDS__meas_r_cm.to_numpy()/100
  err=abs(prediction-implied);err_control=abs(prediction-mu)
  passed=np.isclose(prediction,implied,atol=1e-10,rtol=1e-10)&np.isclose(prediction,mu,atol=1e-10,rtol=1e-10)
  result["full"][case+"_"+bias]=dict(n=len(ids),failed=int((~passed).sum()),vs_archived_residual_max_m=float(err.max()),vs_CONTROL_mu_max_m=float(err_control.max()))
 with np.load(root/"A0_R2_SEARCH"/(case+"_Native_LoS_features.npz"),allow_pickle=False) as z:
  ids=z["pose_id"];frozen_columns=z["columns"].tolist();X=z["features"]
 assert frozen_columns==cols
 prediction=model.predict(pd.DataFrame(X,columns=cols))
 actual=pd.read_csv(out/(case+"_Native_LoS.csv"),float_precision="round_trip")
 assert np.array_equal(ids,actual.pose_id)
 err=abs(prediction-actual.MU_R_EXDS_m)
 result["native"][case]=dict(n=len(ids),finite=bool(np.isfinite(prediction).all()),max_abs_m=float(err.max()),allclose=bool(np.allclose(prediction,actual.MU_R_EXDS_m,atol=1e-10,rtol=1e-10)))
print(json.dumps(result,indent=2))
