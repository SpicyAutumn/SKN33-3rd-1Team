# 테스트 계획 및 결과 보고서

> 문서 기준일: 2026-09-03
>
> 프로젝트: `개인 맞춤형 AI 문화유산 가이드`
>
> 최신 검증 기준: GitHub `main` commit `f38ac054990f412c1ec37a88b2ca6c3250f29c90`

## 1. 요약

이 프로젝트는 한국민족문화대백과사전 원문을 검색하고, 검색 근거 안에서 설명 수준별 답변과 출처를 제공하는 RAG 서비스다. 데이터·검색·계약·UI를 단계별로 검증하고, 실제로 측정하지 않은 생성 품질이나 비용 수치는 결과로 기록하지 않았다.

| 평가 영역 | 핵심 결과 | 판정 |
| :--- | :--- | :---: |
| 원본 데이터 | 75,835건 검사, 정상 75,820건, 본문 누락 15건, 오류·중복 0건 | PASS |
| 전체 청크 | 75,820문서, 179,028청크, 누락·중복·필드 오류 0건 | PASS |
| 자동 테스트 | Python 3.12.14에서 184개와 subtest 53개 통과 | PASS |
| 일반 검색 25문항 | Hybrid Hit@3 `0.92`, MRR `0.820` | 채택 |
| 고유명사 회귀 5문항 | Hybrid Hit@1·Hit@3 `1.00` | PASS |
| 생성 품질 전체 집계 | 수준별 생성·계약·RAGAS 기능은 구현, 공식 전체 평균은 미측정 | 제한사항 |
| Fine-tuning | 동일 조건의 전후 비교를 수행하지 않음 | 후속 과제 |
| LangGraph | 개선 가능성을 확인했으나 지연시간과 통합 일정 때문에 최종 경로에서 제외 | 후속 과제 |

## 2. 테스트 목적과 원칙

### 2.1 목적

- 수집 원본과 검색 청크가 누락·중복 없이 연결되는지 확인한다.
- Dense, BM25, Hybrid 중 현재 질문 세트에서 더 적절한 검색 방식을 찾는다.
- 검색 결과와 생성 결과의 실패 원인을 구분한다.
- LLM이 검색하지 않은 청크나 출처를 만들어 내지 못하게 계약을 검증한다.
- 근거 부족·모호한 질문·위험한 요청·범위 밖 질문을 구분해 처리한다.
- 개선 기법은 같은 질문과 조건으로 비교하며 한 번에 하나의 요소만 바꾼다.

### 2.2 결과 기록 원칙

- `PASS`: 실제 검증 결과와 재현 근거가 있는 항목
- `PARTIAL`: 기능 또는 기준은 있으나 공식 전체 평가가 끝나지 않은 항목
- `NOT RUN`: 이번 프로젝트에서 실행하지 않은 항목
- `REFERENCE`: 조건 일부가 저장소에 없어서 참고용으로만 사용하는 결과

Mock 화면, 단위 테스트의 가짜 응답과 실제 API 실행 결과를 같은 결과로 합치지 않는다.

## 3. 테스트 환경

| 항목 | 값 |
| :--- | :--- |
| 자동 테스트 실행일 | 2026-09-03 |
| 자동 테스트 commit | `f38ac054990f412c1ec37a88b2ca6c3250f29c90` |
| CI 환경 | GitHub Actions, Ubuntu 24.04.4, Python 3.12.14 |
| 원본 데이터 | AKS 상세 API JSON 75,835건 |
| 검색 corpus | 75,820문서, 179,028청크 |
| 청킹 기준 | 최대 1,500자, overlap 200자, definition·body 분리 |
| Embedding | `text-embedding-3-small`, 1,536차원, cosine |
| Vector DB | Pinecone `aks-rag-v1`, `__default__` namespace |
| BM25 | SQLite FTS5, 제목·별칭·본문 색인 |
| Hybrid | 후보 10/10, RRF `k=60`, 가중치 1.5/1.0 |
| 최종 검색 결과 | `top_k=3`, 문서당 최대 2청크, RRF threshold 없음 |
| 생성 | RunPod Ollama, `exaone3.5:7.8b-instruct-q8_0` |
| 생성 설정 | temperature `0.0`, `think=false`, JSON Schema |
| Prompt | `response-type-v1-ollama` (`prompt-baseline-v0` 기반) |

