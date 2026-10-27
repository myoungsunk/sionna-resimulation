# W4 문구 대응 명확화

사용자 원문의 D2는 각 arm 자체의 delta_e_t=post-pre를 정의하고 T3는 그 부호 반전을 요구한다. 따라서 W4 주 판정은 아래 원문 대응으로 한다.
- C_FLIP의 absolute delta_e_t와 MB의 absolute delta_e_t가 반대 부호.
- C_FLIP의 heading bias 이동(arm-BB)과 MB의 heading bias 이동(MB-BB)이 반대 부호.
- |MB absolute delta_e_t|>0.1cm, |MB-BB heading bias|>0.01deg, post/pre 유효.

PROTOCOL.md에서 delta_e_t도 BB대비 gap으로 정의한 부분은 보조 판정으로 별도 유지한다. HYPOTHESIS_DECISIONS.csv의 T3_FLIP_LITERAL을 주 W4, T3_FLIP_GAP을 보조 W4로 분리한다. 두 결과를 함께 보고하여 해석 차이를 숨기지 않는다. 이 변경은 원문 지표 대응을 바로잡으며 실험 입력, seed, replay, 임계값은 바꾸지 않는다. C_FLIP 결과를 검사하기 전에 기록했다.
