# 생성 컴포넌트 입출력 계약 및 응답 스키마

> 작성일: 2026-08-28  
> 상태: 변경 검토 중 — 기존 승인안에 팀원 의견 반영  
> 스키마 버전: `0.2.0-draft`  
> 변경 사유: `candidate_answerable`·`candidate_refusal` 구조를 `candidate_response_type` 중심으로 확장하고 `needs_clarification` 대화 상태를 추가한다.  
> 전제: 실제 문서 표본 없이 설계한 작업용 초안이며, B·C·E·F와의 연동 검토 후 변경할 수 있다.

## 1. 문서 목적

이 문서는 C의 검색 결과, D의 생성 컴포넌트, E의 RAG Chain과 안전장치, F의 Streamlit 화면 사이에서 주고받을 데이터 형식을 정의한다.

D와 E가 RAG Chain 후보를 각자 구현하더라도 같은 입력과 출력 형태로 변환할 수 있게 하여 비교와 통합에 드는 시간을 줄이는 것이 목적이다.

## 2. 0.2.0-draft의 주요 변경

| 변경 항목 | 기존 0.1.0-draft | 변경 0.2.0-draft |
| :--- | :--- | :--- |
| 응답 상태 | `candidate_answerable` + `candidate_refusal.code` | `candidate_response_type` |
| 정상 답변 | `answerable=true` | `answered` |
| 근거 부족 | `insufficient_context` | `insufficient_evidence` |
| 모호한 질문 | 별도 상태 없음 | `needs_clarification` |
| 잘못된 전제 | 별도 상태 없음 | `corrected_premise` |
| 안전 거절 | `safety_restriction` | `safety_refusal` |
| 사용자 메시지 | `draft_answer` | `draft_message` |
| 대화 상태 | 대화 이력 제외 | 추가 질문 한 건을 위한 최소 상태만 추가 |
| 시스템 오류 | 일부 거절 코드와 혼재 | 의미적 응답과 분리 |

코드명은 팀 합의 전까지 작업용 이름으로 사용한다.

## 3. 설계 원칙

1. 생성 모델은 출처 제목과 URL을 기억에 의존해 새로 만들지 않는다.
2. 생성 모델은 답변에 사용한 `chunk_id`만 반환하고, 실제 출처 정보는 검색 문맥의 메타데이터에서 연결한다.
3. 사용자에게 보여줄 응답과 평가·재현을 위한 내부 실행 정보를 구분한다.
4. 검색 점수는 Vector DB에 따라 의미가 다를 수 있으므로 점수의 크기만으로 좋고 나쁨을 단정하지 않는다.
5. 실제 표본 전에는 `MOCK-` 접두사가 붙은 값만 사용한다.
6. 필드 변경 시 `schema_version`을 올리고 변경 이유를 기록한다.
7. D와 E가 서로 다른 내부 구조를 사용해도 아래 공통 계약으로 변환한 뒤 비교한다.
8. `needs_clarification`은 거절이 아니라 다음 사용자 입력을 기다리는 대화 상태로 취급한다.
9. 의미적 응답 상태와 API·파싱·네트워크 오류를 분리한다.

## 4. 전체 데이터 흐름

```text
C: Retriever
   │
   └─ list[RetrievedContext]
              │
              ▼
E 또는 D의 실험 Chain: GenerationRequest 구성
              │
              ▼
D: 질문 상태 판정 → Prompt → Model → Output Parser
              │
              └─ GenerationResult
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
    답변·거절·정정             추가 질문 필요
             │                       │
             ▼                       ▼
E: 근거·안전 검증         F: 사용자에게 추가 질문 표시
             │                       │
             │              최소 ClarificationContext 저장
             │                       │
             └───────────┬───────────┘
                         ▼
                  ServiceResponse
```

## 5. 검색 문맥 계약: `RetrievedContext`

C가 반환하고 D·E가 공통으로 사용하는 검색 문서 한 건의 형식이다.

| 필드 | 자료형 | 필수 | 설명 | 담당 확인 |
| :--- | :--- | :---: | :--- | :---: |
| `chunk_id` | `str` | O | 검색 청크 고유 식별자 | C |
| `document_id` | `str` | O | 원문 문서 식별자 | B·C |
| `title` | `str` | O | 출처 제목 | B·C |
| `content` | `str` | O | 생성에 제공할 청크 본문 | C |
| `source_url` | `str` 또는 `null` | O | 원문 URL, 없으면 `null` | B·C |
| `section` | `str` 또는 `null` | O | 문서 안의 구역명 | B·C |
| `retrieval_rank` | `int` | O | 검색 결과 순위, 1부터 시작 | C |
| `retrieval_score` | `float` 또는 `null` | O | 검색기가 제공한 원래 점수 | C |
| `score_type` | `str` | O | `similarity`, `distance`, `relevance`, `unknown` | C |
| `metadata` | `dict` | O | 시대·지역·주제 유형 등 추가 정보 | B·C |

