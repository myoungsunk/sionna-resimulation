# T8 행별 시간·pose 인증

기존 `audit_regenerated_m45_mapping.py`는 archive inventory와 first-visit T10 소스 수령만 확인한다. 위치·body yaw·timestamp를 원래 Tnone sequence와 행별 비교하지 않으므로 그 결과만으로 자연 재귀를 승인할 수 없다. 기존 physics 코드는 catalog 내 Full−LoS 물리량만 비교하며 M0와 동일 pose 대조가 아니다.

`certify_mapping.py --source-root SOURCE --config INPUTS.json --out OUTPUT`는 원본 P0 manifest의 R4/R5 A/B M0 case를 기준으로 모든 재생성 M45 행을 인증한다. 재귀 인증은 길이·행순서·time·3D position·body yaw·antenna=body+45를 모두 요구한다. reference 길이 밖의 행이나 누락 원본 행도 실패 파일에 남긴다. pose_id나 CRC 일치는 인증 기준이 아니다.

설정 JSON에는 `cases` 목록이 필요하다. 각 항목은 `reference_case`(예: R4_aA_m0), `radio_pose`(RADIO_POSE.csv), `full_h`, `los_h`, 선택적 `source_receipt`, `metadata_evidence`, `radio_z_m`을 갖는다. 경로는 config 기준 또는 절대경로다. `radio_z_m`은 z_m 열이 없을 때만 사용하며, 독립적으로 확인한 height와 `metadata_evidence` 경로가 반드시 필요하다. CSV 열 이름이 다르면 `radio_columns`를 명시한다. 기본 키는 x_m,y_m,z_m,t_s,yaw_body_deg,yaw_antenna_deg다. reference 기본 키는 x,y,z_m,t_s,yaw_body_deg이며 reference z는 manifest의 robot_z_m로 인증한다.

행별 `ROW_CERTIFICATE.csv`, `STATIC_POSE_MATCHES.csv`, `SUMMARY.json`, `MANIFEST.json`, `RESULTS_KO.md`를 생성한다. config·원본 samples·RADIO_POSE·H·receipt·metadata의 hashes를 보존한다. `--static-physics`는 인증과 무관하게 인증된 정적 pose 쌍에서만 원본 observer의 M0/M45 RF 관측 차이를 `STATIC_RF_COMPARISON.csv`에 적는다. 이는 정지 pose의 단일 관측 비교이며 필터 상태 갱신 또는 재귀 Heading 결과가 아니다.

## 주장하지 않는 것

정적 동일 pose 비교로 시간 바인딩·Heading 개선을 주장하지 않는다. 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증도 주장하지 않는다. 인증 성공 시에도 이 준비 runner는 EKF 미실행으로 표시하며 후속 재귀는 Mother의 공통 runtime이 담당한다.
