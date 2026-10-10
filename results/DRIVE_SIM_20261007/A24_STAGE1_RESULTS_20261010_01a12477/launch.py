import sys,importlib.util,json
from pathlib import Path
J=Path('/job');SRC=J/'source'
spec=importlib.util.spec_from_file_location('a24',SRC/'scripts/drive_sim/structured_noise_control.py');m=importlib.util.module_from_spec(spec);sys.modules['a24']=m;spec.loader.exec_module(m)
meta=json.loads((J/'SOURCE_REVISION.json').read_text())
m.git_info=lambda:dict(head=meta['head'],branch=meta['branch'],dirty_files=[],runtime_git_available=False,provenance_method=meta['provenance_method'],archive_sha256=meta['archive_sha256'],local_checkout_dirty_files=meta['dirty_files'])
sys.argv=[str(SRC/'scripts/drive_sim/structured_noise_control.py')]+sys.argv[1:];m.main()
