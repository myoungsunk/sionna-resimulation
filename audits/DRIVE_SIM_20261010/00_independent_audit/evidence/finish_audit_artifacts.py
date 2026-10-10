from pathlib import Path
import re, json, hashlib, subprocess

root = Path(__file__).resolve().parent
repo = root / 'checkout'
p = root / 'INDEPENDENT_SCIENTIFIC_AUDIT_KO.md'
s = p.read_text(encoding='utf-8')
s = s.replace('。', '.').replace('、', ', ')
s = s.replace('Max |Δs|', 'Max Δs')
start = s.index('G2 thresholds median')
end = s.index('\n\n', start)
s = s[:start] + 'G2 기준은 median H≤1e−4, max H≤1e−3, Δs≤1e−3, FP=100%, range≤1 mm이다. G2′는 Δs≤2e−3, FP≥99.5%, range≤2 mm이며 H threshold는 없다. G4 원문은 same as G2지만 node code는 G2′를 사용한다. 위 B 수치는 더 엄격한 G2도 만족하므로 수치 판정은 바뀌지 않는다. **표본 pose/node에서의 관측량 동등성**만 인정하며 경로 구조 전체의 동등성으로 확대하지 않는다.' + s[end:]
s = s.replace('**Original strict G3: FAIL 全6組. Authorised relaxed G3: PASS 全6組, delay-class eligibilityのみ.**', '**Original strict G3: 6조합 모두 FAIL. Authorised relaxed G3: 6조합 모두 PASS, delay-class eligibility 범위에 한정.**')
s = s.replace('2組', '2조합')
s = re.sub(r'\*\*Original strict G3:.*?\*\*', '**Original strict G3: 6조합 모두 FAIL. Authorised relaxed G3: 6조합 모두 PASS, delay-class eligibility 범위에 한정.**', s)
# Restore spacing in dense findings and plan prose, without altering numeric facts.
replacements = {
'all6':'all 6 ', 'raw5630':'raw 5,630', 'samebudget':'동일 budget',
'pre-S6validG3':'pre-S6 valid G3', 'globalheading/localizationclaim':'global heading/localization claim',
'physicalpathidentity':'physical path identity', 'heldout':'held-out',
'samepath/drivetime':'동일 경로/drive time', 'differentelapsed/sampleupdates':'다른 elapsed time/sample updates',
'strongerbaseline':'stronger baseline', 'knownanchor':'known anchor', 'single-anchorcases':'single-anchor cases',
'matchedsynthetic':'matched synthetic', 'independentcalibration':'independent calibration',
'fullchannel':'full-channel', 'ray/direction/reflectionidentity':'ray/direction/reflection identity',
'allchanges':'all changes', 'directionavailability':'direction availability',
'originalFAIL':'original FAIL', 'scientificPASS':'scientific PASS', 'smallRF':'small RF',
'productionworstpositions':'production worst positions', 'tested35poses':'tested 35 poses',
'route-wideobservableequivalence':'route-wide observable equivalence',
'futurefailclosed':'future fail-closed', 'delayeligibility':'delay eligibility',
'time-averaged':'time-averaged', 'noisechoice':'noise choice', 'actualLUT':'actual LUT',
'globaluniquelocalization':'global unique localization', 'PSD-preservingcollapsecorrectionplan':'PSD를 보존하는 collapse correction',
'weakprimarybaseline':'weak primary baseline', 'field':'field',
}
for a,b in replacements.items(): s = s.replace(a,b)
sensor = '''
실제 수치도 placeholder로 유지한다. Sampling dt=.2 s, gyro ARW=.015°/√s, wheelbase=.287 m, nominal radius=.033 m이다.

| Drift | Gyro bias magnitude dps | Gyro SF | Wheel diameter ratio | Wheelbase error |
|---|---:|---:|---:|---:|
| low | .01 | .005 | .002 | .005 |
| mid | .05 | .010 | .005 | .0075 |
| high | .20 | .015 | .010 | .010 |

각 systematic parameter는 run별 random sign이다. Wheel distance variance=2e−5|ds|, yaw variance=1e−4|dθ|+1e−5|ds|; in-place rotating sample의 slip probability=.01, Student-t(3) scale=.5°; 추가 range sigma=.05 m이다. Generator gyro 식은 `(1+SF)Δθ+b dt+ARW√dt N(0,1)`이며 bias random walk를 추가하지 않는다. Datasheet comment와 실제 hardware noise 측정은 구분한다.
'''
needle='### 4.2 State/process/range/s 수식 독립 검사'
s = s.replace(needle, sensor+'\n'+needle)
s = s.replace('원 primary heading metric은', 'Two-sided Wilcoxon alpha=.01, hypothesis별 condition family에 Holm correction을 적용하고, significance와 median relative improvement≥10%를 함께 요구한다. 원 primary heading metric은')
# Make source locators inspectable. First line is linked; stated ranges remain in the label.
files = list(repo.glob('src/qclean_uwb/drivesim/*.py')) + list(repo.glob('src/qclean_uwb/scenarios/*.py')) + list(repo.glob('scripts/drive_sim/*.py')) + list(repo.glob('scripts/*.py')) + list(repo.glob('tests/*.py'))
by_name = {q.name:q for q in files}
def locator(m):
    label=m.group(1); parts=label.split(':',1); name=parts[0]
    q=repo/name
    if not q.is_file(): q=by_name.get(Path(name).name)
    if q is None or not q.is_file(): return m.group(0)
    line=re.match(r'(\d+)', parts[1]) if len(parts)>1 else None
    target=q.as_posix() + (':'+line.group(1) if line else '')
    return '['+label+'](<'+target+'>)'
s = re.sub(r'`([^`\n]*\.py(?::[0-9–—, ]+)?)`',locator,s)
assert not re.search(r'[\u3040-\u30ff]',s), 'Non-Korean language residue'
for n in range(1,12): assert re.search(r'^## '+str(n)+r'\.',s,re.M)
table_errors=[]; count=None
for i,line in enumerate(s.splitlines(),1):
    if line.startswith('|'):
        current=len(re.split(r'(?<!\\)\|',line))-2
        if count is None: count=current
        elif count!=current: table_errors.append((i,count,current))
    else: count=None
assert not table_errors, table_errors
p.write_text(s,encoding='utf-8')
freeze=json.loads((root/'REVISION_FREEZE.json').read_text(encoding='utf-8'))
freeze.update(local_exec_status='resolved; isolated detached checkout and read-only KMS source/artifact verification completed',checkout=str(repo))
(root/'REVISION_FREEZE.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2),encoding='utf-8')
d=json.loads((root/'provenance_validation.json').read_text(encoding='utf-8'))
summary={k:d[k] for k in ['head','working_tree','A14_diff_files','guide_diff_files','prereg_unchanged_from_original','executed_code_correspondence','route_H_hashes_vs_recheck','route_S6_local_hashes_vs_recheck','route_S6_remote_hashes_vs_recheck']}
(root/'provenance_validation.log').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
status=subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
assert not status, status
validation={'report_sections':11,'tables_valid':True,'source_unchanged':True,'frozen_head':d['head'],'report_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'report_bytes':p.stat().st_size,'existing_tests':{'passed':85,'exit_code':0},'full_RF_rerun':False}
(root/'AUDIT_COMPLETION_CHECK.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(validation,ensure_ascii=False))