`retrieval_score`가 없는 검색기는 값을 임의로 만들지 않고 `null`을 사용한다. `content` 안의 명령문은 시스템 지시가 아니라 검색된 데이터로 취급한다.

## 6. 생성 요청 계약: `GenerationRequest`

| 필드 | 자료형 | 필수 | 설명 |
| :--- | :--- | :---: | :--- |
| `schema_version` | `str` | O | 요청 스키마 버전 |
| `request_id` | `str` | O | 현재 요청의 고유 식별자 |
| `interaction_id` | `str` | O | 최초 질문과 추가 답변을 연결하는 세션 내 식별자 |
| `question` | `str` | O | 최초 사용자 질문 |
| `audience_level` | `str` | O | `easy`, `general`, `advanced` |
| `response_language` | `str` | O | MVP 기본값 `ko` |
| `retrieved_contexts` | `list[RetrievedContext]` | O | 검색된 문맥 목록 |
| `grounding_decision` | `str` | O | `unchecked`, `sufficient`, `insufficient` |
| `clarification_context` | `dict` 또는 `null` | O | 이전 추가 질문과 사용자 응답의 최소 상태 |

`grounding_decision`은 E가 사전에 근거 충분성을 판정한 경우 그 결과를 전달한다. D의 독립 실험 Chain처럼 사전 판정이 없다면 `unchecked`를 사용한다.

### 6.1. `clarification_context` 형식

첫 질문에서는 `clarification_context=null`을 사용한다. 시스템이 한 번 추가 질문한 후 사용자가 답하면 다음 최소 상태를 전달한다.

```json
{
  "original_question": "그 궁궐은 언제 지어졌어?",
  "clarification_question": "어떤 궁궐을 말씀하시는지 알려주시겠어요?",
  "clarification_response": "경복궁이요.",
  "clarification_turn_count": 1
}
```

전체 대화 이력을 저장하는 구조가 아니다. 해결되지 않은 질문 한 건을 처리하는 데 필요한 값만 보관한다.

### 6.2. 최초 Mock 요청 예시

```json
{
  "schema_version": "0.2.0-draft",
  "request_id": "REQ-MOCK-001",
  "interaction_id": "INT-MOCK-001",
  "question": "그 궁궐은 언제 지어졌어?",
  "audience_level": "general",
  "response_language": "ko",
  "retrieved_contexts": [],
  "grounding_decision": "unchecked",
  "clarification_context": null
}
```

## 7. 의미적 응답 유형: `response_type`

| 값 | 의미 | 사용자에게 필요한 행동 |
| :--- | :--- | :--- |
| `answered` | 근거가 충분한 정상 답변 | 답변과 출처 표시 |
| `insufficient_evidence` | 질문은 명확하지만 현재 근거가 부족 | 근거 부족 안내 |
| `needs_clarification` | 두 개 이상의 해석이 가능하여 추가 정보 필요 | 추가 질문 한 건 표시 |
| `corrected_premise` | 잘못된 전제를 근거로 정정하며 답변 | 정정 내용과 출처 표시 |
| `safety_refusal` | 인젝션·비밀 요청 등 안전상 거절 | 안전 안내 |
| `out_of_scope` | 서비스 범위 밖 질문 | 서비스 범위 안내 |

`invalid_request`, `generation_error`, `upstream_error`는 질문 의미에 대한 응답 유형이 아니라 애플리케이션 오류 코드로 별도 관리한다.

## 8. 생성 결과 계약: `GenerationResult`

D의 생성 컴포넌트가 E에게 반환하는 내부 결과다. 아직 최종 사용자 응답은 아니다.

| 필드 | 자료형 | 필수 | 설명 |
| :--- | :--- | :---: | :--- |
| `schema_version` | `str` | O | 결과 스키마 버전 |
| `request_id` | `str` | O | 입력과 동일한 요청 식별자 |
| `interaction_id` | `str` | O | 대화 연결 식별자 |
| `candidate_response_type` | `str` | O | 생성 단계의 잠정 응답 유형 |
| `draft_message` | `str` | O | 답변, 정정, 거절 안내 또는 추가 질문 |
| `audience_level` | `str` | O | 실제 적용된 설명 수준 |
| `used_chunk_ids` | `list[str]` | O | 메시지 작성에 실제 사용한 청크 ID |
| `clarification` | `dict` 또는 `null` | O | 추가 질문 정보 |
| `premise_correction` | `dict` 또는 `null` | O | 잘못된 전제와 정정 내용 |
| `related_topic_candidates` | `list[dict]` | O | 근거와 연결된 연관 항목 후보 |
| `generation_metadata` | `dict` | O | Prompt·모델·생성 설정 추적 정보 |

