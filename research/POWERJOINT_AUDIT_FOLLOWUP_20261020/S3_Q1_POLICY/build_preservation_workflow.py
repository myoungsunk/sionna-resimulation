"""Generate the S3-only archive preservation job once compute is sufficiently advanced."""
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
 t=(ROOT/'.github/workflows/powerjoint-audit-followup-s2-preserve.yml').read_text().replace('S2','S3').replace('s2','s3').replace('timeout-minutes: 160','timeout-minutes: 360')
 t=t.replace('S3_N2_GEOMETRY','S3_Q1_POLICY').replace('powerjoint-audit-followup-s3-preserve.yml','powerjoint-audit-followup-s3-preserve-retry1.yml')
 t=t.replace('39374401047 39374960558 39375140765 39375368147 39375649673 39375791934','39378144903 39378550447 39380336271 39380603592')
 (ROOT/'.github/workflows/powerjoint-audit-followup-s3-preserve-retry1.yml').write_text(t)
if __name__=='__main__':main()
