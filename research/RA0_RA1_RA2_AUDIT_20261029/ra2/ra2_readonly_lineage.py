#!/usr/bin/env python3
"""Read-only RA2 seven-case H/SAMPLES/timeline and packet lineage audit.
Never changes original data; emits JSON receipts and nonzero exits on blocked evidence.
"""
import argparse,csv,hashlib,io,json,os, pathlib,sys,urllib.request
import numpy as np
CASES=("R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0","R4_aB_m0","R5_aA_m0","R5_aB_m0")
EXPECTED_H={"R2":1303,"R4":922,"R5":1883}
EXPECTED_T={"R2":979,"R4":742,"R5":1415}
EXPECTED_DIGEST={"R2_aA_m0":"1c40aea5ab7af87223f942c0727c0f6aabe7bd60e55a70c68c74d2c115750a51","R2_aB_m0":"b3b4c61e23286b86c78b6e87f5b9b5358121cbde7717bae73e5650cc900b546c","R2_aA_m45":"dd0264c1d004d78ff0f0d39f5f0c613b084ea89ad558ac448ecbfd0b3e177ea1","R4_aA_m0":"73cfc35ded71b0114d3b15d2a50dba4a804b377d7b3b2b37aafe11c628c83956","R4_aB_m0":"30743ca017615bbfede78a8350739262a756d47ac2213c60b08eb109cebfe1b0","R5_aA_m0":"026a2c5ebb17916633f74d767ec8675f9358c93f8a4ee0df465733838ec89f80","R5_aB_m0":"a4858372414f81156b25fde2e14d57fc0e1a3f987782a5b268dbdf14bcf174b3"}
CONTROL_SHA={"R2_aA_m0":"df8ac0c18d1829fb57e6c71c86888e634a20f47ae0705df21624e1783590b37e","R2_aB_m0":"e1013f6949f9c7b01643d6daf13c447e76c020d5f19a222ce12a08251699c3ac","R2_aA_m45":"08443ed214057b5ec0d9a233f3877b261441e797a6446a173bd08eac6ac5d147","R4_aA_m0":"b999d12690c4ec03473d7ee37072c91a9349e1d3488ff1f5fba5f06ec3b8b1d2","R4_aB_m0":"f1a2e6c98b0485b464db26a9697a4212dbdfe90deef3132fe312693f29e1180e","R5_aA_m0":"5fea1a984fd70cee35ef0bc75b46d3713f32eab1c7ec9c63cd4e5a2bea1f39fa","R5_aB_m0":"596a76e42ba54629a8c97a2837906259238a240ec1d20d94fd5221c9781250e3"}
ROOT="https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/"
SRC="9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13"
BLK="results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
def load(url,p):
 if not p.exists():
  with urllib.request.urlopen(url,timeout=120) as r,p.open("wb") as o:
   while True:
    b=r.read(2**20)
    if not b:break
    o.write(b)
 return p
def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(2**20),b""):h.update(b)
 return h.hexdigest()
def native(h,df):
 n=h.shape[1]; w=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
 B=96; rec=[]
 for st in range(0,len(h),B):
  h0=h[st:st+B,:,:,0]; pad=np.zeros((len(h0),4*n,2),complex);pad[:,:n,:]=h0*w[None,:,None];cir=np.fft.ifft(pad,axis=1)*n
  a=np.abs(cir); port=a.max(axis=1).argmax(axis=1);p=a[np.arange(len(cir)),:,port];tap=(p>=.3*p.max(axis=1)[:,None]).argmax(axis=1)
  power=np.abs(cir[np.arange(len(cir)),tap,:])**2;den=power.sum(axis=1)
  s=np.where(den>0,(power[:,0]-power[:,1])/np.where(den>0,den,1),np.nan)
  r=tap/(4*n*df)*299792458.
  rec.extend(zip(tap.astype(int).tolist(),r.tolist(),s.tolist()))
 return rec
def check_keys(samples,timeline,n):
 ids=[int(x["pose_id"]) for x in samples]
 t={int(x["pose_id"]):x for x in timeline}
 errs=[]
 if len(samples)!=n or set(ids)!=set(range(n)) or len(ids)!=len(set(ids)):errs.append("ERR_DUPLICATE_KEY_OR_MISSING_POSE")
 if not t or len(timeline)!=len(t) or min(t)!=0:errs.append("ERR_TIMELINE_KEY")
 if len(t)<min(len(samples),2):errs.append("ERR_TIMELINE_COUNT")
 for i in (set(ids)&set(t)):
  a=samples[i];b=t[i]
  if abs(float(a["x"])-float(b["x"]))>5e-6 or abs(float(a["y"])-float(b["y"]))>5e-6:errs.append("ERR_POSE_ALIGNMENT");break
 return sorted(set(errs))
def negative_tests():
 a=[dict(pose_id=i,x=float(i),y=0) for i in range(3)];t=[dict(pose_id=i,x=float(i),y=0) for i in range(2)]
 assert "ERR_TIMELINE_COUNT" in check_keys(a,t[:1],3)
 assert "ERR_DUPLICATE_KEY_OR_MISSING_POSE" in check_keys(a[:2]+[dict(a[0])],t,3)
 b=[dict(x) for x in a];b[1]["x"]=100
 assert "ERR_POSE_ALIGNMENT" in check_keys(b,t,3)
 assert "ERR_DUPLICATE_KEY_OR_MISSING_POSE" in check_keys([],[],3)
 assert "ERR_DUPLICATE_KEY_OR_MISSING_POSE" in check_keys(a[:2],t,3)
 return {"duplicate":"REJECT","alignment":"REJECT","zero_rows":"REJECT","missing":"REJECT"}
