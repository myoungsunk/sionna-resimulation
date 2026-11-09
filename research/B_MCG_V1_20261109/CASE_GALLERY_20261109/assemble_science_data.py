#!/usr/bin/env python3
"""Recreate the exact research data/code ZIP and unpack after SHA validation."""
from pathlib import Path
import argparse, base64, hashlib, zipfile
ROOT=Path(__file__).resolve().parent
PARTS=ROOT/"SCIENCE_DATA_PARTS"
NAME="B_MCG_CASEBOOK_SCIENCE_DATA_20261109.zip"
EXPECTED_SIZE=3809078
EXPECTED_SHA256="75098d5ca6803c90f762e283b381701b7a068ee47d9eea0322543bb5095203e4"
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--extract",action="store_true",help="Extract into gallery folder, never overwrite differing files")
    args=parser.parse_args()
    payload="".join((PARTS/f"part_{i:02d}.txt").read_text("ascii").strip() for i in range(8))
    data=base64.b64decode(payload,validate=True)
    assert len(data)==EXPECTED_SIZE,(len(data),EXPECTED_SIZE)
    assert hashlib.sha256(data).hexdigest()==EXPECTED_SHA256,"SHA256_MISMATCH"
    output=ROOT/NAME
    if output.exists():assert output.read_bytes()==data,"EXISTING_FILE_DIFFERS"
    else:output.write_bytes(data)
    print("SOURCE_ZIP_SHA_PASS",NAME,EXPECTED_SHA256,len(data))
    if args.extract:
        with zipfile.ZipFile(output) as z:
            assert z.testzip() is None,"ZIP_CRC_FAIL"
            for info in z.infolist():
                if Path(info.filename).name!=info.filename:raise ValueError("UNSAFE_MEMBER_NAME")
                dest=ROOT/info.filename
                expected=z.read(info)
                if dest.exists():assert dest.read_bytes()==expected,("EXISTING_FILE_DIFFERS",str(dest))
                else:dest.write_bytes(expected)
                print("SHA_RESTORED",info.filename,len(expected))
if __name__=="__main__":main()