### 8.1. `clarification` 형식

```json
{
  "reason_code": "missing_reference",
  "question": "어떤 궁궐을 말씀하시는지 알려주시겠어요?",
  "options": []
}
```

권장 `reason_code` 후보는 다음과 같다.

- `missing_reference`: “그 사람”, “그 장소”처럼 지시 대상이 없음
- `ambiguous_entity`: 같은 이름 또는 여러 대상 후보가 있음
- `ambiguous_scope`: 원하는 설명 범위가 불명확함
- `ambiguous_relation`: 어떤 관계를 묻는지 불명확함
- `ambiguous_time`: 기준 시점이 필요함

선택지가 있으면 최대 3개까지만 제시한다.

```json
{
  "id": "option-1",
  "label": "서울 선릉과 정릉",
  "source_chunk_ids": ["CHUNK-MOCK-001"]
}
```

선택지는 사용자 질문, 저장된 최소 대화 상태 또는 검색 문맥에서 확인된 후보만 사용한다. 검색 근거에서 가져온 선택지는 `source_chunk_ids`를 기록한다.

### 8.2. `premise_correction` 형식

```json
{
  "original_premise": "질문에 포함된 잘못된 전제",
  "corrected_premise": "검색 근거로 확인한 정정 내용",
  "source_chunk_ids": ["CHUNK-MOCK-001"]
}
```

### 8.3. `generation_metadata` 형식

```json
{
  "prompt_version": "prompt-baseline-v0",
  "model_id": "TBD",
  "temperature": null,
  "finish_reason": null,
  "latency_ms": null,
  "token_usage": null
}
```

실행하지 않은 값은 임의로 채우지 않고 `null`로 둔다. 이 정보는 모델이 생성하지 않고 실행 코드가 실제 값으로 조립한다.

## 9. 서비스 응답 계약: `ServiceResponse`

E가 검증을 마치고 F에게 전달하는 최종 응답이다. `citations`는 LLM이 생성한 문자열이 아니라 `used_chunk_ids`와 원본 검색 메타데이터를 연결하여 만든다.

| 필드 | 자료형 | 필수 | 설명 |
| :--- | :--- | :---: | :--- |
| `schema_version` | `str` | O | 서비스 응답 버전 |
| `request_id` | `str` | O | 요청 식별자 |
| `interaction_id` | `str` | O | 대화 연결 식별자 |
| `response_type` | `str` | O | 검증을 통과한 최종 응답 유형 |
| `message` | `str` | O | 사용자에게 표시할 메시지 |
| `audience_level` | `str` | O | 적용된 설명 수준 |
| `citations` | `list[dict]` | O | 원본 메타데이터에서 구성한 출처 |
| `clarification` | `dict` 또는 `null` | O | 사용자에게 요청할 추가 정보 |
| `premise_correction` | `dict` 또는 `null` | O | 정정된 전제 정보 |
| `related_topics` | `list[dict]` | O | 검증된 연관 항목 |
| `warnings` | `list[str]` | O | UI에 알릴 제한 또는 주의사항 |

### 9.1. `citations` 형식

```json
{
  "chunk_id": "CHUNK-MOCK-001",
  "document_id": "DOC-MOCK-001",
  "title": "가상 문서",
  "section": "개요",
  "source_url": null
}
```

## 10. 모호함 판단 기준

다음 조건을 모두 만족할 때만 `needs_clarification`으로 판단한다.

1. 두 개 이상의 합리적인 해석이 가능하다.
2. 해석에 따라 검색 결과나 최종 답변이 크게 달라진다.
3. 현재 질문·최소 대화 상태·검색 결과로 하나를 선택할 근거가 없다.
4. 사용자에게 한 번 질문하면 모호함을 해결할 수 있다.

다음 상황은 `needs_clarification`으로 처리하지 않는다.

- 질문은 명확하지만 문서 근거가 없음 → `insufficient_evidence`
- 잘못된 전제를 문서 근거로 정정할 수 있음 → `corrected_premise`
- 서비스 범위 밖 질문 → `out_of_scope`
- 안전상 답변할 수 없는 질문 → `safety_refusal`
- 하나의 해석이 명확하고 기본 범위로 답변 가능 → `answered`

