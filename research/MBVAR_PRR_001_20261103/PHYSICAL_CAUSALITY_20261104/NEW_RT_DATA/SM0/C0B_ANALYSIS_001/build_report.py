from pathlib import Path
import json,csv,hashlib,datetime
root=Path('D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0')
p=root/'C0B_ANALYSIS_001';out=p/'RESULTS_001'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def main():
 with (out/'SUMMARY.csv').open() as f:rows=list(csv.DictReader(f))
 if len(rows)!=15:raise ValueError('expected15')
 lines=['# C0-B — 선택된 15 pose의 복소 반사·검출 tap 분석','',
 '개정 SM0 데이터의 독립 수용 후 실행한 결과다. 실제 분석 채널은 원본 complex64 per-ray 위상을 semantic chain별 complex128로 합산했다. F64 채널은 별도 합산 검산에만 사용했다.','',
 'R4 8개, R5 6개, R2 1개를 모두 포함한다. R4 pose194는 보존 canary의 사후 개정 재검증 자료이며, 나머지14개는 개정 규약을 실행 전 고정해 새로 생성했다. 전체15개는 기존 결과를 보고 선택한 설명용 hotspot/대조다.','',
 '| 경로 | pose | Full/LoS tap | eMP | 같은 LoS tap 차이 | tap 선택 차이 | 고정 LoS tap에서 가장 큰 면 제거 효과 |','|---|---:|---|---:|---:|---:|---|']
 for r in rows:
  surface=r['strongest_fixed_los_surface'];delta=r['strongest_fixed_los_surface_delta_s']
  txt=surface+' ('+format(float(delta),'+.4f')+')' if delta else '정의 불가'
  lines.append(f"| {r['case'].split('_')[0]} | {r['pose_id']} | {r['fp_full']}/{r['fp_los']} | {float(r['e_mp']):+.4f} | {float(r['same_los_tap']):+.4f} | {float(r['detector_choice']):+.4f} | {txt} |")
 lines += ['', '면 제거 효과는 `원래 Full signed s − 해당 면에 닿는 모든 체인을 제거한 signed s`이며 단위는 signed polarization ratio다. 고정 LoS tap의 abs(delta_s)가 가장 큰 면을 표에 표시했다. 모든 면/체인의 고정 tap·재검출 결과는 각 pose의 surface_removal.csv와 attribution.csv에 보존했다. 여러 면이 같은 체인을 공유하므로 면 효과를 더하지 않는다.','']
 r2=next(r for r in rows if r['case'].startswith('R2'))
 r4small=next(r for r in rows if r['case'].startswith('R4') and r['pose_id']=='234')
 lines += [f"R2 pose525의 tap 이동은 {r2['tap_shift']}인데 eMP는 {float(r2['e_mp']):+.4f}다. 이 표본에서는 검출 tap 이동 없이 같은 tap에서의 복소 합 변화가 큰 편파비 차이를 만든다.", '',
 f"R4 pose234의 eMP는 {float(r4small['e_mp']):+.4f}다. 작은 순편파오차에서도 각 체인·면의 제거 효과와 두 포트 coherent power 항이 존재할 수 있으므로, 작은 eMP만으로 반사 부재를 뜻하지 않는다.", '',
 'same-tap과 tap-choice의 합은 eMP와 대수적으로 같지만 독립적인 물리 원인 비율이 아니다. chain별 signed ratio 제거 효과도 비선형이므로 합산 기여율로 읽지 않는다. 포트별 전력 배분은 direct–reflection 및 reflection–reflection cross term을 포함하고 전체 전력 차이와 closure를 검사했다.','',
 f"15개 표본에서 native/archive eMP 차이의 최대 절대값은 {max(abs(float(r['native_archive_e_mp_difference'])) for r in rows):.8g}, 분해 항등식 최대 잔차는 {max(float(r['identity_error']) for r in rows):.8g}다. Full/LoS 검출 tap은 각각 archive와 동일해야 하는 실행 게이트를 통과했다.",'',
 '정의 불가 카운트는 고정 tap과 재검출, chain과 surface를 각각 구별한다. 두 tap을 보고하므로 아래는 사건수가 아니라 출력 행수다.','']
 for key in ('undefined_surface_signed','undefined_surface_redetected','undefined_chain_signed','undefined_chain_redetected'):
  lines.append(f"- {key}: {sum(int(r[key]) for r in rows)}")
 lines += ['', '이 분석은 저장된 ray 성분을 제거하는 오프라인 시뮬레이션 반사실이다. 실제 벽을 제거해 새 scene에서 재시뮬레이션한 결과가 아니다. 과거 원본 ray 계수가 없어 역사적 경로의 완전 동일성은 미입증이다.','',
 '확인 범위는 선택된 pose의 포트 전력·signed polarization ratio·검출 tap이다. 새 RF 일반화, 자연 발생 빈도, 온라인 복구 guard 성능, EKF Heading/공분산 과신 인과성은 검증하지 않았다. C1–C3와 SM1/SM2는 실행하지 않았다.','',
 '수치 및 결과 해석의 최종 수용 범위는 audit/RESULT_AUDIT.md 및 결과 수용 문서를 따른다.']
 report=p/'RESULTS_KO.md';report.write_text('\n'.join(lines)+'\n',encoding='utf8')
 prov=dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),builder_sha256=sha(Path(__file__)),summary_sha256=sha(out/'SUMMARY.csv'),analysis_manifest_sha256=sha(out/'MANIFEST.json'),report_sha256=sha(report),independent_result_audit='PENDING')
 (p/'REPORT_PROVENANCE.json').write_text(json.dumps(prov,indent=2)+'\n')
 print('report_written',len(rows),'poses')
if __name__=='__main__':main()
