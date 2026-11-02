"""Reproduce Fig. 1 from immutable GitHub SourceFFD code and matching local banks."""
from pathlib import Path
import sys,types,json,hashlib,datetime,platform,csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/"source"))
import pattern_apply as P
import observation as O
BANK_ROOT=Path("D:/codex/raytracing_modules/rt_cp_uwb/results/RF_DELIVERY_RECOVERY_20261019_R01/BANKS")
receipt=json.loads((BASE/"source/SOURCE_BANK_RECEIPT.json").read_text())
banks=[]; inputs=[]
for entry in receipt["banks"]:
    path=BANK_ROOT/entry["path"]
    with path.open("rb") as f: digest=hashlib.file_digest(f,"sha256").hexdigest()
    assert digest==entry["sha256"], "BANK_HASH_MISMATCH"
    with np.load(path,allow_pickle=False) as z: banks.append(P.Bank(dict(z)))
    inputs.append(dict(path=str(path),sha256=digest,github_path=entry["path"]))
shim=types.ModuleType("p0_initial")
shim.load_banks=lambda:banks
shim.ROOT=BASE;shim.OUT=BASE;shim.P=P;shim.O=O
shim.ANCHOR_ROTATION=np.diag([1.,-1.,-1.])
sys.modules["p0_initial"]=shim
adapter=types.ModuleType("p3_rf_adapter4")
adapter.B_OLD=0. # Unused: only physical_h_col is called, never range prediction.
sys.modules["p3_rf_adapter4"]=adapter
from source_model import SourceFFD
model=SourceFFD(banks)
yaw=np.arange(0.,361.,2.)
states=np.column_stack([np.full(len(yaw),7.),np.zeros(len(yaw)),np.radians(yaw),np.zeros(len(yaw))])
case=dict(anchor=[10.,0.,2.65],robot_z_m=.45,mount_deg=0.)
h=model.physical_h_col(states,case)
obs=O.first_path_batch(O.cir_batch(h),1950000.)
power=obs["power"]; den=power.sum(1); share=power/den[:,None]; s=obs["s"]
assert len(yaw)==181 and np.isfinite(power).all() and (den>0).all()
assert np.isfinite(s).all() and (abs(s)<=1).all()
assert np.max(abs(share.sum(1)-1))<1e-12
assert np.max(abs(s-(share[:,0]-share[:,1])))<1e-12
assert np.max(abs(h[0]-h[-1]))<1e-12
# Separate field_world implementation cross-check, no model gradients or cap.
d=(np.array([7.,0.,.45])-np.array(case["anchor"])); dist=np.linalg.norm(d);d/=dist
tht=np.array([np.arccos(d[2])]); pht=np.array([np.arctan2(d[1],d[0])])
v=-d;thr=np.array([np.arccos(v[2])]);phr=np.array([np.arctan2(v[1],v[0])])
tx=P.field_world(banks[0],shim.ANCHOR_ROTATION,tht,pht)[:,0]
errors=[]
for idx in (0,37,90,143,180):
    a=np.radians(yaw[idx]); c,t=np.cos(a),np.sin(a);rot=np.array([[c,-t,0],[t,c,0],[0,0,1]])
    rx=np.stack([P.field_world(b,rot,thr,phr)[:,0] for b in banks],axis=1)
    factor=O.C0/banks[0].freqs_hz/(4*np.pi*dist)*np.exp(-2j*np.pi*banks[0].freqs_hz*dist/O.C0)
    ref=np.einsum("fri,fi->fr",rx,tx)*factor[:,None]
    errors.append(float(np.max(abs(ref-h[idx]))))
assert max(errors)<1e-10
with (BASE/"fig01_los_azimuth_data.csv").open("w",newline="") as f:
    w=csv.writer(f);w.writerow(["yaw_deg","P_plus","P_minus","share_plus","share_minus","s","tap_index"])
    w.writerows(zip(yaw,power[:,0],power[:,1],share[:,0],share[:,1],s,obs["index"]))
