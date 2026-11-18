import numpy as np, pandas as pd
SW=pd.read_csv("SWEEP_FEATURES.csv.gz")
SW["rb"]=np.where(SW.rho<3,"<3",np.where(SW.rho<6,"3-6",">=6"))
SW["xi"]=np.round(SW.x_eval/0.45,0).astype(int); SW["yi"]=np.round(SW.y_eval,2); SW["yw"]=np.round(SW.yaw_deg).astype(int)
pd.set_option("display.width",200)
def corr_pairs(a,b):
    return np.corrcoef(a,b)[0,1] if len(a)>20 else np.nan
for lab in ("e_r","e_s"):
    print(f"===== {lab}: 상관 (같은 거리 bin, 평균 제거 후)")
    for rb in ("<3","3-6",">=6"):
        d=SW[SW.rb==rb].copy(); d["v"]=d[lab]-d[lab].mean()
        piv=d.pivot_table(index=["yi","yw"],columns="xi",values="v")   # along x, same y and yaw
        rx={k:corr_pairs(*[np.concatenate(z) for z in zip(*[(piv[c].values,piv[c+k].values) for c in piv.columns if c+k in piv.columns])]) if any(c+k in piv.columns for c in piv.columns) else np.nan for k in (1,2,3)}
        # across y at same x, yaw
        pv=d.pivot_table(index=["xi","yw"],columns="yi",values="v"); ys=sorted(pv.columns); ry={}
        for i in range(len(ys)):
            for j in range(i+1,len(ys)):
                dy=round(abs(ys[j]-ys[i]),2); m=pv[[ys[i],ys[j]]].dropna()
                if len(m)>20: ry.setdefault(dy,[]).append(np.corrcoef(m[ys[i]],m[ys[j]])[0,1])
        ry={k:round(np.mean(v),2) for k,v in sorted(ry.items())}
        # across yaw at same position
        pw=d.pivot_table(index=["xi","yi"],columns="yw",values="v"); yws=sorted(pw.columns); rpsi={}
        for k in (1,2,3,6):
            a=[];b=[]
            for i,y0 in enumerate(yws):
                y1=yws[(i+k)%len(yws)]; m=pw[[y0,y1]].dropna(); a.append(m[y0].values); b.append(m[y1].values)
            rpsi[10*k]=round(corr_pairs(np.concatenate(a),np.concatenate(b)),2)
        print(f"  ρ {rb:4s} | Δx 0.45/0.9/1.35 m: {[round(v,2) for v in rx.values()]} | Δy: {ry} | Δψ 10/20/30/60°: {list(rpsi.values())}")
