# RetrievedContext 계약 — B

정제·청킹 계층의 저장 청크는 원본 JSONL과 같은 `source_url` 필드를 유지한다. 검색 계층(B)이 RAG·생성 계층에 전달하는 `RetrievedContext`도 0.3 공통 계약에 따라 `source_url`을 사용한다. AKS 웹 문서는 페이지 번호를 사용하지 않으므로 `page` 필드는 검색 반환 형식에 포함하지 않는다.

현재 서비스가 사용하는 V1 Pinecone 인덱스는 기존 metadata의 `source`와 `source_url`을 모두 읽을 수 있다. Retriever Adapter가 이를 `source_url` 하나로 정규화하며, V1에 없는 `metadata.chunking_fingerprint`는 `null`로 반환한다. 이 정규화는 기존 `aks-rag-v1` 인덱스를 재적재하지 않고 검색 시점에 적용한다.

## 저장 청크

```json
{
  "chunk_id": "aks:E0002452:3fa52c9018ab:9d1e2f3a4b5c:body:0001",
  "document_id": "aks:E0002452",
  "title": "경복궁 향원정",
  "content": "향원정은 왕과 가족의 휴식처로 이용되었다.",
  "source_url": "https://encykorea.aks.ac.kr/Article/E0002452",
  "section": "body",
  "metadata": {
    "eid": "E0002452",
    "field": "예술·체육/건축",
    "era": "조선/조선 후기",
    "primary_type": "유적/건물",
    "aliases": [],
    "last_modified_at": "2023-02-07T08:15:00.847",
    "license": "출처 표기 필수",
    "document_fingerprint": "3fa52c9018ab",
    "chunking_fingerprint": "9d1e2f3a4b5c",
    "chunking_version": "v2"
  }
}
```

- `chunk_id`: `aks:{eid}:{document_fingerprint}:{chunking_fingerprint}:{section}:{ordinal}`. 동일 원문과 동일 정제/청킹 설정이면 재실행해도 동일하며, 청킹 설정이 바뀌면 다른 ID가 생성됩니다.
- `content`: `definition`과 `body`를 섞지 않고 각각 청킹합니다. 임베딩 시에는 제목·section을 별도로 앞에 붙이되, 인용할 `content`는 원문 근거만 보존합니다.
- 필수 값이 없으면 필드를 삭제하거나 빈 문자열을 사용하지 않고 `null`을 사용합니다. `metadata` 내부의 선택 필드도 `null`을 허용합니다.

## 검색 반환 형식

```json
{
  "chunk_id": "aks:E0002452:3fa52c9018ab:9d1e2f3a4b5c:body:0001",
  "document_id": "aks:E0002452",
  "title": "경복궁 향원정",
  "content": "향원정은 왕과 가족의 휴식처로 이용되었다.",
  "source_url": "https://encykorea.aks.ac.kr/Article/E0002452",
  "section": "body",
  "retrieval_rank": 1,
  "retrieval_score": 0.82,
  "score_type": "similarity",
  "metadata": {
    "aliases": [],
    "document_fingerprint": "3fa52c9018ab",
    "chunking_fingerprint": null
  }
}
```

- `source_url`: 원문 URL이다. 이전 V1 Pinecone metadata의 `source` 또는 `source_url`을 검색 시 하나의 필드로 정규화한다.
- `page`: 웹 문서 계약에서 제거한다. AKS는 웹 API 원본이므로 페이지 번호를 별도 반환하지 않는다.
- `metadata.chunking_fingerprint`: 식별·추적용 값이다. V1 인덱스에는 없으므로 Adapter가 `null`을 추가하며, 새 청킹 산출물에는 실제 fingerprint가 들어갈 수 있다.
- 빈 문자열과 `"NONE"`은 `null`로 정규화하고, 별칭이 없으면 `metadata.aliases=[]`를 사용한다.
- `retrieval_rank`: 검색 시점에 1부터 부여합니다.
- Pinecone MVP의 `retrieval_score`는 높을수록 유사합니다. 점수가 제공되지 않으면 `null`, `score_type="unknown"`을 사용합니다.
- 근거를 찾지 못하면 Retriever는 `[]`을 반환합니다. 근거 부족 상태 전환은 서비스 RAG Chain의 책임입니다.

## 실행 순서

```powershell
# 1. 정제·청킹: 성공 응답 기준 전체 75,835건
python scripts/build_aks_chunks.py --input "data/raw/encykorea_full_75835_clean.jsonl"

# 2. 외부 API를 호출하지 않는 산출물 확인
python scripts/index_aks_pinecone.py --dry-run

# 3. .env에 OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME을 입력한 뒤
#    먼저 100개 청크만 적재한다.
python scripts/index_aks_pinecone.py --limit 100

# 4. 검색 결과를 확인한다. (처음 100개 청크에 있는 항목으로 질문)
python scripts/search_aks.py "1928년 대구에서 조직된 비밀결사는 무엇이야?" --top-k 3

# 5. 결과가 정상이면 전체 청크를 적재한다.
python scripts/index_aks_pinecone.py
```

원본 JSONL과 생성된 청크/벡터 인덱스는 용량·라이선스 관리 대상이므로 Git에 커밋하지 않습니다.

## 실제 V1 검색 확인 (2026-08-31, Adapter 적용 후)

기본 namespace `__default__`의 전체 179,028개 청크가 적재된 `aks-rag-v1`에서 아래 질문을 `top_k=3`으로 검색했습니다.

```text
질문: 1928년 대구에서 결성되어 만주 독립군을 지원하려 했던 비밀결사는 무엇이야?

1. title=ㄱ당, document_id=aks:E0000003, section=definition
   score_type=similarity, retrieval_score=0.488330156
   source_url=https://encykorea.aks.ac.kr/Article/E0000003
   metadata.chunking_fingerprint=null
2. title=대한독립군결사대, document_id=aks:E0014967, section=definition
   score_type=similarity, retrieval_score=0.479111075
   source_url=https://encykorea.aks.ac.kr/Article/E0014967
   metadata.chunking_fingerprint=null
3. title=대한통군부, document_id=aks:E0015220, section=definition
   score_type=similarity, retrieval_score=0.468744308
   source_url=https://encykorea.aks.ac.kr/Article/E0015220
   metadata.chunking_fingerprint=null
```

각 결과는 위 JSON 계약의 10개 최상위 필드를 포함해 반환됩니다. `retrieval_score`는 Pinecone cosine similarity로, 값이 클수록 질문과 더 유사합니다. 실제 전체 RetrievedContext 예시 3건과 Dev 25건 Hit@3 결과는 팀 내부 전달용 `data/handoff/`에 별도로 보관합니다.
