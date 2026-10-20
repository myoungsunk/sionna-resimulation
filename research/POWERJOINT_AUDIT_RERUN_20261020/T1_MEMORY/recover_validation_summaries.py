from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parent
items=[('T1_MEMORY/execution_new_unit_39361490496/C03',12237966255),('T1_MEMORY/execution_new_unit_39361490496/C02',12237831493),('T1_MEMORY/execution_new_unit_39361490496/O03',12237711741),('T1_MEMORY/execution_new_unit_39361490496/O01',12237188612),('T1_MEMORY/execution_new_unit_39361490496/O02',12237008363),('T1_MEMORY/execution_new_unit_39361490496/C01',12236883913),('T8_MAPPING/execution_39361554110',12237048283)]
for dest,aid in items:
 out=root.parent/dest
 if (out/'ACTIONS_ARTIFACT.json').exists():continue
 subprocess.run([sys.executable,'D:/tmp/powerjoint_collect_artifact.py',str(aid),str(out)],check=True)
print('ALL_SEVEN_RECOVERED',flush=True)