자동 테스트는 외부 API를 실제 호출하는 성능 시험이 아니라, Mock과 test double을 사용한 코드·계약 회귀 검사다. 실제 검색 성능은 별도의 Dense·BM25·Hybrid 평가 실행 결과를 사용한다.

## 4. 평가 데이터

| 평가 세트 | 문항 수 | 구성 | 검토 상태 | 사용 목적 |
| :--- | ---: | :--- | :--- | :--- |
| RAG Dev v1 | 48 | answered 20, insufficient 8, clarification 5, corrected 5, safety 5, out-of-scope 5 | approved 40, draft 8 | 반복 개발·응답 유형 평가 |
| 검색 평가 대상 | 25 | Dev의 answered 20 + corrected 5 | Dev 상태를 따름 | Dense·BM25·Hybrid 공식 비교 |
| Holdout v1 | 12 | 여섯 응답 유형 각 2건 | draft 12 | 최종 후보의 마지막 검증 |
| 고유명사 회귀 v1 | 5 | 경복궁·석굴암·종묘·향원정·백제금동대향로 | draft 5 | 정확한 표제어 검색 회귀 |
| 초기 Retrieval v1 | 20 | 서로 다른 분야 각 1건 | 별도 review 필드 없음 | 초기 Dense 기준 확인 |

`draft` 문항은 평가 재료로 사용할 수 있지만 사람 검수가 끝난 공식 Holdout으로 보지는 않는다. Holdout 결과를 반복해 보면서 설정을 조정하지 않는다.

## 5. 평가 방법

### 5.1 데이터 품질

- JSON 파싱 성공 여부
- EID 중복·누락
- 본문 유무와 corpus 제외 처리
- manifest 대상 문서와 청크 문서의 완전 일치
- 필수 필드와 자료형
- 청크 ID 중복과 빈 content
- 파일 경로·크기·SHA-256 기록

### 5.2 검색

- `Hit@1`: 기대 문서가 첫 번째 결과인지 확인한다.
- `Hit@3`: 기대 문서가 상위 3개 안에 있는지 확인한다.
- `MRR`: 정답 문서가 앞에 있을수록 높은 점수를 준다.
- 평균 검색 시간: 질문 1건의 검색과 결합에 걸린 평균 시간이다.

이번 비교의 정답은 `document_id`를 기준으로 판정한다. 같은 문서의 definition·body 청크 중 어느 것이 검색돼도 문서 적중으로 계산한다.

### 5.3 생성·RAG 답변

- 자동 검사: JSON 구조, 필수 필드, 응답 유형, `used_chunk_ids` 유효성
- 정상 답변 평가: 근거 일치 40점, 질문 충족 25점, 설명 수준 25점, 명확성 10점
- 보류·거절 평가: 기대 응답 유형, 빈 청크 ID 목록, 추측 여부를 PASS/FAIL로 확인
- RAGAS: 개별 답변의 Faithfulness와 Answer Relevancy를 계산하도록 구현
- 사람 검토: 자동 검사와 LLM 평가가 충돌하거나 실패한 사례를 우선 확인

근거 일치 또는 질문 충족이 0점이면 총점과 관계없이 실패다. 글자 수 이탈은 초기에는 실패가 아닌 `length_warning`으로 기록한다.

## 6. 테스트 계획과 수행 상태

