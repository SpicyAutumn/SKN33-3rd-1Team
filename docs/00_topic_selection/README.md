# 3차 프로젝트 주제 선정 진행 기록

> **현재 상태:** RAG 기반 AI 문화유산 지식 안내 서비스 방향으로 구체화 — 최종 서비스명·세부 MVP 지속 조정<br>
> **최근 현행화:** 팀장 및 A~F 역할 분담, 작업 기준안 `v0.1`, Track B 역할·생성 계약·Prompt Baseline 반영<br>
> **기록 기준일:** 2026-08-28  
> **저장소:** `SKN33-3rd-1Team`

이 디렉터리는 주제 확정 전까지 제안된 아이디어, 회의 발언, 개인 구체화안, 회의 후속 검토와 데이터 검증 과정을 보존합니다. `권장`, `검토`, `가능`으로 작성된 내용은 팀의 `합의`, `선정`, `결정`을 의미하지 않습니다.

## 1. 권장 열람 순서

1. [1차 주제 선정 및 사전 검토 기록](01_initial_review/topic_selection_summary.md)
2. [문화유산 도슨트 범위 검토 Q&A](01_initial_review/heritage_ai_docent_scope_qna.md)
3. [B2B·B2C 관점 주제 검토안](01_initial_review/project_topic_b2b_b2c_review.md) · [HTML](01_initial_review/project_topic_b2b_b2c_review.html)
4. [2차 회의 전 3개 변경 주제 검토안](01_initial_review/revised_topic_2_3_share.md) · [HTML](01_initial_review/revised_topic_2_3_share.html)
5. [2026-08-26 13:30 2차 회의록](02_meeting_records/topic_selection_meeting_2026-08-26.md)
6. [방문 도우미 + 문화유산 여행 도슨트 보완안](03_post_meeting_reviews/post_meeting_topic_1_heritage_travel_docent.md) · [HTML](03_post_meeting_reviews/post_meeting_topic_1_heritage_travel_docent.html)
7. [문화유산 기반 한국사 교육 주제 보완안](03_post_meeting_reviews/post_meeting_topic_2_heritage_learning_companion.md) · [HTML](03_post_meeting_reviews/post_meeting_topic_2_heritage_learning_companion.html)
8. [개인 성향 기반 홈 리셋 코치 제안서](03_post_meeting_reviews/home_reset_ai_project_proposal.html)
9. [2차 회의 결과 후속 이행 기록](03_post_meeting_reviews/post_meeting_topic_refinement_log.md) · [HTML](03_post_meeting_reviews/post_meeting_topic_refinement_log.html)
10. [2026-08-26 18:00 이후 주제 의견 요청 및 후속 팀 논의 기록](02_meeting_records/instructor_topic_feedback_2026-08-26.md)
11. [데이터 확보 가능성 검증서](04_data_validation/data_feasibility_check.md)

### 후속 설계 참고

- [저장소 루트 README와 현재 팀 구성](../../README.md)
- [Track B 역할 및 업무 범위](../track_b/01_role_and_scope.md)
- [생성 컴포넌트 입출력 계약](../track_b/02_generation_contract.md)
- [Prompt Baseline 설계](../track_b/03_prompt_baseline.md)

## 2. 디렉터리 구분

| 디렉터리 | 기록 내용 | 현재 성격 |
|---|---|---|
| `01_initial_review` | 1차 회의, 후보 비교, 2차 회의 전 개인 구체화안 | 과거 기록·팀 합의 전 검토 |
| `02_meeting_records` | 팀원이 실제로 제시한 의견과 회의 결과 | 회의 사실 기록 |
| `03_post_meeting_reviews` | 2차 회의 결과에 따른 후보별 후속 보완 | 당시 검토안·참고 기록 |
| `04_data_validation` | 공식 데이터·라이선스·검색 가능성 검증 | 실제 데이터 검증 전 작업 문서 |

## 3. 현재까지의 진행 흐름

```text
2026-08-25 1차 주제 선정
        ↓
2026-08-26 오전 개인 기획 및 회의 전 구체화
        ↓
2026-08-26 13:30 2차 회의 — 최종 주제 미확정
        ↓
방문·도슨트 결합안과 교육 주제 후속 보완
        ↓
2026-08-26 18:00 이후 강사님께 주제 의견 요청 및 팀 간략 논의
        ↓
(가칭) 개인 맞춤형 AI 문화유산 도슨트 방향으로 의견 수렴
        ↓
현장 도슨트에 한정하지 않는 AI 문화유산 지식 안내 서비스로 구체화
        ↓
작업 기준안 v0.1 채택 및 팀장·A~F 역할 분담
        ↓
Track B 역할·생성 계약·Prompt Baseline 정리
        ↓
실제 데이터 검증·Baseline RAG·평가 계획 구체화 예정
```

## 4. 문서 관리 원칙

- Markdown 파일을 내용 수정의 원본으로 사용합니다.
- HTML 파일은 팀 공유·발표·시각화용 생성 결과로 사용합니다.
- 회의록의 기존 발언과 과거 결론은 삭제하거나 현재 의견으로 덮어쓰지 않습니다.
- 회의 후 분석은 회의 당시 합의와 별도 문서로 구분합니다.
- 최종 주제가 결정되면 [프로젝트 정의서](../01_project_definition.md)와 [의사결정 기록](../decision_log.md)을 갱신합니다.

## 5. 현재 미확정 사항

- 최종 프로젝트·서비스명
- 핵심 사용자 정의의 최종 문구
- 한국민족문화대백과사전에서 실제 수집·가공할 수 있는 데이터 범위와 이용조건
- 서비스 MVP에 포함할 정확한 기능과 교육·추천 등 확장 기능의 경계
- Baseline 모델·생성 설정·API 비용 한도
- 검색·답변·안전장치 평가 지표와 목표값
- Prompt Baseline 비교 결과에 따른 Fine-tuning 최종 채택 여부

## 6. 다음 작업

1. 한국민족문화대백과사전의 실제 수집 방식·이용조건·메타데이터를 Document Card에 기록합니다.
2. 소규모 실제 문서 표본으로 정제·청킹·검색 가능성을 먼저 검증합니다.
3. Dense Retriever와 Prompt Baseline을 연결한 실행 가능한 기본 RAG 흐름을 만듭니다.
4. 검색·생성·출처·답변 보류·안전장치의 평가 질문과 기준을 정합니다.
5. Baseline 결과를 확인한 후 Fine-tuning 비교 실험의 데이터와 비용 범위를 확정합니다.
6. Streamlit에서 같은 입출력 계약을 사용해 실제 RAG 응답을 연결합니다.

위 절차는 작업 기준안이며, 데이터 검증과 팀 회의 결과에 따라 순서와 범위를 조정할 수 있습니다.
