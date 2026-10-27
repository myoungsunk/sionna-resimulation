# Office Mount 0°/45° → Corridor 실행 결과

2026-10-27 Snowball(KMS)에서 입력 동결, Office 학습, held-route Corridor C_PWIDE 학습, 재귀 평가를 완료했다. **기술 검증은 PASS이며, Full 채널에서 Office PWIDE의 POWER 대비 개선은 확인되지 않았다.** 기존 RF 시뮬레이션 데이터를 사용한 보정기 학습·재귀 재생 결과다. 신규 RF 시뮬레이션이나 실제 로봇 실험을 수행한 결과가 아니다.

## 실행 범위와 검증

| 항목 | 실제 결과 |
|---|---|
| Office 입력 | O01/O02/O03, Mount 0°/45° 모두 사용 |
| 학습 행 | 1,150행; O01 384 / O02 414 / O03 352 |
| 제외 행 | Direct-LoS가 없는 472행은 기존 라벨 마스크 유지 |
| SourceFFD–Direct-LoS | 준비 단계 최대 절대차 2.654925×10⁻⁶, 고정 한계 0.05 이내 |
| Office 학습 | POWER 및 PCIR/PWIDE 완료; target 학습·튜닝 없음 |
| Corridor 학습 | R2/R4/R5별 outer held-route C_PWIDE 3개 완료 |
| 평가 사례 | R2_aA_m45, R2_aA_m0, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0 |
| 평가 조건 | 각 사례의 Full B0, Full L2, Direct-LoS B0: 총 21개 |
| 비교군 | 10 Arms × 21조건 = 210개 점수행 |
| 초기 상태 | 기존 고정 nominal 초기 상태; 초기 오차 factorial은 수행하지 않음 |
| C_POWER 기준선 | 21/21 PASS; 5개 지표 최대 절대차 2.373213×10⁻¹², 요구조건 **<10⁻⁷** |
| 시계열 재검증 | Arm별 시간·step 순서, 행 수, 유한성, 출력 SHA 확인 PASS |
| 점수 재계산 | t≥30초 자료에서 11개 지표 재계산 PASS; 최대 절대차 7.105428×10⁻¹⁵ |
| 코드 시험 | 전체 79/79 PASS; 새로운 Mount 학습 계약 시험 4개 포함 |

Office 내부 teacher는 검증 경로의 두 Mount를 함께 제외한다. 공간 중복 제외 후 teacher 행 수는 O01 458, O02 732, O03 400이다. 상세 기록은 [OFFICE_INNER_FOLD_AUDIT.json](OFFICE_INNER_FOLD_AUDIT.json)에 있다. Corridor의 외부 held-route와 내부 공간 제외도 기존 계약을 유지했다. R1은 사용하지 않았다.

## 주요 결과

아래 수치는 **각 조건의 7개 사례별 heading RMSE를 산술평균**한 값이다. 표본 전체를 합친 RMSE가 아니며, 7개 사례를 독립 공간 7개로 취급하지 않는다. 낮을수록 좋다.

| 조건 | C_POWER | C_PWIDE | O_POWER | O_PWIDE | O_PWIDE가 O_POWER보다 개선된 사례 |
|---|---:|---:|---:|---:|---:|
| Full B0 | 1.659° | 1.605° | 1.670° | 2.577° | 1/7 |
| Full L2 | 1.567° | 1.398° | 1.574° | 2.580° | 0/7 |
| Direct-LoS B0 | 1.465° | 2.214° | 1.548° | 1.336° | 4/7 |

Full B0에서 O_PWIDE는 O_POWER보다 평균 heading RMSE가 약 54.3% 증가했다. 평균 XY RMSE도 0.160 m → 0.255 m로 증가했다. 따라서 현재 입력·학습·재귀 prior 설정에서 PWIDE의 Full 채널 환경 전이 개선을 주장할 수 없다. Direct-LoS 대조군의 개선을 Full 채널의 개선으로 일반화할 수 없다.

일관성도 함께 확인해야 한다. Full B0의 O_POWER/O_PWIDE 평균 heading NEES는 각각 10.116/20.776, 명목 95% 구간의 평균 coverage는 50.92%/38.98%였다. RMSE뿐 아니라 불확실성 평가에서도 제한이 나타난다. C_PWIDE는 Full B0 평균 RMSE가 소폭 감소했지만 개선 사례는 2/7이고 coverage는 59.80% → 56.90%였다. 이 결과를 전체적인 우월성으로 해석하지 않는다.