| ID | 영역 | 계획 | 결과 근거 | 상태 |
| :--- | :--- | :--- | :--- | :---: |
| DATA-01 | 원본 | 75,835건의 형식·EID·본문·중복 검사 | `outputs/aks_raw_validation.*` | PASS |
| DATA-02 | 청크 | manifest와 전체 청크의 문서·필드·ID 검사 | Document Card와 청크 검증 기록 | PASS |
| RET-01 | Dense | Dev 25문항 Hit@1·Hit@3·MRR·시간 | Hybrid 검색 보고서 | PASS |
| RET-02 | BM25 | 같은 질문·top-k로 단독 비교 | Hybrid 검색 보고서 | PASS |
| RET-03 | Hybrid | RRF 결합과 문서당 제한 적용 비교 | Hybrid 검색 보고서 | PASS |
| RET-04 | 고유명사 | 이름이 직접 포함된 5문항 회귀 | 고유명사 회귀 보고서 | PASS |
| GEN-01 | 출력 계약 | JSON Schema와 여섯 응답 유형 검사 | pytest | PASS |
| GEN-02 | 출처 | 검색에 없는 ID 차단·Citation 조립 | pytest | PASS |
| GEN-03 | 수준별 답변 | easy/general/advanced Prompt와 길이 설정 | 코드·표본 확인 | PARTIAL |
| SAFE-01 | 안전 | 비밀정보 요청을 검색 전에 거절 | pytest | PASS |
| SAFE-02 | 범위 | 실시간·코딩 등 범위 밖 요청 차단 | pytest | PASS |
| UI-01 | 화면 | 실제/Mock 모드, 출처 묶기, 근거 보기 | pytest·시연 확인 | PASS |
| UI-02 | 접근 | 빈 질문 안내와 브라우저 TTS | pytest·시연 확인 | PASS |
| EVAL-01 | RAGAS | 개별 응답 Faithfulness·Relevancy 계산 | 구현·pytest | PARTIAL |
| E2E-01 | 통합 | 질문부터 답변·출처까지 성공률·P95 | 공식 집계 없음 | NOT RUN |
| FT-01 | Fine-tuning | 같은 기반 모델의 전후 품질 비교 | 학습 미실행 | NOT RUN |

## 7. 수행 결과

### 7.1 원본과 청크 품질

| 항목 | 결과 | 판정 |
| :--- | ---: | :---: |
| 상세 원본 JSON | 75,835건 | PASS |
| 정상 corpus 대상 | 75,820건 | PASS |
| 본문 누락 | 15건, corpus 제외 | PASS |
| JSON 파싱 오류 | 0건 | PASS |
| 중복 EID | 0건 | PASS |
| JSONL 누락 EID | 0건 | PASS |
| 최종 청크 | 179,028건 | PASS |
| manifest 대상 문서 누락 | 0건 | PASS |
| 제외 문서의 잘못된 포함 | 0건 | PASS |
| 빈 청크·중복 청크 ID·필드 오류 | 0건 | PASS |

최종 제출 청크는 2026-09-03에 다시 검사했다. 179,028개 청크와 75,820개 문서가 manifest 대상과 일치했고, 파일 크기 371,158,516 bytes, SHA-256 `444d9fc8e8da5c845610d0a960a43ef04152dd525087e659c511b72382b317e0`을 검증 보고서에 기록했다.

### 7.2 자동 테스트

| 항목 | 결과 |
| :--- | :--- |
| Workflow | `Python tests` |
| 실행 환경 | Ubuntu 24.04.4, Python 3.12.14 |
| 결과 | `184 passed, 53 subtests passed` |
| 실행 시간 | 1.74초 |
| 판정 | PASS |

자동 테스트는 데이터 수집 로직, 청킹, Pinecone Adapter, BM25·Hybrid 결합, RAG 계약, 안전·범위 검사, Ollama 구조화 출력, Streamlit 연결과 RAGAS 평가 연결을 검사한다.

### 7.3 Dense·BM25·Hybrid 비교

Dev의 검색 평가 대상 25문항을 동일한 `top_k=3`으로 비교했다.

| 검색 방식 | Hit@1 | Hit@3 | MRR | 평균 검색 시간 |
| :--- | ---: | ---: | ---: | ---: |
| Dense | 0.76 (19/25) | 0.88 (22/25) | 0.800 | 0.601초 |
| BM25 | 0.20 (5/25) | 0.32 (8/25) | 0.260 | 0.442초 |
| Hybrid | **0.76 (19/25)** | **0.92 (23/25)** | **0.820** | 1.043초 |

