"""Recompute ACTUAL frozen P4 local LUT kink slice from immutable failure input.

Not a schematic: full original R4 local MAP is rerun at fixed (mu,P,z,R)
and the identical frozen LUT h(x) is sampled while varying y(m) only.
One-step model and original raw files are unchanged.
"""
import argparse,io,json,math,os,hashlib,zipfile
from pathlib import Path
from datetime import datetime,timezone
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from core import map_update
from p3_rf_adapter4 import FrozenLut,R0
from p4_kink_fig_audit import ROOT,HERE,ZIP_SHA,get_sha

def fsha(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for part in iter(lambda:f.read(1<<20),b""):h.update(part)
 return h.hexdigest()

def source_member(z,suffix):
 matches=[x for x in z.namelist() if x.endswith(suffix)]
 if len(matches)!=1:raise RuntimeError("FROZEN_MEMBER_NOT_UNIQUE:"+str(matches))
 return matches[0]

def run(artifact,audit,out):
 a=json.loads(Path(audit).read_text())
 if not(a["decision"]=="GO" and a["source_sha"]==os.getenv("GITHUB_SHA")):
  raise RuntimeError("AUDIT_NOT_GO")
 if fsha(artifact)!=ZIP_SHA:raise RuntimeError("ORIGINAL_P4_FAILED_ZIP_CHANGED")
 for name,sha in a["source_hashes"].items():
  fn=ROOT/name if "/" in name else HERE/name
  if name=="workflow":fn=ROOT/".github/workflows/ekf4-r4-p4-kink-figure.yml"
  if get_sha(fn)[1]!=sha:raise RuntimeError("PLOT_CODE_CHANGED_AFTER_AUDIT:"+name)
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 byid={v["id"]:v for v in manifest["cases"]}
 lut=FrozenLut(ROOT)
 originals=[
 ("R2_aA_m0","full",80,"M4_P"),
 ("R2_aA_m0","los",61,"M4_P"),
 ("R4_aB_m0","full",8,"M4_P")
 ]
 plt.rcParams["font.family"]="DejaVu Sans"
 reports=[]
 with zipfile.ZipFile(artifact) as z:
  if z.testzip():raise RuntimeError("ZIP_CRC_MISMATCH")
  refpath=source_member(z,"/p4_final/P4_FINAL.json")
  final=json.loads(z.read(refpath))
  if final["git_sha"]!="46d679a32f55cae460d9ed35b4bb944bc48cc4ce":
   raise RuntimeError("ORIGINAL_P4_COMMIT_NOT_MATCHED")
  for case,ch,k,method in originals:
   suffix=f"/p4_map/P4_FAILURE_SNAPSHOTS/{case}_{ch}_k{k:04d}_{method}.json"
   f=source_member(z,suffix)
   data=z.read(f)
   previous_hash=next((v for key,v in final["source_archive_manifest"].items() if key.endswith(f.split("/")[-1])),None)
   if hashlib.sha256(data).hexdigest()!=previous_hash:
    raise RuntimeError("ORIGINAL_FAILURE_SNAPSHOT_SHA_CHANGED")
   obj=json.loads(data)
   c=byid[case]
   mu=np.asarray(obj["prior_mu4"],float)
   P=np.asarray(obj["prior_P4"],float)
   zraw=np.asarray(obj["z_range_s"],float)
   model=lambda x:lut.model(x,c)
   res=map_update(mu,P,zraw,model,R0,range_first=(method=="M4_R"),
                  max_iter=80,gradient_tol=1e-8)
   orig=obj["solver"]
   if res.status!=orig["status"] or abs(res.gradient_inf-orig["gradient_inf"])>1e-9:
    raise RuntimeError("ORIGINAL_NUMERIC_FAILURE_NOT_REPRODUCED")
   xstar=mu+res.prior_delta
   ax,ay,az=(float(v) for v in c["anchor"])
   u,v=xstar[0]-ax,xstar[1]-ay
   angle=math.degrees(math.atan2(-v,u))
   nearest=-180+2*round((angle+180)/2)
   delta_mm=np.linspace(-4,4,1601)
   y_offsets=delta_mm*.001
   hbase=lut.model(xstar,c)[0][1]
   vals=[];derivatives=[];costs=[];grid_angles=[]
   LP=np.linalg.cholesky(P);LR=np.linalg.cholesky(R0)
   for d in y_offsets:
    x=xstar.copy();x[1]+=d
    h,H=model(x)
    y=np.linalg.solve(LP,x-mu)
    vres=np.linalg.solve(LR,zraw-h)
    costs.append(.5*float(y@y+vres@vres))
    vals.append(float(h[1]-hbase))
    derivatives.append(float(H[1,1]))
    grid_angles.append(math.degrees(math.atan2(-(x[1]-ay),x[0]-ax)))
   vals=np.asarray(vals);derivatives=np.asarray(derivatives)
   costs=np.asarray(costs)
   k0=len(delta_mm)//2
   cost_delta=costs-costs[k0]
   sides={}
   for h in (1e-4,1e-5,1e-6):
    hh=(lut.model(xstar+np.array([0,h,0,0]),c)[0][1])
    hl=(lut.model(xstar-np.array([0,h,0,0]),c)[0][1])
    sides[str(h)]={"left_dsd_y":(hbase-hl)/h,
                   "right_dsd_y":(hh-hbase)/h,
                   "discontinuity":abs((hh-hbase)/h-(hbase-hl)/h)}
   # Locate the exact phi_tx crossing by local first order slope.
   local_angle_diff=(angle-nearest)
   d_angle_d_y=-180/math.pi*u/(u*u+v*v)
   knot_offset_mm= -local_angle_diff/d_angle_d_y*1000 if d_angle_d_y else None
   info={"case":case,"channel":ch,"index":k,"time_s":obj["t_s"],
         "solver_status":res.status,"gradient_inf":res.gradient_inf,
         "x_final":xstar.tolist(),"phi_tx_at_final_deg":angle,
         "nearest_phi_tx_grid_deg":nearest,
         "estimated_phi_tx_knot_offset_mm":knot_offset_mm,
         "s_value_at_final":float(hbase),
         "s_derivative_y_at_final":float(lut.model(xstar,c)[1][1,1]),
         "one_sided_s_derivatives":sides,
         "objective_min_offset_mm":float(delta_mm[int(np.argmin(costs))]),
         "objective_at_terminal":float(costs[k0]),
         "objective_difference_at_pm4mm":[float(cost_delta[0]),float(cost_delta[-1])],
         "source_failure_sha256":hashlib.sha256(data).hexdigest()}
   reports.append(info)
   stem=f"{case}_{ch}_k{k:04d}"
   np.savez_compressed(out/(stem+"_ACTUAL_SLICE.npz"),
       delta_y_mm=delta_mm,delta_s=vals,
       derivative_ds_dy=derivatives,
       delta_MAP_objective=cost_delta,
       phi_tx_deg=np.asarray(grid_angles),
       x_final=xstar)
   # Figure 1: actual frozen non-smooth continuous s interpolation.
   fig=plt.figure(figsize=(9,4.6))
   plt.plot(delta_mm,vals,linewidth=2,label="Frozen LUT: s(y+delta)-s(y*)")
   plt.axvline(knot_offset_mm,linestyle="--",linewidth=1,
          label=f"phi_tx = {nearest:.0f} deg grid boundary")
   plt.xlabel("Lateral perturbation delta y around failed MAP state (mm)")
   plt.ylabel("Delta s (dimensionless)")
   plt.title(f"Actual frozen RF LUT - {case} / {ch.upper()} / t={obj['t_s']:.1f}s")
   plt.legend();plt.grid(alpha=.25);plt.tight_layout()
   fig.savefig(out/(stem+"_S_KINK.png"),dpi=190);plt.close(fig)
   # Figure 2: sudden jump in actual dy derivative from frozen LUT.
   fig=plt.figure(figsize=(9,4.6))
   plt.plot(delta_mm,derivatives,linewidth=2,label="Analytic ds/dy, exact frozen LUT cell")
   plt.axvline(knot_offset_mm,linestyle="--",linewidth=1,
               label=f"phi_tx cell boundary")
   plt.xlabel("Lateral perturbation delta y (mm)")
   plt.ylabel("ds/dy (1/m)")
   plt.title(f"Discontinuous LUT Jacobian - {case} / {ch.upper()}")
   plt.grid(alpha=.25);plt.legend();plt.tight_layout()
   fig.savefig(out/(stem+"_JACOBIAN_JUMP.png"),dpi=190);plt.close(fig)
   # Figure 3: actual fixed-prior objective J, not a stylized V-curve.
   fig=plt.figure(figsize=(9,4.6))
   plt.plot(delta_mm,1e6*cost_delta,linewidth=2,
            label="Actual fixed-prior MAP cost delta")
   plt.axhline(0,linewidth=1,linestyle=":")
   plt.axvline(knot_offset_mm,linestyle="--",linewidth=1,
               label="LUT grid boundary")
   plt.xlabel("Lateral perturbation delta y (mm)")
   plt.ylabel("J(y+delta)-J(y*)   (x 1e-6)")
   plt.title(f"Original MAP objective around failed iterate - {case} / {ch.upper()}")
   plt.grid(alpha=.25);plt.legend();plt.tight_layout()
   fig.savefig(out/(stem+"_OBJECTIVE_SLICE.png"),dpi=190);plt.close(fig)
   (out/(stem+"_ACTUAL_SLICE.json")).write_text(json.dumps(info,indent=2)+"\n")
   print("P4_KINK_FIG "+json.dumps({k:info[k] for k in
      ("case","channel","index","solver_status","phi_tx_at_final_deg",
       "nearest_phi_tx_grid_deg","objective_min_offset_mm",
       "s_derivative_y_at_final")}),flush=True)
 summary={"schema":"P4_ACTUAL_FROZEN_LUT_COST_PROFILE_V1",
          "original_p4_sha":"46d679a32f55cae460d9ed35b4bb944bc48cc4ce",
          "original_archive_sha256":ZIP_SHA,
          "diagnostic_git_sha":os.getenv("GITHUB_SHA"),
          "scientific_PASS":False,
          "source_model_unmodified":True,
          "status":"PROFILE_COMPLETED",
          "cases":reports,
          "time_utc":datetime.now(timezone.utc).isoformat()}
 (out/"P4_ACTUAL_FIGURES_FINAL.json").write_text(json.dumps(summary,indent=2)+"\n")
 return 0

if __name__=="__main__":
 p=argparse.ArgumentParser()
 for name in ("artifact","audit","out"):p.add_argument("--"+name,required=True)
 a=p.parse_args();raise SystemExit(run(a.artifact,a.audit,a.out))