plt.rcParams.update({"font.family":"Times New Roman","font.size":9,"mathtext.fontset":"stix","axes.labelsize":10,"xtick.labelsize":9,"ytick.labelsize":9,"legend.fontsize":9,"axes.linewidth":.65,"pdf.fonttype":42,"ps.fonttype":42})
fig,axs=plt.subplots(2,1,figsize=(3.5,3.65),sharex=True)
fig.subplots_adjust(left=.18,right=.97,bottom=.13,top=.90,hspace=.38)
axs[0].plot(yaw,share[:,0],color="#0072B2",lw=1.15,marker="o",markevery=15,ms=3,mfc="white",label=r"$P_+/(P_++P_-)$")
axs[0].plot(yaw,share[:,1],color="#D55E00",lw=1.15,ls="--",marker="s",markevery=15,ms=3,mfc="white",label=r"$P_-/(P_++P_-)$")
axs[0].set_ylabel("Port power fraction");axs[0].set_ylim(-.04,1.04);axs[0].set_yticks([0,.5,1])
handles,_=axs[0].get_legend_handles_labels()
axs[0].legend(handles,[r"$+45^\circ$ RX",r"$-45^\circ$ RX"],loc="lower center",bbox_to_anchor=(.55,1.01),ncol=2,frameon=False,handlelength=1.8,columnspacing=1,borderpad=0)
axs[0].text(.0,1.045,"(a)",transform=axs[0].transAxes)
axs[1].plot(yaw,s,color="black",lw=1.2,marker="o",markevery=15,ms=3,mfc="white")
axs[1].axhline(0,color=".65",lw=.6,ls=":")
axs[1].set_ylabel(r"Normalized power difference $s$")
axs[1].set_ylim(-1.08,1.08);axs[1].set_yticks([-1,-.5,0,.5,1])
axs[1].set_xlabel(r"Robot azimuth $\psi$ (deg)")
axs[1].text(.0,1.045,"(b)",transform=axs[1].transAxes)
for ax in axs:
    ax.set_xlim(0,360);ax.set_xticks([0,90,180,270,360]);ax.tick_params(direction="in",top=True,right=True,length=3,width=.6)
    ax.grid(True,lw=.4,color=".87")
fig.canvas.draw()
# Check all text extents against the figure rectangle.
renderer=fig.canvas.get_renderer();fw,fh=fig.canvas.get_width_height()
outside=[]
for item in fig.findobj(matplotlib.text.Text):
    if item.get_visible() and item.get_text():
        bb=item.get_window_extent(renderer)
        if bb.x0<-.5 or bb.y0<-.5 or bb.x1>fw+.5 or bb.y1>fh+.5: outside.append(item.get_text())
assert not outside, outside
for ext in ("pdf","svg","png"):
    fig.savefig(BASE/f"fig01_los_azimuth.{ext}",dpi=600)
manifest=dict(question_id="FIG-LOS-AZIMUTH-001",role="IMPLEMENTER",scope="Manuscript figure; deterministic direct-only SourceFFD evaluation, no RT or EKF performance runs",
source_repo="myoungsunk/sionna-resimulation",source_branch="writing/dual-lp-paper-physical-observation-model-results-20261102",source_commit="61475a1f12071cb0fcdbd62a728d833f1d6732b5",
governance_note="Repository governance is scoped to MBVAR-INFO, outside this figure task. Local COMMON_CONTRACT + IMPLEMENTER used.",
case=case,robot_xy_m=[7,0],yaw_deg=[0,360,2],frequencies_hz=[6250400000.,6749600000.,1950000.],noise=None,channel="direct-only SourceFFD, not measured data or a new Sionna RT run",inputs=inputs,
checks=dict(samples=181,s_min=float(s.min()),s_max=float(s.max()),periodic_s_error=float(abs(s[0]-s[-1])),separate_field_implementation_max_abs_H=max(errors),finite_and_domain=True,text_within_canvas=True),
format=dict(width_in=3.5,height_in=3.65,font="Times New Roman",text_pt="9-10",png_dpi=600,pdf="vector; embedded TrueType fonts",caption="outside graphic"),
timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),command="python build_figure.py",python=sys.version,numpy=np.__version__,matplotlib=matplotlib.__version__,review="SELF_CHECK_ONLY; no independent audit or scientific adoption")
for name in ("COMMON_CONTRACT.md","ROLE_IMPLEMENTER.md"):
    p=Path("C:/Users/Myoungsun Kim/.codex/research-governance")/name
    manifest.setdefault("governance_sha256",{})[name]=hashlib.sha256(p.read_bytes()).hexdigest()
manifest["files"]={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in BASE.rglob("*") if p.is_file() and p.suffix in (".py",".csv",".png",".pdf",".svg",".json") and p.name!="manifest.json"}
(BASE/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(manifest["checks"],indent=2))