Hybrid는 Dense보다 정답 문서를 상위 3개 안에서 한 건 더 찾았고 MRR도 `0.020` 높았다. 대신 평균 검색 시간은 `0.442초` 늘었다. BM25 단독 성능은 낮아 Dense를 대체하지 않고 정확한 제목·별칭을 보완하는 용도로 사용한다.

### 7.4 고유명사 회귀

| 방식 | Hit@1 | Hit@3 | MRR |
| :--- | ---: | ---: | ---: |
| Dense | 0.60 (3/5) | 0.80 (4/5) | 0.667 |
| BM25 | 1.00 (5/5) | 1.00 (5/5) | 1.000 |
| Hybrid | **1.00 (5/5)** | **1.00 (5/5)** | **1.000** |

Dense는 `종묘` 질문에서 `중앙종묘㈜`를 먼저 찾고, `향원정` 질문에서 `향현사`를 먼저 찾는 사례가 있었다. 제목·별칭 일치를 사용하는 Hybrid는 두 질문 모두 기대 원문을 1위로 복원했다.

### 7.5 검색 설정 비교

| 비교 항목 | 확인 결과 | 채택 기준 |
| :--- | :--- | :--- |
| 후보 수 5/10/20/25 | 후보가 많다고 항상 좋아지지 않음 | Dense 10 + BM25 10 |
| 최종 top-k 3/5 | 5개로 늘려도 놓친 두 질문을 추가로 찾지 못함 | `top_k=3` |
| 문서당 제한 없음/2/1 | 최대 2개는 Hit 지표를 유지하며 한 문서 3개 독점 방지 | 최대 2개 |
| Dense 가중치 1.0~2.5 | 1.5 이상은 동일 성능, 1.0은 하락 | Dense 1.5 / BM25 1.0 |
| RRF threshold | 정답·오답·범위 밖 점수 분포가 크게 겹침 | 적용하지 않음 |

### 7.6 생성·답변 품질

다음 기능은 구현과 자동 검사가 완료됐다.

- EXAONE 3.5 기반 Ollama 생성
- easy/general/advanced 수준별 Prompt와 생성량
- 여섯 응답 유형의 구조화 출력
- `CTX-1` 같은 짧은 근거 참조를 실제 `used_chunk_ids`로 복원
- 한 청크만 가리키는 잘린 ID를 복원하고 사용할 근거가 없으면 답변을 보류
- 복합 질문·대상 누락 표현·검색 결과의 동명 항목에 대한 확인 질문
- 답변 내용과 응답 유형이 어긋난 일부 전제 정정 결과를 계약에 맞게 정규화
- 보류·확인·거절 응답의 `used_chunk_ids`를 빈 목록으로 유지
- 사용된 청크에서 Citation과 근거 문장을 복사
- 개별 답변의 RAGAS Faithfulness·Answer Relevancy 계산

그러나 전체 Dev·Holdout을 실제 생성 모델로 실행한 평균 점수, 환각률, 응답 유형 정확도, 평균·P95 응답시간과 비용은 공식 집계되지 않았다. 따라서 화면의 개별 평가값이나 예시 응답을 전체 모델 성능으로 해석하지 않는다.

Qwen과 EXAONE 답변을 사람이 비교한 표본에서는 EXAONE이 어려운 한자어를 줄이고 연도 흐름을 풀어 설명하는 경향이 관찰되어 시연 모델로 선택했다. 동일 고정 문맥·동일 Prompt의 정량 비교가 아니므로 공식 모델 우위로 단정하지 않는다.

<!-- PDF_PAGE_BREAK -->

### 7.7 LangGraph 참고 실험

발표자료에 정리된 같은 질문 세트 비교 결과는 다음과 같다.

| 지표 | 기존 방식 | 초기 LangGraph | 이유 기반 LangGraph |
| :--- | ---: | ---: | ---: |
| 응답 유형 정확도 | 72.7% | 69.7% | 78.8% |
| 보류 판단 정확도 | 72.7% | 69.7% | 84.8% |
| Citation precision | 100.0% | 100.0% | 95.0% |
| Citation recall | 64.0% | 60.0% | 76.0% |
| 평균 응답시간 | 7,628ms | 7,936ms | 9,725ms |
| 재검색 문항 | 0건 | 18건 | 0건 |
| 실행 오류 | 0건 | 0건 | 0건 |

