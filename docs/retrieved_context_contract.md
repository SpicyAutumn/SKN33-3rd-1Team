# RetrievedContext 계약 — B 초안

정제·청킹·검색 계층(B)이 RAG·생성 계층에 전달하는 검색 결과의 임시 계약입니다. 실제 JSONL의 필드를 확인한 뒤 확정하며, 필드명은 기존 초안의 `source` 대신 URL임을 명확히 하는 `source_url`을 사용합니다.

## 저장 청크

```json
{
  "chunk_id": "aks:E0002452:3fa52c9018ab:body:0001",
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
    "chunking_version": "v1"
  }
}
```

- `chunk_id`: `aks:{eid}:{document_fingerprint}:{section}:{ordinal}`. 동일 원문과 동일 정제/청킹 설정이면 재실행해도 동일합니다.
- `content`: `definition`과 `body`를 섞지 않고 각각 청킹합니다. 임베딩 시에는 제목·section을 별도로 앞에 붙이되, 인용할 `content`는 원문 근거만 보존합니다.
- 필수 값이 없으면 필드를 삭제하거나 빈 문자열을 사용하지 않고 `null`을 사용합니다. `metadata` 내부의 선택 필드도 `null`을 허용합니다.

## 검색 시 추가되는 필드

```json
{
  "retrieval_rank": 1,
  "retrieval_score": 0.82,
  "score_type": "similarity"
}
```

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

## 실제 검색 확인 (2026-08-29)

기본 namespace `__default__`의 전체 179,028개 청크를 `aks-rag-v1`에 적재한 뒤 아래 질문으로 상위 3건을 확인했습니다.

```text
질문: 길쌈노래에 대해 설명해줘

1. title=길쌈노래, section=definition, score=0.663182139
   content=여성들이 길쌈을 하면서 부르는 민요.
   source_url=https://encykorea.aks.ac.kr/Article/E0008547
2. title=길쌈노래, section=body, score=0.565747619
   source_url=https://encykorea.aks.ac.kr/Article/E0008547
3. title=길쌈노래, section=body, score=0.527364433
   source_url=https://encykorea.aks.ac.kr/Article/E0008547
```

각 결과는 위 JSON 계약의 모든 필드를 포함해 반환됩니다. `retrieval_score`는 Pinecone cosine similarity로, 값이 클수록 질문과 더 유사합니다.
