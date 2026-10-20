"""Publish T8 preserved row certificates and static observation summaries only."""
from pathlib import Path
import csv,json,hashlib,shutil,math
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def write(p,rows):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 root=HERE/'execution_39361554110';result=root/'t8_mapping';meta=json.loads((root/'ACTIONS_ARTIFACT.json').read_text());m=json.loads((result/'MANIFEST.json').read_text());summary=json.loads((result/'SUMMARY.json').read_text())
 assert m['technical']=='TECHNICAL_PASS' and int(m['actions_run_id'])==39361554110 and not m['recursion_executed']
 assert len(summary)==4 and all(r['recursive_status']=='BLOCKED_INPUT' and not r['recursive_binding_certified'] for r in summary)
 for name in ['ROW_CERTIFICATE.csv','STATIC_POSE_MATCHES.csv','STATIC_RF_COMPARISON.csv','SUMMARY.json']:shutil.copyfile(result/name,HERE/name)
 rows=read(HERE/'STATIC_RF_COMPARISON.csv');groups={}
 for r in rows:
  assert r['scope']=='STATIC_SAME_POSE_SINGLE_OBSERVATION_NOT_EKF';groups.setdefault((r['case'],int(r['mount_deg'])),[]).append(r)
 stats=[]
 for (case,mount),rs in sorted(groups.items()):
  paired=[r for r in rs if r['full_valid']=='True' and r['los_valid']=='True'];los=[r for r in rs if r['los_valid']=='True']
  rms=lambda key:math.sqrt(sum(float(r[key])**2 for r in paired)/len(paired))
  stats.append(dict(case=case,mount_deg=mount,n_rows=len(rs),n_paired_valid=len(paired),n_los_valid=len(los),delta_s_rms=rms('full_minus_los_s'),delta_range_rms_m=rms('full_minus_los_range_m'),fp_mismatch_fraction=sum(r['FP_mismatch']=='True' for r in paired)/len(paired),los_saturation_fraction=sum(r['los_abs_s_gt_0p95']=='True' for r in los)/len(los),scope='STATIC_SAME_POSE_SINGLE_OBSERVATION_NOT_EKF'))
 assert len(stats)==8 and len(rows)==11220
 write(HERE/'STATIC_RF_SUMMARY.csv',stats)
 cert=read(HERE/'ROW_CERTIFICATE.csv');fail=sum(r['pass_']=='False' for r in cert)
 m.update(scientific='BLOCKED_INPUT',scientific_scope='M1 ordered pose/time binding for recursion; static measured-observation comparisons are limited diagnostics only',artifact_id=meta['id'],artifact_sha256=meta['digest'],source_commit=meta['workflow_run']['head_sha'],recursive_status='BLOCKED_INPUT',n_recursive_certified=0,n_requested=4,n_row_certificates=len(cert),n_failed_rows=fail,n_static_rows=len(rows),n_static_pose_pairs=sum(s['static_matched_rows'] for s in summary),same_pose_static_heading_or_ekf=False)
 m['recovery']=dict(whole_archive_sha256_verified=True,raw_npz_downloaded=False,artifact_metadata_sha256=sha(root/'ACTIONS_ARTIFACT.json'),source_manifest_sha256=sha(result/'MANIFEST.json'),source_summary_sha256=sha(result/'SUMMARY.json'),release_receipts={route:dict(path=str((root/f'legacy_snapshot/{route}/RESTORE_RECEIPT.json').relative_to(HERE)).replace('\\','/'),sha256=sha(root/f'legacy_snapshot/{route}/RESTORE_RECEIPT.json')) for route in ['R4','R5']},execution_files={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in root.rglob('*') if p.is_file()})
 m['outputs']={n:sha(HERE/n) for n in ['ROW_CERTIFICATE.csv','STATIC_POSE_MATCHES.csv','STATIC_RF_COMPARISON.csv','STATIC_RF_SUMMARY.csv','SUMMARY.json']}
 (HERE/'MANIFEST.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 text='# T8 재생성 M45 시간 바인딩 결과\n\n계산 TECHNICAL_PASS; 재귀 입력 인증 과학 판정 BLOCKED_INPUT. Actions run39361554110 / artifact12237048283에서 4조건 모두 ordered pose/time 바인딩에 실패했다. 재귀 EKF·B0/L2 Heading·visit skip 비교는 실행하지 않았다.\n\n|조건|M0/M45 행수|동일 ID의 geometry 불일치|인증된 기준 clock 없는 행|정적 pose 쌍|재귀|\n|---|---:|---:|---:|---:|---|\n'
 for s in summary:text+=f"|{s['case']}|{s['reference_n']}/{s['m45_n']}|{s['reference_clock_geometry_mismatch_rows']}|{s['reference_clock_missing_rows']}|{s['static_matched_rows']}|BLOCKED_INPUT|\n"
 text+=f'\n행별 인증 {len(cert)}행 중 {fail}행 실패다. 같은 pose_id 또는 같은 행수는 같은 geometry/clock 인증이 아니다. 원 M0 Tnone과 재생성 T10 first-visit의 완전한 pose·시간·body yaw·antenna yaw 대응이 필요하다. 없는 clock을 추정하거나 일치하지 않는 pose_id의 시간을 붙이지 않았다.\n\n'
 text+='Geometry-only matching은 위치≤1mm·body yaw≤.01°·antenna=body+45°를 충족하는 pose만 사용했다. 총 5,610개 pose 쌍에서 M0/M45 각각 관측하여 STATIC_RF_COMPARISON.csv 11,220행을 보존했다. 모호한 후보와 미매칭 pose는 모두 0이다. 이 비교는 정적 단일 RF 관측 비교이며 EKF one-step 상태 갱신이나 Heading 개선 검증이 아니다.\n\n|조건|mount|Δs RMS|Full/LoS FP 불일치|LoS |s|>.95|\n|---|---:|---:|---:|---:|\n'
 for s in stats:text+=f"|{s['case']}|{s['mount_deg']}|{s['delta_s_rms']:.6f}|{s['fp_mismatch_fraction']:.3%}|{s['los_saturation_fraction']:.3%}|\n"
 text+='\n위 수치는 인증된 정적 전체 pose 집합의 요약이며 x10–16 V1/V2 시간 구간 통계로 해석하지 않는다. Native LoS의 무효 행을 생성·대체하지 않았다. 모든 원본 detector는 고정 Hann/4N IFFT·strongest RX30% leading edge·공통 tap을 사용한다.\n\n원본 코드 commit: `'+meta['workflow_run']['head_sha']+'`. artifact SHA256: `'+meta['digest']+'`. MANIFEST에 SourceFFD observer·원 RF·M45 RF·pose·lock·release multipart asset의 SHA와 receipt를 보존했다. 기존 실패 execution_r01/r02/r03도 삭제하지 않았다.\n\n## 주장하지 않는 것\n\n정적 비교로 시간 바인딩, 재귀 Heading/gyro bias 개선, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 이번 결과는 T10 first-visit pose 집합의 관측 대비이며 M0 Tnone 궤적 재귀의 대체물이 아니다.\n'
 text=text.replace('|LoS |s|>.95|','|LoS abs(s)>.95|')
 (HERE/'RESULTS_KO.md').write_text(text,encoding='utf-8')
 print(json.dumps({k:m[k] for k in ['technical','scientific','source_commit','n_row_certificates','n_failed_rows','n_static_rows','n_static_pose_pairs']}))
if __name__=='__main__':main()
