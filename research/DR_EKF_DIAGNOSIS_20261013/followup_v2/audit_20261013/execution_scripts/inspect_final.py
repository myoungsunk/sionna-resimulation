import pathlib,subprocess,json,collections
root=pathlib.Path.cwd();out=root/'audit_evidence/remote_f1d6d9fc';out.mkdir(exist_ok=True)
prefix='research/DR_EKF_DIAGNOSIS_20261013/'
paths=['cache/CACHE_D6_MANIFEST.json','package_d6_cache.py','out/D6_CONFIRMATION_s8100-8399.json','out/D6_CONFIRMATION_s8100-8399_CELLS.csv','out/MANIFEST_D6_CONFIRMATION_s8100-8399.json','out/D5_PF_VALIDATION.json','out/MANIFEST_D5_PF_VALIDATION.json','out/logs/README.md','D6_SPEC.json','dr_harness.py','dr_consistency.py']
listing=subprocess.check_output(['git','ls-tree','-r','f1d6d9fc',prefix],text=True)
(out/'git_tree.txt').write_text(listing)
for line in listing.splitlines():
 name=line.split('\t')[1]
 if '/out/logs/' in name and name.endswith('.log'):paths.append(name[len(prefix):])
for name in paths:
 p=out/name;p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(subprocess.check_output(['git','show','f1d6d9fc:'+prefix+name]))
m=json.loads((out/'cache/CACHE_D6_MANIFEST.json').read_text())
print(json.dumps(dict(count=len(m['files']),split=sum(v['stored_as']=='parts' for v in m['files'].values()),bytes=sum(v['bytes'] for v in m['files'].values()),arms=dict(collections.Counter(k.split('/')[0] for k in m['files']))),indent=2))
print((out/'out/D5_PF_VALIDATION.json').read_text())


