import subprocess,sys,pathlib,json
root=pathlib.Path(__file__).resolve().parent/'execution_39359952488'
items={'O01':12237161269,'C03':12237146888,'O03':12236673976,'C02':12236504528,'C01':12236404720,'O02':12236009723}
for route,aid in items.items():
 out=root/route
 if (out/'ACTIONS_ARTIFACT.json').exists(): continue
 p=subprocess.run([sys.executable,'D:/tmp/powerjoint_collect_members.py',str(aid),str(out)],check=False)
 if p.returncode: raise SystemExit(p.returncode)
print('ALL_SIX_RECOVERED',flush=True)