검색 점수 하나 또는 LLM이 생성한 자신감 점수만으로 모호함을 판정하지 않는다.

## 11. 추가 질문 정책

- 추가 질문은 한 번에 하나만 작성한다.
- 질문에 이미 포함된 정보를 다시 묻지 않는다.
- 선택지는 명확할 때만 최대 3개까지 제공한다.
- 검색 결과에서 확인되지 않은 선택지를 기억으로 만들지 않는다.
- `clarification_turn_count`의 기본 상한은 1회로 둔다.
- 한 번 확인한 뒤에도 모호하면 자동으로 계속 질문하지 않고, 질문을 완전한 문장으로 다시 작성해 달라고 안내한 후 대기 상태를 종료한다.
- MVP에서는 전체 대화 기록 대신 `ClarificationContext` 한 건만 보관한다.

## 12. 응답 유형 판정 순서

```text
안전 위반
→ safety_refusal

서비스 범위 밖
→ out_of_scope

잘못된 전제를 검색 근거로 정정 가능
→ corrected_premise

두 개 이상의 해석이 가능하고 하나를 선택할 근거가 없음
→ needs_clarification

질문은 명확하지만 근거 부족
→ insufficient_evidence

정상 답변 가능
→ answered
```

실제 Chain에서는 일부 판정이 검색 전과 검색 후에 나뉠 수 있다. 이 순서는 최종 응답 유형이 서로 겹칠 때의 우선순위 기준이다.

## 13. 필수 검증 규칙

### 공통 규칙

1. 요청과 결과의 `request_id`, `interaction_id`가 같아야 한다.
2. `candidate_response_type`과 `response_type`은 승인된 여섯 값 중 하나여야 한다.
3. `audience_level`은 `easy`, `general`, `advanced` 중 하나여야 한다.
4. `used_chunk_ids`는 입력의 `retrieved_contexts`에 존재하는 값만 사용할 수 있다.
5. 출처 제목·URL·구역은 검색 메타데이터에서 복사하고 LLM 출력에서 가져오지 않는다.
6. 스키마에 없는 필드는 구현 단계에서 기본적으로 거부하고, 필요한 경우 버전을 변경한다.

### 응답 유형별 규칙

| 응답 유형 | 필수 조건 |
| :--- | :--- |
| `answered` | `used_chunk_ids` 1개 이상, `clarification=null`, `premise_correction=null` |
| `insufficient_evidence` | 질문은 명확해야 하며, `clarification=null`, `premise_correction=null` |
| `needs_clarification` | `clarification.question` 필수, 질문 1개, 선택지 최대 3개 |
| `corrected_premise` | `premise_correction` 필수, 근거 `source_chunk_ids` 1개 이상 |
| `safety_refusal` | `clarification=null`, `premise_correction=null`, 비밀 값을 메시지에 포함하지 않음 |
| `out_of_scope` | `clarification=null`, `premise_correction=null` |

`related_topics`는 `answered` 또는 `corrected_premise`일 때만 제공하는 것을 기본안으로 한다.

## 14. 시스템 오류와 의미적 응답의 구분

| 상황 | 분류 | 처리 |
| :--- | :--- | :--- |
| 근거 부족 | `insufficient_evidence` | 정상적인 의미적 응답 |
| 모호한 질문 | `needs_clarification` | 정상적인 대화 상태 |
| 안전상 거절 | `safety_refusal` | 정상적인 안전 동작 |
| 비어 있거나 파싱할 수 없는 입력 | `invalid_request` | 입력 검증 오류 |
| 구조화 출력 파싱 실패 | `generation_error` | 생성·파서 오류 |
| API·네트워크 장애 | `upstream_error` | 외부 호출 오류 |

시스템 오류는 정상 거절률이나 답변 보류 정확도에 포함하지 않는다.

## 15. Mock 응답 예시

### 15.1. 추가 질문 필요

```json
{
  "schema_version": "0.2.0-draft",
  "request_id": "REQ-MOCK-001",
  "interaction_id": "INT-MOCK-001",
  "candidate_response_type": "needs_clarification",
  "draft_message": "어떤 궁궐을 말씀하시는지 알려주시겠어요?",
  "audience_level": "general",
  "used_chunk_ids": [],
  "clarification": {
    "reason_code": "missing_reference",
    "question": "어떤 궁궐을 말씀하시는지 알려주시겠어요?",
    "options": []
  },
  "premise_correction": null,
  "related_topic_candidates": [],
  "generation_metadata": {
    "prompt_version": "prompt-baseline-v0",
    "model_id": null,
    "temperature": null,
    "finish_reason": null,
    "latency_ms": null,
    "token_usage": null
  }
}
```

