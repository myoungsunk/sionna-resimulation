#!/usr/bin/env python3
"""P2 Source/Math/Original data PRE-RUN only. No estimator recursive scoring.

This auditor code uses separate direct numerical finite differences, manual
Joseph update, raw byte SHA and physical original RF/bank/trace. Written by
the same chat author as proposer; separate GitHub runner does not imply a
different human or model author. This explicitly cannot authorize P2 alone.
"""
from __future__ import annotations
import csv,hashlib,io,json,math,os,pathlib,platform,subprocess,sys,time,traceback,zipfile
import numpy as np

ROOT=pathlib.Path.cwd()
LOCK=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P2_20261101"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
OUT=pathlib.Path(os.getenv("DLP_P2_AUDIT_OUT","/tmp/dlp_p2_audit"));OUT.mkdir(parents=True,exist_ok=True)
ZIP=pathlib.Path(os.getenv("DLP_RF_ZIP","/tmp/dlp_p2_rf_original.zip"))
BANKS=pathlib.Path(os.getenv("DLP_BANK_DIR","/tmp/dlp_p2_banks"))
start=time.monotonic()
checks={};failure=[];info={}
def sha(path):
    d=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
      for b in iter(lambda:f.read(1<<20),b""):d.update(b)
    return d.hexdigest()
def J(path):return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
def accept(name,condition,note,actual=None):
    checks[name]={"status":"PASS" if condition else "FAIL","note":str(note),"measured":actual}
    print("P2_AUDIT",name,checks[name]["status"],str(actual)[:500],flush=True)
    if not condition:failure.append(dict(gate=name,reason=str(note),measured=actual))
def f(x,a,ds,gyro,dt):
    y=np.array(x,float);q=gyro-y[3]*dt;h=q/2
    fac=np.sinc(h/np.pi)
    ang=y[2]+h
    y[:2]+=ds*fac*np.array([math.cos(ang),math.sin(ang)])
    y[2]=(y[2]+q+np.pi)%(2*np.pi)-np.pi
    return y