초기 LangGraph는 정확도가 낮아지고 불필요한 재검색이 늘었다. 이유 기반 분기는 정확도와 Citation recall을 높였지만 기존 방식보다 평균 응답시간이 약 2.1초 늘고 Citation precision이 5%p 낮아졌다.

이 결과의 평가 문항 수, commit, Prompt·모델 설정과 원본 결과 파일이 현재 저장소에 완전하게 남아 있지 않으므로 `REFERENCE`로 분류한다. 일정 안에 최종 서비스와 통합 회귀 검증을 마치기 어려워 3차 프로젝트 실행 경로에는 포함하지 않았다.

## 8. 대표 실패 사례

| 사례 | 증상 | 구분 | 현재 대응 | 후속 개선 |
| :--- | :--- | :--- | :--- | :--- |
| 종묘 | Dense 1위가 `중앙종묘㈜` | 검색 실패 | Hybrid에서 원문 1위 | 회귀 세트 유지 |
| 향원정 | Dense 1위가 `향현사` | 검색 실패 | Hybrid에서 원문 1위 | 제목·별칭 평가 확대 |
| Dev 006·015 | 세 검색 방식 모두 top-3 미적중 | 검색 실패 | 실패 사례로 보존 | Query rewrite·reranker 검토 |
| 직지 | 사용자가 기대한 표제어 대신 유사한 다른 항목 노출 가능 | 표제어·오타 처리 부족 | 공식 정량 결과 없음 | exact title·alias 후보 안내 연결 |
| 복합 질문 | 여러 질문을 하나의 검색으로 처리하면 일부 근거 누락 | 요청 처리 한계 | 한 번에 한 질문을 요청 | 질문 분해·질문별 검색 검토 |
| 근거 부족 | 점수만으로 답변 가능 여부를 구분하기 어려움 | 근거 판정 한계 | threshold 없이 내용 확인 | 의미 기반 EvidenceChecker 비교 |
| `chunk_id` 잘림 | 모델이 실제 ID의 끝이나 해시 일부를 빼 답변이 예외로 종료됨 | 생성·계약 연결 오류 | 한 청크만 가리키는 접두사·해시 누락을 복원해 대표 질문 36/36 정상 | 회귀 테스트 유지 |
| 거절 응답의 근거 | `safety_refusal` 등 답변이 아닌 응답에 근거가 붙어 계약 위반 | 응답 정규화 오류 | 답변이 아닌 응답은 `used_chunk_ids=[]`로 정규화 | 응답 유형별 회귀 테스트 유지 |

## 9. 과제에서 제시한 평가 방법 적용 여부

제시된 평가 기술을 모두 사용해야 하는 것은 아니며, 실제 구현 대상과 실행 결과가 있는 항목만 결과로 포함했다.

| 평가 방법 | 3차 프로젝트 적용 | 설명 |
| :--- | :---: | :--- |
| 데이터셋 품질 | 적용 | 결측·중복·누락·필드·출처 추적 검사 |
| Embedding·Retriever | 적용 | Dense·BM25·Hybrid Hit@1·Hit@3·MRR·시간 비교 |
| Hybrid Search | 적용 | RRF 설정과 고유명사 회귀 검증 |
| RAG 답변·환각 | 부분 적용 | RAGAS와 Citation 검증 구현, 공식 전체 집계 미완료 |
| LLM-as-a-Judge | 부분 적용 | RAGAS 평가 연결, 전체 모델 비교 결과 미완료 |
| Human Evaluation | 표본 관찰 | Qwen·EXAONE 응답을 비교했으나 공식 점수표는 미완료 |
| 시스템 통합 | 부분 적용 | 실제 시연 흐름과 자동 테스트 완료, E2E 성공률·P95 미측정 |
| LangGraph | 참고 실험 | 개선 가능성 확인, 최종 서비스 미통합 |
| Fine-tuning·LoRA·QLoRA | 미적용 | 동일 조건의 학습 전후 비교 미수행 |
| BLEU·ROUGE·Exact Match/F1 | 미적용 | 서술형 답변의 공식 기준 답안·전체 실행 결과 미완료 |
| Reranker·GraphRAG·Agent | 미적용 | 이번 MVP 범위 밖 |
| LangSmith Trace | 미적용 | 화면의 자체 실행 과정 표시를 사용 |