### 15.2. 잘못된 전제 정정

```json
{
  "schema_version": "0.2.0-draft",
  "request_id": "REQ-MOCK-002",
  "interaction_id": "INT-MOCK-002",
  "candidate_response_type": "corrected_premise",
  "draft_message": "질문의 전제를 검색 근거에 따라 바로잡아 설명합니다.",
  "audience_level": "general",
  "used_chunk_ids": ["CHUNK-MOCK-001"],
  "clarification": null,
  "premise_correction": {
    "original_premise": "질문에 포함된 잘못된 전제",
    "corrected_premise": "검색 근거로 확인한 정정 내용",
    "source_chunk_ids": ["CHUNK-MOCK-001"]
  },
  "related_topic_candidates": [],
  "generation_metadata": {
    "prompt_version": "prompt-baseline-v0",
    "model_id": null,
    "temperature": null,
    "finish_reason": null,
    "latency_ms": null,
    "token_usage": null
  }
}
```

## 16. 팀원 협업 및 논의 필요 항목

| 번호 | 논의 항목 | 제안 | 협업 대상 | 확정 필요 시점 |
| :---: | :--- | :--- | :---: | :--- |
| S-01 | 검색 문맥 필드 | `chunk_id`, `document_id`, `content`, 출처 메타데이터를 공통 필수값으로 사용 | B·C | 실제 표본 연결 전 |
| S-02 | 검색 점수 표현 | 점수와 함께 `score_type`을 전달하고 임계값은 C·E가 결정 | C·E | 검색기 연결 전 |
| S-03 | 근거 판정 전달 | 사전 판정이 있으면 `sufficient/insufficient`, 없으면 `unchecked` | D·E | RAG 후보 비교 전 |
| S-04 | 설명 수준 | 내부 코드는 `easy/general/advanced`, UI 문구는 `쉽게/일반/깊이 있게` | D·F·팀 | UI·Prompt 확정 전 |
| S-05 | 출처 구성 | D는 `used_chunk_ids`만 반환하고 E가 출처 메타데이터를 연결 | C·D·E | 통합 구현 전 |
| S-06 | 서비스 응답 필드 | F가 필요한 필드와 표시하지 않을 내부 필드를 구분 | E·F | UI 실제 연결 전 |
| S-07 | 연관 항목 | MVP 포함 여부와 표시 형태를 팀에서 결정 | A·D·E·F | 생성 코드 구현 전 |
| S-08 | 오류 책임 | 생성·파싱 오류는 D, Chain·외부 호출 오류는 E가 우선 기록 | D·E | 통합 테스트 전 |
| S-09 | 응답 유형 코드명 | 여섯 개 `response_type` 이름과 의미 확정 | D·E·F·팀 | Prompt·UI 확정 전 |
| S-10 | 추가 질문 상태 | `interaction_id`와 최소 `ClarificationContext` 저장 위치 결정 | A·D·E·F | 생성 코드 구현 전 |
| S-11 | 모호함 판정 | 네 가지 판정 조건과 추가 질문 1회 제한 검토 | D·E·팀 | Prompt·평가 확정 전 |
| S-12 | 잘못된 전제 정정 | `corrected_premise`의 UI 표시와 평가 방법 결정 | D·E·F | UI·평가 확정 전 |

팀원 협의 전에도 이 문서를 `0.2.0-draft` 작업 계약으로 사용해 각자 후보를 만들 수 있다. 다만 실제 통합이나 성능 비교 전에 관련 항목을 확인하고, 합의 결과가 달라지면 스키마 버전을 변경한다.

## 17. 이번 변경의 승인 항목

- `candidate_answerable`·`candidate_refusal` 대신 `candidate_response_type`을 사용하는 구조
- 여섯 가지 의미적 응답 유형
- `draft_answer`를 범용 `draft_message`로 변경
- `needs_clarification`의 모호함 판정 네 조건
- 추가 질문 한 건과 최대 세 개 선택지
- 추가 질문 횟수 1회 제한
- 전체 대화 이력 대신 최소 `ClarificationContext`만 저장
- `corrected_premise`의 정정 내용과 근거 연결
- 의미적 응답과 시스템 오류의 분리
- 실제 코드 구현 전 S-09~S-12를 팀과 확인하는 원칙

이 변경안이 재승인되기 전에는 3단계 Prompt Baseline을 수정하지 않는다.