def main():
 p=argparse.ArgumentParser();p.add_argument("--work",default="ra2_output");a=p.parse_args()
 out=pathlib.Path(a.work);out.mkdir(exist_ok=True,parents=True);qa=[];issues=[]
 try:neg=negative_tests()
 except Exception as ex:neg={"status":"FAIL","error":str(ex)};issues.append("ERR_NEGATIVE_FIXTURE")
 for c in CASES:
  route=c[:2]; n=EXPECTED_H[route];d=out/c;d.mkdir(exist_ok=True)
  try:
   Hf=load(f"{ROOT}{SRC}/{BLK}/FULL_RF/H_{c}.npy",d/"H.npy")
   sf=load(f"{ROOT}{SRC}/{BLK}/{c}/SAMPLES.json",d/"samples.json")
   tf=load(f"{ROOT}{SRC}/results/DRIVE_SIM_20261007/S1/routes/timeline_{route}_Tnone.csv",d/"timeline.csv")
   dh=sha(Hf); samples=json.loads(sf.read_text());timeline=list(csv.DictReader(tf.open()))
   z=np.load(Hf,mmap_mode="r",allow_pickle=False);err=check_keys(samples,timeline,n)
   if dh!=EXPECTED_DIGEST[c]:err.append("ERR_SOURCE_HASH")
   if tuple(z.shape)!=(n,257,2,2):err.append("ERR_H_SHAPE")
   if len(timeline)!=EXPECTED_T[route]:err.append("ERR_TIMELINE_COUNT")
   bank=d/"bank.npz"
   bank_url="https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/"+SRC+"/LP_plus45_bank.npz"
   try:
    load(bank_url,bank)
    bh=sha(bank)
    if bh!="b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b":err.append("ERR_BANK_HASH")
    with np.load(bank) as bx: freq=bx["freqs_hz"]
    if len(freq)!=257 or not np.all(np.isfinite(freq)) or not np.allclose(np.diff(freq),freq[1]-freq[0],rtol=1e-10,atol=1e-4):
     err.append("ERR_FREQUENCY_GRID")
    else:
     obs=native(z,float(freq[1]-freq[0]))
     (d/"OBS_NATIVE.csv").write_text("pose_id,first_tap,range_m,s\n"+"".join(f"{i},{x[0]},{x[1]:.15g},{x[2]:.15g}\n" for i,x in enumerate(obs)))
   except Exception as be:
    obs=[];err.append("ERR_BANK_UNAVAILABLE_"+str(be)[:110])
   trace=d/"control_B0.npz"
   try:
    control_url="https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/"+SRC+"/research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL/"+c+"_B0.npz"
    load(control_url,trace)
    ctrlsha=sha(trace)
    if ctrlsha!=CONTROL_SHA[c]:err.append("ERR_CONTROL_SHA")
    with np.load(trace,allow_pickle=False) as T:
     tk={key:tuple(T[key].shape) for key in T.files}
     names=[str(x) for x in T["names"]];jb=names.index("OFF_BB")
     packet_z=T["nu"][:,jb,:]+T["h"][:,jb,:]+T["mu"][:,jb,:]
     times=T["t_s"]; truth=T["truth_scoring_only"]
     if len(packet_z)!=len(timeline):err.append("ERR_PACKET_COUNT")
     if len(times)!=len(timeline):err.append("ERR_PACKET_TIME_LENGTH")
     if len(times)==len(timeline) and max(abs(float(q0["t_s"])-float(t)) for q0,t in zip(timeline,times))>1e-8:err.append("ERR_TIME_ALIGNMENT")
     if len(packet_z)==len(timeline) and obs:
      ob=np.asarray(obs[:len(packet_z)],float)
      delta_s=np.abs(ob[:,2]-packet_z[:,1]);delta_r=np.abs(ob[:,1]-packet_z[:,0])
      sp=float(np.nanmax(delta_s));rp=float(np.nanmax(delta_r))
      if sp>1e-12:err.append("ERR_S_NATIVE_PARITY")
      if rp>1e-9:err.append("ERR_R_NATIVE_PARITY")
      replay={"n":len(packet_z),"max_ds":sp,"max_dr_m":rp,"s_pass":sp<=1e-12,"r_pass":rp<=1e-9}
     else:replay={"status":"BLOCKED_SHAPE"}
   except Exception as ce:
    replay={"status":"BLOCKED_CONTROL","error":str(ce)}
    err.append("ERR_CONTROL_UNAVAILABLE")
   q={"case":c,"raw_sha256":dh,"expected_sha256":EXPECTED_DIGEST[c],"sha_valid":dh==EXPECTED_DIGEST[c],"h_shape":list(z.shape),"samples":len(samples),"timeline":len(timeline),"keys_errors":err,"range_s_native":"RECOMPUTED_FROM_SHA_VERIFIED_H_BANK" if obs else "BLOCKED_FREQ_BANK","raw_native_n":len(obs),"packet_replay":replay,"control_sha256":sha(trace) if trace.exists() else "MISSING"}
   qa.append(q);issues.extend(err)
  except Exception as ex:
   qa.append({"case":c,"status":"BLOCKED_INPUT","error":str(ex)});issues.append("ERR_INPUT_FETCH")
 (out/"RA2_AUDIT.json").write_text(json.dumps({"source_sha":SRC,"case_rows":qa,"negative":neg,"status":"BLOCKED_EVIDENCE" if issues or len(qa)!=7 else "PARTIAL_READONLY","issues":sorted(set(issues)),"scientific_approval":False},indent=2,ensure_ascii=False))
 print(json.dumps({"status":"BLOCKED_EVIDENCE" if issues else "PARTIAL_READONLY","case_count":len(qa),"issues":sorted(set(issues))},indent=2))
 return 2 if issues else 0
if __name__=="__main__":sys.exit(main())
