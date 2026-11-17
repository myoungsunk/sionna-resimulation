def flat(d,p=""):
    out={}
    if isinstance(d,dict):
        for k,v in d.items(): out.update(flat(v,f"{p}/{k}"))
    elif isinstance(d,list):
        for i,v in enumerate(d): out.update(flat(v,f"{p}[{i}]"))
    else: out[p]=d
    return out
def compare(a,b,tol=1e-6):
    A,B=flat(a),flat(b); bad=[]
    for k in set(A)|set(B):
        x,y=A.get(k),B.get(k)
        if isinstance(x,(int,float)) and isinstance(y,(int,float)) and not isinstance(x,bool):
            if abs(x-y)>tol*max(1,abs(y)): bad.append((k,x,y))
        elif x!=y: bad.append((k,x,y))
    return bad