## 10. 결론과 제한사항

### 10.1 채택한 구성

```text
Dense 후보 10 + BM25 후보 10
→ RRF(k=60, 1.5/1.0)
→ 문서당 최대 2청크
→ 최종 top_k=3
→ 점수 threshold 없이 근거 내용 확인
→ EXAONE 3.5 수준별 답변
→ used_chunk_ids 검증 후 Citation 조립
```

Hybrid는 일반 Dev에서 Hit@3와 MRR을 개선했고, 고유명사 회귀에서 Dense의 대표 실패를 보완했다. 증가한 검색 시간은 평균 약 0.44초로, 고유명사 검색 안정성 개선과 교환되는 비용이다.

### 10.2 남은 제한

- Holdout 12건과 고유명사 회귀 5건의 사람 검수 상태가 `draft`다.
- 생성 품질·환각률·응답 유형 정확도의 전체 집계가 없다.
- 전체 E2E 성공률과 평균·P95 응답시간, 호출 비용을 측정하지 않았다.
- Fine-tuning 전후 비교를 수행하지 않았다.
- 청킹 후보 CH-01~04의 공식 검색·답변 품질 비교가 끝나지 않았다.
- LangGraph 개선안은 조건 기록과 통합 회귀 검증이 부족해 최종 서비스에서 제외했다.

### 10.3 후속 우선순위

1. Holdout과 회귀 문항의 사람 검수를 완료한다.
2. 실제 서비스 경로로 Dev·Holdout을 실행해 응답 유형, Citation, 지연시간을 집계한다.
3. 의미 기반 EvidenceChecker 또는 reranker를 비교한다.
4. 오타·별칭 후보 안내와 복합 질문 분해를 각각 별도 기능으로 검증한다.
5. LangGraph 개선안을 같은 환경에서 다시 측정한 뒤 정확도와 지연시간을 함께 판단한다.
6. Fine-tuning은 고정 문맥·같은 기반 모델·같은 Prompt 기준선을 확보한 뒤 진행한다.

## 11. 재현 명령

```powershell
# 전체 자동 테스트
python -m pytest -q

# Dense·BM25·Hybrid 비교
python scripts/evaluate_hybrid_retrieval.py `
  --cases data/evaluation/aks_rag_dev_v1.jsonl `
  --split dev --top-k 3

# 고유명사 회귀
python scripts/evaluate_hybrid_retrieval.py `
  --cases data/evaluation/aks_named_heritage_regression_v1.jsonl `
  --split regression --top-k 3 `
  --output outputs/aks_named_heritage_regression_result.json

# 전체 청크 무결성 재검증
python scripts/validate_aks_chunks.py `
  --input data/processed/aks_full_chunks.jsonl `
  --manifest data/manifest.csv `
  --report outputs/aks_full_chunks_validation.json
```

실제 검색 명령은 OpenAI와 Pinecone 키, BM25 DB가 필요하다. 실제 답변 생성에는 접근 가능한 Ollama HTTP Service가 추가로 필요하다.

## 12. 근거 문서

- `outputs/aks_raw_validation.json`, `outputs/aks_raw_validation_report.md`
- `docs/document-card.md`
- `docs/hybrid_retrieval_evaluation_report.md`
- `docs/hybrid_retrieval_experiment_matrix.md`
- `docs/named_heritage_retrieval_regression_report.md`
- `docs/track_b/02_generation_contract.md`
- `docs/track_b/03_prompt_baseline.md`
- `docs/track_b/04_generation_evaluation_criteria.md`
- GitHub Actions run `33585427145`
- `3차프로젝트_공유용_수정본.pptx`의 검색·LangGraph·모델 비교 슬라이드
