"""Preparation regression tests; no solver import or runtime invocation."""
import ast,io,json,tarfile,tempfile,subprocess,sys
from pathlib import Path
from unittest.mock import patch
import unittest
import orchestrate as O

class PreparationTests(unittest.TestCase):
 def test_approval_gate(self):
  from approval_gate import authorized
  a=dict(approved=True,implementation_commit="abc",total_calls=79156,runners=4,workers=16,retries=0)
  self.assertTrue(authorized("push","1",None,None,a,"abc"))
  self.assertFalse(authorized("push","1",None,None,a,"other"))
  self.assertFalse(authorized("push","2",None,None,a,"abc"))
  self.assertFalse(authorized("push","1",None,None,dict(a,approved=False),"abc"))
 def test_partial_handoff_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);work=root/"work";out=root/"out";work.mkdir();out.mkdir()
   ids=[r["task_id"] for r in O.ledger()]
   O.dump(work/"inventory.json",dict(pending=ids[:308],reused={k:"preserved" for k in ids[308:]}))
   for group in ["B0","B1","SM1a","G3","inputs"]:(work/(group+".tar.gz")).write_bytes(b"fixture")
   (out/"shard_0.tar.gz").write_bytes(b"broken archive")
   subprocess.run([sys.executable,str(O.HERE/"collect.py"),str(work),str(out)],check=True)
   self.assertEqual(len(json.loads((out/"ALL_KEYS.json").read_text())),400)
   self.assertEqual(json.loads((out/"FINAL_QA.json").read_text())["status"],"INCOMPLETE")
   self.assertTrue((out/"handoff.tar.gz").is_file())
 def test_canary_corruption_rejected(self):
  from reuse_canary import verify
  with tempfile.TemporaryDirectory() as d:
   work=Path(d);(work/"shard_canary.tar.gz").write_bytes(b"invalid")
   with self.assertRaisesRegex(AssertionError,"CANARY_ARCHIVE_SHA"):verify(work)
 def test_registered_universe(self):
  rows=O.ledger()
  self.assertEqual(sum(int(r["expected_solver_calls"]) for r in rows),102860)
  self.assertEqual(len(rows),400)
 def test_canary_registered(self):
  rows=[r for r in O.ledger() if r["route"]=="R4_B" and r["pose_id"] in ("194","234") and r["source_track"]=="ORIGINAL_6_WALL_CORRIDOR"]
  self.assertEqual(len(rows),4)
  self.assertEqual(sum(int(r["expected_solver_calls"]) for r in rows),1028)
 def test_mutated_ledger_rejected(self):
  with patch.object(O,"sha",return_value="0"*64):
   with self.assertRaises(AssertionError):O.ledger()
 def test_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   archive=Path(d)/"bad.tar"
   with tarfile.open(archive,"w") as t:
    m=tarfile.TarInfo("../escape");m.size=1;t.addfile(m,io.BytesIO(b"x"))
   with self.assertRaises(AssertionError):O.safe_extract(archive,Path(d)/"target")
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   archive=Path(d)/"bad.tar"
   with tarfile.open(archive,"w") as t:
    m=tarfile.TarInfo("link");m.type=tarfile.SYMTYPE;m.linkname="/etc/passwd";t.addfile(m)
   with self.assertRaises(AssertionError):O.safe_extract(archive,Path(d)/"target")
 def test_source_syntax(self):
  for f in ["orchestrate.py","task.py","collect.py"]:
   ast.parse((O.HERE/f).read_text())
 def test_bindings_unique_complete(self):
  b=json.loads((O.HERE/"PR35_BINDINGS.json").read_text())
  self.assertEqual(len(b),24)
  self.assertTrue(all(len(v["raw_sha256"])==64 for v in b.values()))
 def test_asset_hashes_frozen(self):
  a=json.loads((O.HERE/"ASSETS.json").read_text())
  self.assertEqual({v["group"] for v in a.values()},{"inputs","B0","B1","SM1a","G3"})
  self.assertTrue(all(len(v["sha256"])==64 and v["size"]<=40*1024**2 for v in a.values()))
if __name__=="__main__":unittest.main()
