# 집계 코드 독립 감사

VERDICT: ACCEPT. 감사자: /root/ablation_audit.

analyze_fixed_weight_comparison.py는 동일 prior 비교의 시간·GT·prior·공분산·gate 일치 후 집계한다. 재귀와 one-step, donor·조건·채널·range를 구분하며 `<1/3` 층화는 Cauchy 가중치 기준의 기술통계로 제한한다. manifest 해시·parity·schema 및 단계별 63 입력/252 재귀/504 one-step 셀을 확인한다. 원시 trace에서 각 metric을 재계산해 CSV와 1e-10 이내로 대조한다. 경로/seed별 결과와 pooled 결과를 구분한다.

중대한 집계·짝짓기 오류 없음. 필수 수정 없음. 실제 산출물과 최종 결론은 별도 결과 감사 대상이다.