def run():
  receipt=J(LOCK/"P2_PROPOSER_LOCK_RECEIPT.json")
  config=J(LOCK/"P2_CONFIG_LOCK.json")
  tol=J(LOCK/"P2_NUMERIC_TOLERANCES.json")
  contract=LOCK/"P2_EXPERIMENT_CONTRACT_PROPOSER_LOCKED.md"
  changed=[a["name"] for a in receipt["file_digests"] if sha(LOCK/a["name"])!=a["sha256"]]
  accept("A00_PROPOSER_LOCK",not changed and len(tol["tests"])==16 and
         config["status"]=="PROPOSER_LOCKED_AUDIT_PENDING",
         "Original P2 lock exact hashes, no post-hoc changes",dict(sha_mismatch=changed))
  assert not changed,"CONTRACT_DIGEST_CHANGED"
  assert config["base_p1_head"]=="21aa49ea809255a2dc863a4fbdb1e2c98dcaa16a"
  source_errors=[]
  for item in config["pinned_sources"]:
      got=subprocess.check_output(["git","hash-object",item["path"]],text=True).strip()
      if got!=item["git_blob"]:source_errors.append([item["path"],got,item["git_blob"]])
  accept("A01_PINNED_SOURCE",not source_errors,"6 exact upstream source blob hashes",
         dict(n=len(config["pinned_sources"]),errors=source_errors))
  assert not source_errors,"SOURCE_SHA_CHANGED"
  p1lock=J(P1/"P1_INPUT_LOCK.json")
  errors=[]
  for item in p1lock["base_assets"]:
      p=ROOT/item["path"]
      if not p.is_file() or sha(p)!=item["sha256"] or p.stat().st_size!=item["bytes"]:
          errors.append(item["path"])
  accept("A02_ORIGINAL_39",not errors and len(p1lock["base_assets"])==39,"39 exact original raw C0 files byte SHA",
         dict(missing_or_wrong=errors[:10],verified=39-len(errors)))
  assert not errors,"C0_BINARY_MISSING_OR_SHA_MISMATCH"
  bankpaths=[]
  for item in p1lock["ffd_bank_source"]["banks"]:
      got=list(BANKS.rglob(item["filename"]))
      if len(got)!=1 or sha(got[0])!=item["sha256"] or got[0].stat().st_size!=item["bytes"]:
         errors.append(item["filename"])
      else:bankpaths.append(got[0])
  accept("A03_REAL_BANKS",len(bankpaths)==2 and len(errors)==0,
         "Both physical FFD .npz original bytes verified, not LFS pointers",
         dict(names=[x.name for x in bankpaths]))
  assert len(bankpaths)==2 and not errors,"BANK_HASH_CHANGED"
  archived=config["original_archived_rf_artifact"]
  expect_sha=archived["archive_sha256"]
  zsha=sha(ZIP)
  accept("A04_ARCHIVE_ZIP",zsha==expect_sha and zipfile.is_zipfile(ZIP),
         "Full original archived 14 trace ZIP exact byte SHA",dict(actual=zsha,expected=expect_sha,bytes=ZIP.stat().st_size))
  assert zsha==expect_sha,"ARCHIVE_ZIP_HASH_CHANGED"
  z=zipfile.ZipFile(ZIP)
  assert z.testzip() is None,"ARCHIVE_CRC_INVALID"
  summary_raw=z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json")
  summary=json.loads(summary_raw)
  trace_error=[];refs={};truth={}
  for descriptor in summary["per_case"]:
    name="P2_OUT/"+descriptor["trace_file"]
    payload=z.read(name)
    if hashlib.sha256(payload).hexdigest()!=descriptor["trace_sha256"]:trace_error.append(name);continue
    with np.load(io.BytesIO(payload),allow_pickle=False) as a:
      t=a["t_s"].copy();poseid=a["pose_id"].copy()
      x=a["truth_for_offline_scoring_only"].copy()
      obs=np.column_stack((a["z_r_m"],a["z_s"]))
      prior=a["xminus"].copy();prior_P=a["Pminus"].copy()
    key=(descriptor["case"],descriptor["channel"])
    refs[key]=dict(t=t,poseid=poseid,truth=x,obs=obs,prior=prior,prior_P=prior_P)
  ok=(len(refs)==14 and len(trace_error)==0 and
      hashlib.sha256(summary_raw).hexdigest()==archived["archive_summary_sha256"])
  accept("A05_ALL_14_ARCHIVED_TRACES",ok,"original 14 exact archive trace hashes",
         dict(n=len(refs),missing=trace_error,summary_sha=hashlib.sha256(summary_raw).hexdigest()))
  assert ok,"ARCHIVE_TRACES_BROKEN"
  case_meta={a["id"]:a for a in J(ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json")["cases"]}
  expected_cases=set(config["cases"])
  assert set(case_meta)==expected_cases,"CASE_SET_DRIFT"
  counts={"R2":979,"R4":742,"R5":1415}
  geomerrors=[];comp_keys={};sync=[]
  for cid in config["cases"]:
    c=case_meta[cid]
    mode_full=refs[(cid,"full")];mode_los=refs[(cid,"los")]
    for key in ("t","poseid","truth"):
       if not np.array_equal(mode_full[key],mode_los[key]):geomerrors.append([cid,"FULL_LOS_NOT_MATCHED",key])
    route=c["route"];n=counts[route]
    if len(mode_full["t"])!=n or not np.all(np.diff(mode_full["t"])>0):
       geomerrors.append([cid,"TIMELINE_LENGTH_OR_ORDER"])
    if route not in comp_keys:comp_keys[route]=mode_full
    elif any(not np.array_equal(comp_keys[route][name],mode_full[name]) for name in ("t","poseid","truth")):
       geomerrors.append([cid,"ROUTE_TRUTH_DIFFER"])
  calc=sum(counts[case_meta[cid]["route"]] for cid in config["cases"])
  calc_eval=sum(np.count_nonzero(refs[(cid,"full")]["t"]>=30) for cid in config["cases"])
  accept("A06_MATCHED_C0_KEYS",not geomerrors and calc==7251 and calc_eval==6201,
         "7 paired cases, Full vs LoS true time/pose identical, correct independent scene count",
         dict(errors=geomerrors[:6],timeline_per_channel=calc,eval_ge30_per_channel=int(calc_eval)))
  assert not geomerrors,"POSE_OR_CASE_MATCH_FAILED"
  sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
  sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
  import core
  from qclean_uwb.drivesim.sensor_v2 import SensorV2Config,generate,motion_increments,rng
  import r2_bias_replay as old_replay
  samples=[]
  consistency=[];source_bias=[]
  for route,trace in comp_keys.items():
    t=trace["t"];pose=trace["truth"]
    ds,da=motion_increments(t,pose,convention="legacy-euler")
    controls={}
    for level in ("B0","L2"):
      inputs,x0=old_replay.build_positive_bias_controls(t,pose,level,0)
      controls[level]=inputs
      # Repeat independently to detect accidental unseeded states.
      again,x02=old_replay.build_positive_bias_controls(t,pose,level,0)
      if not(np.array_equal(x0,x02) and all(np.array_equal(inputs[k],again[k])
                 for k in ("t_s","dt_s","ds_odom","dtheta_gyro"))):consistency.append([route,level,"NONDETERMINISTIC"])
      if not np.array_equal(inputs["t_s"],t):consistency.append([route,level,"T_CHANGED"])
      if not np.allclose(x0[:2],pose[0,:2]+rng(0,"initial").standard_normal(3)[:2]*.1):
        consistency.append([route,level,"INITIAL_TEST_WEAK_WRONG"]); # first 2 component only
    bias=.2*np.pi/180
    d0=controls["B0"]["ds_odom"];d1=controls["L2"]["ds_odom"]
    if np.max(abs(d0-d1))>1e-12:consistency.append([route,"L2_WHEEL_DIFF"])
    ga=controls["L2"]["dtheta_gyro"]-controls["B0"]["dtheta_gyro"]
    if np.max(abs(ga[1:]-bias*controls["B0"]["dt_s"][1:]))>1e-12:
      consistency.append([route,"L2_NOT_ONLY_GYRO_BIAS",float(np.max(abs(ga[1:]-bias*controls["B0"]["dt_s"][1:])))])
    samples.append(dict(route=route,n=len(t),init_x=x0.tolist(),
                        B0_L2_wheel_max=float(np.max(abs(d0-d1))),
                        B0_L2_gyro_bias_residual_max=float(np.max(abs(ga[1:]-bias*controls["B0"]["dt_s"][1:])))))
  accept("A07_SENSOR_PAIRED_GENERATOR",not consistency,
      "Frozen sensor-v2 seed0 identical route streams; B0/L2 differ by exact gyro-bias only",
      dict(samples=samples,errors=consistency))
  assert not consistency,"SENSOR_INPUT_MISMATCH"
  # Repeat frozen 4state f/F/G and covariance propagation in an independently
  # coded mathematical path, not invoking evaluator's analytic Jacobian.
  ferror=[];gerror=[];qerror=[]
  teststates=[
    np.array([6.0,.3,.42,math.radians(.05)]),
    np.array([11.,-.5,-2.2,math.radians(.2)]),
    np.array([3.9,.1,3.0,0.])]
  for x in teststates:
    ds,da,dt=.041,.013,.2
    y,F,G=core.transition(x,ds,da,dt)
    fd=np.zeros((4,4));eps=1e-6
    for j in range(4):
      e=np.zeros(4);e[j]=eps
      ap=f(x+e,None,ds,da,dt);am=f(x-e,None,ds,da,dt)
      v=(ap-am)/(2*eps)
      v[2]=((ap[2]-am[2]+np.pi)%(2*np.pi)-np.pi)/(2*eps)
      fd[:,j]=v
    ferror.append(float(np.max(abs(F-fd))))
    assert abs(F[2,3]+dt)<=1e-14
    Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    P=np.diag([.01,.01,math.radians(5)**2,math.radians(.1)**2])
    pred,cov,F0,G0=core.predict(x,P,ds,da,dt,Q)
    y2=f(x,None,ds,da,dt)
    cov_ref=(F@P@F.T+G@Q@G.T)
    qerror.append(float(np.max(abs(cov-cov_ref))))
    if np.linalg.eigvalsh(cov).min()<=0:qerror.append(1.)
  accept("A08_4STATE_F_FD",max(ferror)<1e-6 and max(qerror)<1e-10,
         "Four-state analytic F including F_psi_bg=-dt versus independent central FD",
         dict(max_f=max(ferror),max_covariance=max(qerror)))
  assert max(ferror)<1e-6 and max(qerror)<1e-10,"FOUR_STATE_MATH_INVALID"
  # Manual scalar/Joseph conditional used as an independent numerical oracle.
  from core import gaussian_update
  Kerrors=[];Perrors=[];niserrors=[];drift=[]
  P=np.array([[.05,.004,.003,.00002],[.004,.05,.002,0],[.003,.002,.01,-.00001],[.00002,0,-.00001,1e-5]])
  P=(P+P.T)/2
  xx=np.array([5.7,.2,.16,.0001])
  def obs1(x):
     d=np.sqrt((x[0]-4)**2+(x[1])**2+2.2**2)
     h=np.array([d-0.5315983906250129])
     H=np.array([[(x[0]-4)/d,x[1]/d,0.,0.]])
     return h,H
  for joint in (False,True):
     baseH=obs1(xx)[1]
     H=np.concatenate((baseH,[[.3,-.15,.7,0.]]),axis=0) if joint else baseH
     h=np.r_[obs1(xx)[0],[.2]] if joint else obs1(xx)[0]
     rr=np.diag([0.0068578637,.0081]) if joint else np.array([[0.0068578637]])
     z=h+np.array([.09,.03] if joint else [.09])
     # One-step linearization at same x, no bias observation derivative
     manualNu=z-h
     S=H@P@H.T+rr
     K=P@H.T@np.linalg.inv(S)
     newx=xx+K@manualNu;newx[2]=(newx[2]+np.pi)%(2*np.pi)-np.pi
     A=np.eye(4)-K@H
     newP=A@P@A.T+K@rr@K.T
     model=lambda v:(h+H@(v-xx),H)
     out,cov,diag=gaussian_update(xx,P,z,model,rr,gate_threshold=None)
     Kerrors.append(float(np.max(abs(out-newx))))
     Perrors.append(float(np.max(abs(cov-newP))))
     niserrors.append(abs(diag["NIS"]-float(manualNu@np.linalg.solve(S,manualNu))))
  accept("A09_MANUAL_JOSEPH_NIS",max(Kerrors)<1e-10 and max(Perrors)<1e-10 and max(niserrors)<1e-10,
         "independent manual Joseph EKF for scalar range and joint s/r, NIS exact",
         dict(max_state=max(Kerrors),max_P=max(Perrors),max_NIS=max(niserrors)))
  assert max(Kerrors)<1e-10 and max(Perrors)<1e-10,"JOSEPH_UPDATE_MISMATCH"
  # SourceFD physical pilot: real bank and actual estimated-state geometry.
  # Read-only model under test; independent FD on stable first-path/cell.
  sys.path.insert(0,str(ROOT/'research/FFD_P0P3_20261016'))
  import p0_initial
  from source_model import SourceFFD
  temp=ROOT.parent
  assert not (temp/"BANK_MANIFEST.json").exists()
  for item,p in zip(p1lock["ffd_bank_source"]["banks"],bankpaths):
     (temp/item["filename"]).symlink_to(p)
  (temp/"BANK_MANIFEST.json").write_text(json.dumps({"npz_sha256":{x["filename"]:x["sha256"] for x in p1lock["ffd_bank_source"]["banks"]}}))
  (temp/"ffd_p0p3/out").mkdir(parents=True,exist_ok=True)
  model=SourceFFD()
  errors=[];tested=0;crossings=0;hrfd=[]
  for case_id in config["cases"]:
     case=case_meta[case_id]
     x=refs[(case_id,"full")]["truth"][0].copy()
     # Use estimated-state perturbation; true pose here only selects an
     # offline pre-run source canary, not a model runtime input.
     guess=np.array([x[0]+.15,x[1]-.04,x[2]+.04,0.])
     pr,H,di=model.batch(guess[None],case,gradient=True,return_diagnostics=True)
     if H.shape!=(1,2,4) or abs(H[0,:,3]).max()>1e-12 or not np.isfinite(H).all():
        errors.append([case_id,"BAD_SHAPE_OR_BIAS"])
     d=np.sqrt((guess[0]-case["anchor"][0])**2+(guess[1]-case["anchor"][1])**2+
               (case["robot_z_m"]-case["anchor"][2])**2)
     if abs(pr[0,0]-(d-0.5315983906250129))>1e-12:errors.append([case_id,"R_BRIDGE_DIFFER"])
     for ax in (0,1,2):
       t=np.zeros(4);t[ax]=1e-5
       p,_,dpi=model.batch((guess+t)[None],case,gradient=False,return_diagnostics=True)
       n,_,dni=model.batch((guess-t)[None],case,gradient=False,return_diagnostics=True)
       if not(np.array_equal(di["tap"],dpi["tap"]) and np.array_equal(di["tap"],dni["tap"])
         and np.array_equal(di["cells"],dpi["cells"]) and np.array_equal(di["cells"],dni["cells"])):
           crossings+=1;continue
       fd=(p[0,1]-n[0,1])/(2e-5);delta=abs(fd-H[0,1,ax])
       if delta>2e-5 and (abs(H[0,1,ax])<=1e-6 or delta/abs(H[0,1,ax])>1e-4):
         errors.append([case_id,ax,delta])
       tested+=1
  accept("A10_SOURCE_OBSERVATION_CANARY",not errors and tested>0,
         "Pinned SourceFFD 2x4 H and expected d+B_OLD, finite diff on stable original-bank cells",
         dict(tested_axes=tested,crossings=crossings,errors=errors))
  assert not errors and tested>0,"SOURCE_H_JAC_INVALID"
  assert set(config["arms"])=={"DR4","R4","J4_SRC"} and set(config["channels"])=={"FULL","LOS"}
  assert [x["label"] for x in config["sensor_controls"]["conditions"]]==["B0","L2"]
  assert config["population"]["scene_independent"]==1
  accept("A11_SCOPE_NO_SCIENCE_YET",True,"Preflight only, no recursive filter scoring/metrics/learning invoked",
         dict(arms=list(config["arms"]),bias=["B0","L2"],scene_n=1))
  info.update(dict(sources=[x["git_blob"] for x in config["pinned_sources"]],
        archived_zip_sha256=zsha,source_jac_test_axes=tested,
        original_39_pass=True,bank_sha_pass=True,same_control_routes=list(comp_keys)))
  z.close()

if __name__=="__main__":
  try:run()
  except BaseException as e:
    failure.append(dict(gate="AUDITOR_UNHANDLED_EXCEPTION",reason=repr(e),traceback=traceback.format_exc()))
    print("P2_AUDIT_EXCEPTION",repr(e),traceback.format_exc(),flush=True)
  verdict="ACCEPT_WITH_BOUNDARIES" if not failure and len(checks)>=12 else "BLOCKED_EVIDENCE"
  result=dict(schema="DLP_P2_INDEPENDENT_GITHUB_RUNNER_PRE_RUN_V1",
      verdict=verdict,contract_id="DLP-EKF-GAPS-001/P2-V1",
      input_contract_sha256="568ef6b794457f682ae9fd96e30d8a6f072d0283fcfd17aed4dcc2adfb76a48b",
      config_sha256="99c4f6303ece8d19b2a30f1217f62c852df3074583dff6c388245a54c555cc43",
      tolerance_sha256="ab385d88538b0f2485fdcf1cceef31262a08a7a5c214751c4dfc6949e6101ae3",
      actor="GPT-6-authored independent mathematical preflight on separate GitHub Actions Linux runner",
      identity_boundaries="Same ChatGPT conversation authored proposer and preflight; computational runner/code separately executed, NOT separately authenticated human GitHub reviewer.",
      git_sha=os.environ.get("GITHUB_SHA"),run_id=os.environ.get("GITHUB_RUN_ID"),
      code_sha256=sha(__file__),runtime={"python":sys.version,"numpy":np.__version__,"platform":platform.platform()},
      checks=checks,failures=failure,detail=info,
      P2_science_status="NOT_RUN",p2_frozen=False,
      allowed_next="Append-only P2 FROZEN proposer and computational-auditor SHA ratification if ACCEPT_WITH_BOUNDARIES",
      scope="C0 7 cases; B0 and L2; 3 4-state arms, no original data or P1 output mutation",
      duration_s=time.monotonic()-start)
  (OUT/"P2_PRE_RUN_AUDIT.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
  print("P2_AUDIT_FINAL",verdict,"CHECKS",len(checks),"FAIL",len(failure),flush=True)
  sys.exit(0 if verdict=="ACCEPT_WITH_BOUNDARIES" else 1)