전체 Arm 및 사례별 수치는 다음 파일에 보존했다.

- [ALL_TRANSFER_SCORES.csv](ALL_TRANSFER_SCORES.csv): 210개 점수행.
- [PAIRED_COMPARISONS.csv](PAIRED_COMPARISONS.csv): 동일 사례·조건의 POWER/PWIDE 및 교차 결합 차이.
- [CASE_MEAN_SCORES.csv](CASE_MEAN_SCORES.csv): 조건별 사례 산술평균.
- [VALIDATION_RECEIPT.json](VALIDATION_RECEIPT.json): 모든 조건의 재검증 결과.

## 과학적 해석 범위

편파 Gate 4개 Arm은 모두 **EXPLORATORY_GT_PROXY**다. Office GT 오차의 95분위수로 정한 임계값을 유지했으며, 실제 Office 재귀 prior의 d₀ 분포에 맞춘 보정이나 환경 전이 검증은 수행하지 않았다. Full B0에서 Gate를 적용한 O_PWIDE 평균 RMSE도 약 2.64–2.65°로, ungated O_PWIDE보다 개선되지 않았다. 이 결과는 정식 Gate의 유효성 판단을 대신하지 않는다.

O_POWER_C_PWIDE는 Office POWER로 추론하지만 Corridor POWER teacher 잔차로 학습한다. Full B0 평균 RMSE 1.529°는 **교차 결합 진단**이며, PWIDE 학습 환경만 바꾼 순수 효과가 아니다.

이번 실행에는 Office in-domain 재귀 성능 평가가 없다. 따라서 동일 모델의 Office→Corridor 성능 저하량은 아직 산출하지 않았다. Corridor에서 O_POWER 대비 O_PWIDE의 변화와 Corridor held-route 대조군의 결과까지가 이번 근거의 범위다. 결과를 본 뒤 임계값·seed·학습 조건을 변경하거나 선택적으로 재실행하지 않았다.

## 보존·재현 자료

[EXECUTION_EVIDENCE.tar.gz](EXECUTION_EVIDENCE.tar.gz)에 21개 조건의 시간순 자료·점수·QA·C_POWER trace, Office/Corridor 학습 모델, frozen 입력 manifest, 실행 코드·시험·명령·종료코드·로그를 보존했다. 원본 RF와 안테나 bank 바이너리는 해시가 기록된 원래 위치에 보존했으며 중복 업로드하지 않았다. 이전 Mount 준비 산출물도 변경하지 않았다. 파일 이동·삭제는 수행하지 않았다.

입력 준비 커밋은 `e4ccdd737fac9961261b7483095a79e515297111`, 원래 transfer 수정 기준은 `33e9849be8c5c62d45eb7e5ade7e85438b8fa247`이다. 이번 실행에서는 Mount별 사례 키와 실제 장착각을 학습 경로에 전달하고, joint 입력 QA/manifest를 평가 시에도 재검증하도록 보강했다. 실행 당시 코드 SHA는 [EXECUTION_PLAN_02.json](EXECUTION_PLAN_02.json) 및 각 평가 QA에 고정되어 있다.

실행 이미지는 `sha256:adad98bb4db40f5ad272dd4fbb0a9ffc8bdabb527e476d683b06aee7fcc5fe59`다. 기존 P2 버전인 NumPy 2.3.3 / SciPy 1.16.2 / pandas 2.3.2 / scikit-learn 1.7.2를 사용했다. 네트워크를 차단한 컨테이너에서 평가했고, 첫 C_POWER 통과 후 나머지 조건을 최대 4개씩 병렬 실행했다. 호스트 Python과 원본 데이터는 변경하지 않았다.

최초 입력 동결은 Git attribute 객체가 없어 차단됐다. 필요한 고정 Git 객체를 보충하고 index를 갱신한 뒤 attempt02 전체 실행을 완료했다. 원본 소스·물리 모델·허용오차를 바꾸지 않았다. 실패 기록도 archive에 남겼다.

패키지 출처·archive 해시는 [DELIVERY_RECEIPT.json](DELIVERY_RECEIPT.json), 파일별 해시는 [SHA256SUMS.txt](SHA256SUMS.txt), 완료 조건은 [PIPELINE_RECEIPT.json](PIPELINE_RECEIPT.json)에 있다. 결과 확인의 다음 명령은 새로 풀어 둔 전달 폴더에서 `sha256sum -c SHA256SUMS.txt`다. 추가 학습·튜닝·평가는 별도 지시에 따른다.
