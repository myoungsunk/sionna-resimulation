"""IEEE-sized redraw of supplied F01 data; no model or filter execution."""
from pathlib import Path
import json, hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image
import pymupdf

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
src=ROOT/"tables/THREE_STAGE_COMPARISON_12_BIASES.csv"
data=pd.read_csv(src)
routes=["R2-B","R4-B","R5-B"]
stages=["Direct LoS — zero mean","Full multipath — BB_ORIG","Full multipath — MB_VAR"]
sel=data[(data.bias=="B0")&data.stage.isin(stages)].copy()
assert len(sel)==9 and not sel.duplicated(["route","stage"]).any()
assert np.isfinite(sel[["head_rmse_deg","xy_rmse_cm"]].values).all()
sel.to_csv(OUT/"F01_plot_data.csv",index=False,encoding="utf-8-sig")
plt.rcParams.update({"font.family":"Times New Roman","font.size":9.5,
 "axes.labelsize":9.5,"axes.titlesize":9.5,"xtick.labelsize":9.5,
 "ytick.labelsize":9.5,"legend.fontsize":9.5,"axes.linewidth":.65,
 "hatch.linewidth":.45,"pdf.fonttype":42,"ps.fonttype":42,
 "mathtext.fontset":"stix","svg.fonttype":"none","savefig.facecolor":"white"})
fig,axs=plt.subplots(1,2,figsize=(7.16,2.9))
fig.subplots_adjust(left=.075,right=.99,bottom=.23,top=.83,wspace=.27)
styles=[("#b9d8ec","//",r"LoS-only ($\mu=0$)"),
        ("#e1a27d","",r"Full: BB_ORIG"),
        ("#b5d4c0","xx",r"Full: MB_VAR")]
x=np.arange(3);width=.225
for ax,col,ylabel,panel in zip(axs,["head_rmse_deg","xy_rmse_cm"],
 ["Heading RMSE (deg)","Position RMSE (cm)"],["(a) Heading","(b) Planar position"]):
 for j,(stage,(color,hatch,label)) in enumerate(zip(stages,styles)):
  vals=sel[sel.stage==stage].set_index("route").loc[routes,col].to_numpy()
  ax.bar(x+(j-1)*width,vals,width,color=color,edgecolor="#222222",
         linewidth=.5,hatch=hatch,label=label)
 ax.set_ylabel(ylabel)
 ax.set_xticks(x,routes)
 ax.set_ylim(0,1.65 if col=="head_rmse_deg" else 10.5)
 ax.spines[["top","right"]].set_visible(False)
 ax.tick_params(direction="out",length=3,width=.6)
 ax.set_axisbelow(True);ax.grid(axis="y",color=".86",linewidth=.4)
 ax.text(.5,-.24,panel,transform=ax.transAxes,ha="center",va="top",fontsize=9.5)
fig.legend(*axs[0].get_legend_handles_labels(),loc="upper center",bbox_to_anchor=(.52,.995),
           ncol=3,frameon=False,handlelength=1.8,columnspacing=1.7)
# Verify every text extent stays inside the fixed paper canvas.
fig.canvas.draw()
renderer=fig.canvas.get_renderer()
for obj in fig.findobj(matplotlib.text.Text):
 if obj.get_visible() and obj.get_text():
  bb=obj.get_window_extent(renderer)
  assert bb.x0>=-1 and bb.y0>=-1 and bb.x1<=fig.bbox.width+1 and bb.y1<=fig.bbox.height+1, obj.get_text()
name="F01_THREE_STAGE_B0_PERFORMANCE_IEEE"
for ext in ["png","pdf","svg"]:
 fig.savefig(OUT/f"{name}.{ext}",dpi=600)
plt.close(fig)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((ROOT/"PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
original_checks=[]
for item in manifest["files"]:
 p=ROOT/item["path"]
 original_checks.append(p.exists() and sha(p)==item["sha256"])
assert all(original_checks), "Supplied package hash mismatch"
pdf=pymupdf.open(OUT/f"{name}.pdf")
page=pdf[0]
assert abs(page.rect.width/72-7.16)<.001
assert abs(page.rect.height/72-2.9)<.001
fonts=page.get_fonts(full=True)
assert fonts and all(pdf.extract_font(f[0])[3] for f in fonts)
with Image.open(OUT/f"{name}.png") as im:
 assert im.size==(4296,1740)
 dims=im.size
report={"figure":"F01","review_order":"1/13","activity":"format-only redraw from supplied CSV",
 "created_utc":datetime.now(timezone.utc).isoformat(),
 "source_csv":str(src),"source_sha256":sha(src),"selected_rows":9,
 "package_file_hashes_checked":len(original_checks),"package_hashes_pass":all(original_checks),
 "size_inches":[7.16,2.9],"font":"Times New Roman","font_path":font_manager.findfont("Times New Roman"),
 "text_size_pt":9.5,"png_dpi":600,"png_pixels":dims,"pdf_fonts_embedded":True,
 "new_filter_or_RT_execution":False,
 "caveat":"LoS mean=0; Full arms keep archived mean corrections. Not a single-factor multipath causal comparison.",
 "outputs":{p.name:sha(p) for p in OUT.glob(name+".*")}}
(OUT/"F01_format_check.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"rows":9,"size_inches":report["size_inches"],"package_hash_checks":len(original_checks),
 "embedded_fonts":True,"png_pixels":dims}))

