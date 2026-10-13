import pathlib, subprocess, difflib, json, hashlib
root=pathlib.Path(__file__).parent
files=['research/DR_EKF_DIAGNOSIS_20261013/followup_v2/'+n for n in ['common.py','v3_second_order.py','v4_calibration.py','v5_independent.py']]+['tests/test_dr_ekf_followup_v2.py']
patch=[];meta=[]
for name in files:
 before=subprocess.check_output(['git','show','HEAD:'+name],cwd=root)
 after=(root/name).read_bytes()
 patch.extend(difflib.unified_diff(before.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True),fromfile='a/'+name,tofile='b/'+name))
 meta.append(dict(path=name,original_sha256=hashlib.sha256(before).hexdigest(),audited_sha256=hashlib.sha256(after).hexdigest()))
(root/'audit_evidence/audit_fixes.patch').write_text(''.join(patch),encoding='utf-8',newline='')
(root/'audit_evidence/source_changes.json').write_text(json.dumps(dict(base_commit='3032a58925ad4d1e3acec85865958e6580d79be7',changes=meta),indent=2),encoding='utf-8')
