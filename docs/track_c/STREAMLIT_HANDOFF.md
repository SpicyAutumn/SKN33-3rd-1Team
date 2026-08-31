# Track C Streamlit 인계 — 문화유산 맞춤형 답변 서비스

최종 갱신: 2026-08-31. 브랜치 `feature/track-c-audience-level` (PR #13, Draft) 기준으로 다시 작성했다.
이 문서는 팀 공통 API 계약을 바꾸거나 담당자를 확정하는 문서가 아니다.

## 0. 지난 인계 이후 달라진 것

이전 판은 **모든 것이 Mock인 상태**를 인계했다. 지금은 검색까지 실제로 연결돼 있다.

| | 이전 | 지금 |
| :--- | :--- | :--- |
| 검색 | 없음 (고정 응답) | **실제 Pinecone 검색** (v1, 179,028 청크) |
| 파이프라인 | UI가 직접 조립 | **`RagService.answer_with_trace()` 호출** |
| 설명 수준 | UI 없음 | 선택 + 답변 후 전환 |
| 평가 탭 | 고정 RAGAS 점수 | **검색 품질 실측** + RAGAS는 미연결 명시 |
| 탐험 지도 | 키워드 사전 하드코딩 | **검색 결과 메타데이터로 구성** |
| TTS | `</script>` 탈출 가능 | 이스케이프 + `st.iframe` |
| 탭 | 4개 | 5개 (`공정 견학` 추가) |
| 테스트 | 없음 | 24개 (전체 82개 통과) |

**여전히 없는 것: 답변 문장 생성.** 아래 3절을 반드시 읽을 것.

## 1. 무엇이 진짜이고 무엇이 임시인가

이걸 구분하지 못하면 "다 됐다"고 잘못 보고하게 된다.

**실제로 동작하는 것**

- 질문 → OpenAI 임베딩 → Pinecone 검색 → 근거 반환
- 출처 표시, 근거 문장, 원문 링크 (모두 실제 백과사전 데이터)
- 같은 문서 청크 묶기
- 설명 수준 선택과 전달 (`audience_level`)
- 평가 탭의 검색 품질 지표
- 탐험 지도의 연결 관계 (분야·시대·유형·지역·이칭)
- 공정 견학의 6단계와 원문 역추적

**임시로 채워 둔 것 — 실제 구현이 오면 지운다**

```python
# app/rag_client.py
EvidencePassthroughGenerator   # 답변 문장을 만들지 않고 검색 원문만 전달
ScoreEvidenceChecker           # 유사도 기준선(0.40)만 보는 근거 판정
```

두 클래스 모두 `[제거 예정]` 주석이 달려 있다. 왜 필요한지는 3절에 있다.

**아직 없는 것**

- 답변 문장 생성 (생성 담당 작업 대기)
- RAGAS 점수, LLM 심사 (평가 담당 작업 대기)
- `related_topics` (계약상 기본 비활성)
- 탐험 지도 노드 클릭 시 재검색

## 2. 파일 구성

```text
app/
  app.py                    실행·테마 적용·머리말·5개 탭 배치
  theme.py                  전체 시각 스타일 (CSS)
  rag_client.py             RagService 조립 + 임시 구현체        ← 교체 지점
  retrieval.py              화면과 서비스 사이 얇은 연결 계층
  regions.py                제목·본문에서 지역 추출
  mock_responses.py         키 없을 때 쓰는 예시 응답
  tabs/
    chat.py                 질문 제출·설명 수준·last_result
    process.py              검색 청크 표시 (팀원 작성, 손대지 않음)
    pipeline.py             공정 견학 — 원문에서 답변까지의 과정
    evaluation.py           검색 품질 실측 + RAGAS 미연결 표시
    explore.py              탐험 지도 데이터 구성
    guide.py                미사용
  components/
    citations.py            출처 카드·근거 문장
    response_cards.py       응답 유형별 화면·TTS
    exploration_map.html    클릭 확장 지도 (팀원 작성, 손대지 않음)
tests/
  test_app_track_c.py       Track C 단위 테스트 24개
```

**손대지 않은 팀원 파일**: `process.py`, `exploration_map.html`. 화면 구조와 표시 형식은 그대로 두고 데이터만 실제 값으로 바꿨다.

## 3. 왜 임시 구현이 필요한가 — 지우기 전에 읽을 것

`RagService`를 그냥 쓰면 **모든 질문이 보류로 나온다.** 두 가지 이유다.

```python
# src/rag_service/service.py
def __init__(self, *, retriever, generator: GenerationComponent, ...)
                                 # ↑ 필수 인자인데 구현체가 없다

def _decide_grounding(self, question, contexts):
    ...
    if self.evidence_checker is None:
        return "insufficient"    # ↑ 없으면 무조건 보류
```

그래서 Track C가 계약 인터페이스를 따르는 최소 구현을 넣어 뒀다.
**실제 구현이 오면 `build_service()`의 인자 두 개만 바꾸면 된다.**

```python
# app/rag_client.py
return RagService(
    retriever=PineconeRetriever(),
    generator=EvidencePassthroughGenerator(),   # ← 여기
    evidence_checker=ScoreEvidenceChecker(),    # ← 여기
)
```

`EvidencePassthroughGenerator`의 유일한 규칙은 **근거 밖 문장을 지어내지 않는 것**이다. 검색된 원문만 그대로 넘긴다. 이 규칙을 깨는 방향으로 고치지 말 것.

## 4. 탭 간 상태 공유

`RagService.answer_with_trace()`의 반환 구조를 그대로 세션에 싣는다.

```python
last_result = {
    "question": str,
    "audience_level": "easy" | "general" | "advanced",
    "response": ServiceResponse,        # 계약 9장. retrieved_contexts 없음에 주의
    "retrieved_contexts": [...],        # 실행 추적. 검색 결과 전체
    "used_chunk_ids": [...],            # 근거로 쓰인 청크
    "retrieval_top_k": int,
    "related_keywords": [...],          # response["related_topics"]
}
```

**주의**: `ServiceResponse`에는 `retrieved_contexts`가 없다. 검색 결과가 필요하면 반드시 `execution["retrieved_contexts"]`에서 읽어야 한다. 이걸 `response`에서 찾다가 질문 기록이 항상 비는 버그가 있었다.

- `question_history`: 최근 10건의 질문·제목.
- `clarification_context`, `interaction_id`: 추가 질문 선택 시 담기고 다음 요청에 전달된다.
- 지도에서 펼친 상태는 iframe JavaScript 안에만 있다. 탭 전환·재실행 시 유지되지 않는다.
- `session_state`는 영구 저장이 아니다. 새 세션·재접속에는 사라진다.
- `st.cache_data`를 사용자별 질문 보관함으로 쓰지 않는다. 공유 캐시에 개인정보가 섞이면 안 된다.

## 5. 기준선 판정은 한 곳만 쓴다

`app/rag_client.py`의 `meets_threshold()` 하나만 쓴다. 화면·근거 판정·근거 선택이 어긋나면 안 된다.

```python
def meets_threshold(context, min_score=TEMP_EVIDENCE_MIN_SCORE) -> bool:
    score = _score(context)
    return score is None or score >= min_score
```

- 점수 없음(`None`)은 판단 불가로 보고 **통과**시킨다. 점수를 주지 않는 검색기도 있다.
- `0.0`은 실제 점수다. `or` 연산으로 처리하면 falsy로 걸려 통과해 버린다. 반드시 `is None`으로 구분한다.

이 함수를 쓰는 곳: `ScoreEvidenceChecker`, `EvidencePassthroughGenerator`, `evaluation.py`, `pipeline.py`.

## 6. 역할 경계

- **UI / Track C**: 화면, 상태 공유, 설명 수준 선택과 전달, 응답 연결, 통합 확인.
- **생성 · Prompt · Fine-tuning 담당**: 설명 수준을 실제 답변에 적용, 답변 문장 생성.
- **RAG Chain · 통합 평가 담당**: 근거 충분성 판정, 재검색, `used_chunk_ids` 검증, Citation 조립.
- **데이터 수집 · 전처리 · 검색 담당**: 수집·정제·청킹·임베딩·적재, `RetrievedContext` 반환까지.

근거 표시를 위해 같은 청크를 Pinecone에서 다시 조회하지 않는다. Citation의 `content`는 같은 요청의 검색 결과에서 온다.

### Pinecone 주의

v1 전체 179,028개 청크가 `aks-rag-v1`, 기본 namespace에 적재돼 있다. 모델은 `text-embedding-3-small`, 1,536차원, cosine.

**UI 작업을 이유로 전체 재적재, namespace 삭제, 임베딩 재생성, 플랜 변경을 수행하지 않는다.** 키 값은 문서·코드·PR에 넣지 않는다.

## 7. 알려진 한계 — PR에서 숨기지 말 것

1. **설명 수준을 바꿔도 답변 문장은 그대로다.** 화면과 데이터 흐름만 준비돼 있고, 말투를 실제로 바꾸는 것은 생성 담당 몫이다.
2. **검색이 대표 질문에서 틀린다.** `경복궁에 대해 알려줘` → 1위 `금관조복`(0.411), 정답 `경복궁`(0.388)은 기준선 미달로 탈락. 점수 기준선은 순위 실패를 고치지 못한다. 검색 담당 후속 작업이다.
3. **같은 문서가 top_k를 잠식한다.** 석굴암·훈민정음 모두 5건 중 3건이 동일 문서였다. 화면 묶기는 반영했으나 검색 단계 제한은 RAG Chain 후속 작업이다.
4. **RAGAS 네 지표는 미연결이다.** 점수를 지우고 설명만 남겨 뒀다. 값을 지어내 채우지 말 것.
5. **탐험 지도는 노드를 눌러도 재검색하지 않는다.** `exploration_map.html`이 데이터를 한 번에 받는 구조다. 하려면 그 파일을 고쳐야 한다.
6. **지역 판별은 유적·건물 7,951건 중 2,841건(35.7%)이다.** 제목 앞머리와 본문 주소만 본다. 좌표 기반 실제 지도는 위경도가 없어 3차 범위 밖이다.
7. **`Citation`에 유사도가 없다.** 계약에 없어서 출처 카드에 표시하지 않는다. 점수는 평가 결과·공정 견학 탭에서 본다. 나중에 붙인다면 순위가 아니라 `chunk_id`로 `RetrievedContext`를 찾아 연결할 것.
8. **TTS는 브라우저 음성 합성에 의존한다.** OS 한국어 음성과 브라우저 정책에 영향을 받는다. 정지·속도·음성 선택 기능은 없다.

## 8. 실행과 확인

**키가 없어도 화면은 뜬다.** `.env`가 없으면 Mock 모드로, 있으면 실제 검색으로 자동 전환된다.

```bash
git fetch origin
git switch feature/track-c-audience-level

python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python run.py
```

macOS/Linux는 `source .venv/bin/activate`를 쓴다.

실제 검색까지 보려면 저장소 루트에 `.env`를 만든다.

```ini
OPENAI_API_KEY=본인_키
PINECONE_API_KEY=팀_공용_키
PINECONE_INDEX_NAME=aks-rag-v1
```

> `PINECONE_API_KEY`는 **v1 인덱스가 있는 팀 계정 키**여야 한다. 개인 키를 넣으면 빈 인덱스를 보게 되어 모든 질문이 보류로 나온다. 에러가 나지 않아 원인을 찾기 어렵다.

화면 위쪽 배지로 모드를 확인한다. `🔧 Mock 응답 모드` / `✅ 실제 검색 연결됨`.

**확인용 질문**

| 질문 | 무엇을 보는지 |
| :--- | :--- |
| `경주 불국사에 대해 알려줘` | 근거 3건, 공정 견학, 탐험 지도가 모두 채워진다 |
| `석굴암 본존불의 특징은?` | 같은 문서 3청크가 출처 1건으로 묶인다 |
| `아이폰 최신 모델 가격 알려줘` | 보류. 공정 견학에서 왜 보류했는지 보인다 |
| `경복궁에 대해 알려줘` | **검색이 실패하는 사례.** 7절 2번 항목 |

**테스트**

```bash
python -m pytest -q
python -m pytest tests/test_app_track_c.py -q
```

Streamlit은 하위 모듈(`app/tabs/*.py`) 변경을 자동 반영하지 못한다. **화면이 안 바뀌면 서버를 재시작한다.**

## 9. 주의할 함정

- **`st.html`에 넣는 CSS에 날 HTML 태그를 쓰면 안 된다.** `<svg>`를 그대로 넣었더니 정화 과정에서 스타일시트 전체가 제거돼 폰트·탭·카드가 모두 무너졌다. SVG는 퍼센트 인코딩(`%3Csvg...`)해서 넣는다.
- **`st.iframe`은 `height=0`을 거부한다.** 소리만 내는 용도라도 `height=1`을 쓴다.
- **배경색·글자색을 직접 지정하지 않는다.** Streamlit 테마 값을 그대로 쓰고 강조색과 반투명 층만 얹는다. 직접 지정하면 밝은 화면과 어두운 화면 중 한쪽에서 글씨가 묻힌다.
- **`.streamlit/config.toml`은 실행 위치가 저장소 루트일 때만 읽힌다.** `python run.py`로 실행하면 정상 적용된다.

## 10. 권장 진행 순서

**지금 바로 할 수 있는 것**

1. `top_k` 슬라이더 — 평가 화면에 기본 3 / 비교 5. 공식 평가 때는 고정. (팀 합의됨)
2. 발표 시연 시나리오 — 8절 질문 4개로 전 기능을 보여주는 흐름 정리
3. 공정 견학 탭 다듬기

**생성 구현이 오면**

4. `build_service()`의 인자 두 개 교체 (3절)
5. `EvidencePassthroughGenerator`·`ScoreEvidenceChecker`·`TEMP_EVIDENCE_MIN_SCORE` 제거
6. 설명 수준이 실제로 답변을 바꾸는지 확인
7. 평가 탭의 RAGAS 지표에 실측값 연결

**하지 말 것**

- 근거 없이 답변 문장을 만들어 채우는 것
- 평가 점수를 임의 값으로 채우는 것
- `process.py`·`exploration_map.html`을 크게 뜯어고치는 것 (팀원 작성 영역)
- 계약에 없는 필드를 화면 마음대로 추가하는 것

## 11. 관련 문서

- `docs/track_b/02_generation_contract.md` — 응답 계약 0.3.0-draft. **가장 먼저 읽을 것**
- `docs/retrieved_context_contract.md` — 검색 반환 형식
- `docs/track_b/04_generation_evaluation_criteria.md` — 평가 기준
- `docs/document-card.md` — 데이터 출처와 이용조건
- PR #13 — 이 작업의 리뷰 이력. 왜 이렇게 했는지가 코멘트에 남아 있다
