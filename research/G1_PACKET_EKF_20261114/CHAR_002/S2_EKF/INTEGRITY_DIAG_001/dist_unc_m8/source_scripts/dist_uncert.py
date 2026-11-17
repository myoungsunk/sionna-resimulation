import numpy as np, pandas as pd
D=np.degrees
Z=np.load("/home/claude/diag/station_sweep_errors.npz")
x,yaw,st,e,a=Z["x"],Z["yaw"],Z["st"],Z["es"],Z["a"]; rho=np.abs(x-10)
edges=np.array([0,1.5,3,4.5,6,7.5,9.01]); mids=(edges[:-1]+edges[1:])/2
b=np.digitize(rho,edges)-1
print("== 1. 학습: station sweep 거리 bin별 (n packet = 36 yaw × station 수)")
print("bin | n | A: σ_mp RMS | C: σ_θ (°) | C: σ_res | C 적합 R² (e² ~ a²) | 강건판(중앙): σ_θ°/σ_res")
T=[]
for k in range(len(mids)):
    m=b==k; ee=e[m]; aa=a[m]
    sA=np.sqrt(np.mean(ee**2))
    X=np.c_[aa**2,np.ones(m.sum())]; c,*_=np.linalg.lstsq(X,ee**2,rcond=None); c=np.maximum(c,1e-12)
    r2=1-np.sum((ee**2-X@c)**2)/np.sum((ee**2-np.mean(ee**2))**2)
    # robust: median-based on |e| in a^2 terciles via 1.4826*MAD scaling
    q=np.quantile(aa**2,[1/3,2/3]); g=np.digitize(aa**2,q); med=[(np.mean(aa[g==j]**2),(1.4826*np.median(np.abs(ee[g==j])))**2) for j in range(3)]
    Mx=np.array(med); cr,*_=np.linalg.lstsq(np.c_[Mx[:,0],np.ones(3)],Mx[:,1],rcond=None); cr=np.maximum(cr,1e-12)
    T.append(dict(lo=edges[k],hi=edges[k+1],sA=sA,st=np.sqrt(c[0]),sr=np.sqrt(c[1]),str_=np.sqrt(cr[0]),srr=np.sqrt(cr[1])))
    print(f"{edges[k]:.1f}-{edges[k+1]:.1f} | {m.sum()} | {sA:.4f} | {D(np.sqrt(c[0])):.2f} | {np.sqrt(c[1]):.4f} | {r2:.2f} | {D(np.sqrt(cr[0])):.2f} / {np.sqrt(cr[1]):.4f}")
T=pd.DataFrame(T)
# correlation length: same yaw, stations k apart (same side of anchor), standardized by bin RMS
print("\n== 상관: 같은 yaw, station 간격 Δx (0.45 m 배수), 같은 거리 bin 쪽")
zs=e/T.sA.values[b]
xs=np.unique(x); key={(round(xx,2),int(yy)):i for i,(xx,yy) in enumerate(zip(x,yaw))}
for lab,sel in [("근거리 ρ<3",lambda r:r<3),("3–6 m",lambda r:(r>=3)&(r<6)),("6–9 m",lambda r:r>=6)]:
    out=[]
    for kk in (1,2,3,4):
        p=[]
        for i,xx in enumerate(xs[:-kk]):
            x2=xs[i+kk]
            if not (sel(abs(xx-10)) and sel(abs(x2-10))) or (xx-10)*(x2-10)<0: continue
            for yy in range(-180,180,10):
                i1=key.get((round(xx,2),yy)); i2=key.get((round(x2,2),yy))
                if i1 is not None and i2 is not None: p.append((zs[i1],zs[i2]))
        p=np.array(p); out.append(np.corrcoef(p[:,0],p[:,1])[0,1] if len(p)>20 else np.nan)
    # yaw lag correlation within station
    yl=[]
    for lag in (1,2,3,4):
        p=[]
        for xx in xs:
            if not sel(abs(xx-10)): continue
            for yy in range(-180,180,10):
                y2=((yy+10*lag+180)%360)-180; i1=key.get((round(xx,2),yy)); i2=key.get((round(xx,2),y2))
                if i1 is not None and i2 is not None: p.append((zs[i1],zs[i2]))
        p=np.array(p); yl.append(np.corrcoef(p[:,0],p[:,1])[0,1])
    print(f"{lab}: Δx 0.45/0.9/1.35/1.8 m → "+" ".join(f"{v:+.2f}" for v in out)+" | Δψ 10/20/30/40° → "+" ".join(f"{v:+.2f}" for v in yl))
T.to_csv("/home/claude/diag/dist_uncert_table.csv",index=False)
