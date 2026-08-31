# AKS 하이브리드 검색 가이드

## 목적

기존 검색은 OpenAI 임베딩과 Pinecone cosine similarity를 이용한 Dense Retriever이다. 의미가 비슷한 문서를 찾는 데 강하지만, `경복궁`, `석굴암`처럼 정확한 고유명사가 질문에 포함된 경우에는 원문 제목보다 문맥이 비슷한 다른 청크가 앞설 수 있다.

하이브리드 검색은 다음 두 결과를 결합한다.

- **Dense Retriever**: Pinecone의 임베딩·cosine similarity 검색
- **BM25 Retriever**: 제목·별칭·본문의 키워드 검색. 전체 AKS 청크 JSONL로 만든 로컬 SQLite FTS5 인덱스를 사용한다.

BM25 단계에서는 제목 또는 별칭이 질문의 핵심 용어와 정확히 일치하는 청크를 먼저 후보로 둔다. 예를 들어 `경복궁에 대해 알려줘`는 제목이 `경복궁`인 원문을 우선 후보로 만든다. 그 외 후보는 SQLite FTS5의 BM25 점수(제목 5, 별칭 3, 본문 1 가중치) 순으로 정렬한다.

## 순위 결합: RRF

Pinecone cosine similarity와 BM25 점수는 범위와 뜻이 달라 직접 더하지 않는다. 각 검색기의 순위를 **Reciprocal Rank Fusion(RRF)**으로 결합한다.

```text
RRF 점수 = dense_weight / (rrf_k + Dense 순위)
         + bm25_weight / (rrf_k + BM25 순위)
```

첫 기준값은 다음과 같다.

```text
candidate_k = 10
rrf_k = 60
dense_weight = 1.5
bm25_weight = 1.0
```

`rrf_k=60`은 통상적인 RRF 기준값이다. `dense_weight=1.5`, `bm25_weight=1.0`은 아래 Dev 비교에서 선택했다. RRF 설정 변경은 검색 로직만 바꾸며 청킹·임베딩·Pinecone 재적재가 필요 없다.

## 초기 평가 결과

평가 대상은 PR #15 Dev의 `answered` 20건과 `corrected_premise` 5건, 총 25건이며 `top_k=3`이다.

| 검색 방식 | Dense 가중치 | BM25 가중치 | Hit@3 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Dense 단독 | - | - | 0.88 (22/25) | 0.80 |
| RRF 동등 결합 | 1.0 | 1.0 | 0.84 (21/25) | 0.713 |
| RRF 튜닝 | 1.5 | 1.0 | **0.92 (23/25)** | **0.82** |
| RRF 튜닝 | 2.0 | 1.0 | **0.92 (23/25)** | **0.82** |

동등 결합은 BM25 후보가 의미상 더 적합한 Dense 결과를 밀어내 성능이 낮아졌다. `1.5`와 `2.0`은 같은 결과였으므로, BM25 신호를 조금 더 남기는 작은 값인 `1.5`를 기본값으로 선택했다. Holdout의 검색 평가 대상 4건에서는 Dense 단독과 선택 설정이 모두 Hit@3·MRR 1.00이었다. Holdout 표본이 작으므로 이 결과만으로 일반화하지 않으며, 후속 질문 세트가 늘어나면 재평가한다.

## 실행

전제: 팀 Drive에서 받은 전체 청크 파일을 `data/processed/aks_chunks.jsonl`에 둔다. 이 파일과 생성되는 BM25 SQLite 파일은 대용량 원문이므로 Git에 올리지 않는다.

Pinecone 제어 API 연결이 느리거나 막힌 환경에서는 `.env`에 아래 선택 항목을 추가할 수 있다. 값은 Pinecone 콘솔의 해당 인덱스 **Host**를 복사한다. API Key가 아니므로 검색 대상 인덱스를 직접 지정하는 용도다.

```text
PINECONE_INDEX_HOST=인덱스-Host-주소
```

```powershell
# 1. 전체 179,028개 청크로 로컬 BM25 인덱스 생성
.\.venv\Scripts\python.exe scripts\build_aks_bm25.py

# 기존 BM25 인덱스를 다시 만들 때만 사용
.\.venv\Scripts\python.exe scripts\build_aks_bm25.py --force

# 2. 하이브리드 검색 결과 확인
.\.venv\Scripts\python.exe scripts\search_hybrid_aks.py "경복궁에 대해 알려줘" --top-k 3

# 3. PR #15 Dev 질문 중 answered 20건 + corrected_premise 5건으로
#    Dense 단독과 하이브리드의 Hit@3·MRR 비교
.\.venv\Scripts\python.exe scripts\evaluate_hybrid_retrieval.py --top-k 3

# Dev에서 고른 설정을 holdout의 검색 평가 대상 4건으로 확인
.\.venv\Scripts\python.exe scripts\evaluate_hybrid_retrieval.py `
  --cases data\evaluation\aks_rag_holdout_v1.jsonl --split holdout `
  --dense-weight 1.5 --top-k 3
```

3번은 총 25개 질문을 Pinecone에 읽기 전용으로 질의하며, 질문 임베딩을 위해 OpenAI Embeddings API를 호출한다. Pinecone에 벡터를 추가·수정하지 않는다. 상세 결과는 Git 제외 경로인 `outputs/aks_hybrid_retrieval_dev_result.json`에 기록된다.

## 결과 형식

하이브리드 최종 결과도 기존 RetrievedContext 계약의 최상위 10개 필드만 반환한다.

```text
chunk_id, document_id, title, content, source_url,
section, retrieval_rank, retrieval_score, score_type, metadata
```

`retrieval_score`는 결합된 RRF relevance 점수이고 `score_type`은 `relevance`이다. 원래의 cosine/BM25 개별 점수와 같은 수치로 해석하면 안 된다.

## 분리한 후속 실험

- 문서당 최대 2개 청크 제한
- score threshold
- RRF 가중치·`rrf_k` 튜닝
- BM25용 한국어 형태소 분석기 적용 여부

위 항목은 기본 하이브리드 베이스라인의 Hit@3·MRR를 먼저 확인한 뒤 별도로 비교한다.
