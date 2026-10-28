#!/usr/bin/env python3
"""Verify ZIP-extracted patch package payload before applying anything."""
from __future__ import annotations
from pathlib import Path
import json,hashlib,sys
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'PATCH_PACKAGE_SHA256.json').read_text(encoding='utf-8'))
for rel,h in manifest['files'].items():
 p=ROOT/rel
 if not p.is_file():raise SystemExit(f'MISSING: {p}')
 got=hashlib.sha256(p.read_bytes()).hexdigest()
 if got!=h:raise SystemExit(f'SHA256 FAIL: {p}\n{got} != {h}')
print(f"[PASS] {len(manifest['files'])} patch package files SHA256 valid.")
