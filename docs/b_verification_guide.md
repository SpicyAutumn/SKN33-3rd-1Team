# B 파트 직접 확인 가이드

아래 명령은 프로젝트 루트에서 PowerShell 터미널에 한 줄씩 실행한다. `data/raw`의 원본을 변경하거나 Pinecone에 다시 업로드하지 않고, 현재 상태를 읽어 확인하는 명령만 정리했다.

## 1. 청크 수 확인

```powershell
.\.venv\Scripts\python.exe scripts\index_aks_pinecone.py --dry-run
```

정상 결과:

```json
{"chunks_ready": 179028, "start_offset": 0, "input_path": "...aks_chunks.jsonl"}
```

`--dry-run`은 OpenAI나 Pinecone API를 호출하지 않는다. 생성된 청크 파일을 읽어 몇 개가 준비됐는지만 확인한다.

원본에서 청크를 새로 만들 때 `scripts/build_aks_chunks.py`의 `--limit`은 선택 사항이다. 생략하면 전달받은 성공 원본 전체를 처리한다. 예를 들어 1만 건만 시험하려면 `--limit 10000`을 명시한다.

## 2. 청크 하나 직접 보기

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
Get-Content .\data\processed\aks_chunks.jsonl -Encoding utf8 -TotalCount 1
```

한 줄이 하나의 검색 단위다. 다음 필드를 확인한다.

Windows PowerShell 5.1은 BOM 없는 UTF-8 파일을 기본 인코딩으로 읽지 못할 수 있으므로, 반드시 `-Encoding utf8`을 붙인다. 첫 두 줄은 현재 터미널의 출력 인코딩도 UTF-8로 맞춘다.

- `content`: 생성 모델에 전달할 원문 조각
- `section`: `definition` 또는 `body`
- `chunk_id`: `aks:{EID}:{원문지문}:{청킹설정지문}:{구역}:{순번}` 형태의 재현 가능한 ID
- `metadata`: 시대·분야·유형·별칭·라이선스 등 필터링/출처용 정보

청킹 규칙은 [pipeline.py](../src/rag_indexing/pipeline.py)의 `normalize_text`, `split_content`, `build_chunks`에 있다. 본문은 최대 1,500자씩 나누고, 긴 문단은 앞 청크의 마지막 200자를 다음 청크에 겹쳐서 문맥이 끊기지 않게 했다. 정의와 본문은 섞지 않는다.

청크 크기·overlap·청킹 버전이 달라지면 `청킹설정지문`도 달라져 같은 원문이라도 다른 `chunk_id`가 생성된다.

## 3. Pinecone 전체 업로드 수 확인

```powershell
.\.venv\Scripts\python.exe scripts\check_aks_index.py
```

정상 결과는 아래처럼 `MATCH`다.

```json
{
  "index_name": "aks-rag-v1",
  "namespace": "",
  "expected_vector_count": 179028,
  "actual_vector_count": 179028,
  "status": "MATCH"
}
```

이 명령은 Pinecone에 저장된 벡터 개수만 조회한다. 임베딩을 새로 만들거나 비용이 드는 업로드를 하지 않는다.

## 4. 실제 검색 결과 확인

```powershell
.\.venv\Scripts\python.exe scripts\search_aks.py "ㄱ당은 어떤 단체야?" --top-k 3
```

정상이라면 첫 결과의 `title`은 `ㄱ당`, `retrieval_rank`는 `1`, `source`는 `https://encykorea.aks.ac.kr/Article/E0000003`, `page`는 `null`이다.

검색 결과는 RAG 담당자가 바로 사용할 `RetrievedContext` 형식이다. 필드 정의와 실제 상위 3건 예시는 [retrieved_context_contract.md](retrieved_context_contract.md)에 있다.

## 5. 정식 검색 평가 실행

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_aks_retrieval.py --top-k 3
```

이 명령은 사람이 정답 문서를 확인한 20개 질문을 Pinecone에 검색한다. 각 질문에서 **정답 `document_id`가 상위 3건 안에 있는지**를 판정하고, 아래 두 수치를 출력한다.

- `recall_at_k`: 20개 중 정답 문서를 top-3에서 찾은 비율
- `mrr`: 정답이 얼마나 높은 순위에 있었는지를 반영한 점수(1에 가까울수록 좋음)

2026-08-30 기준 결과는 `Recall@3 = 0.90 (18/20)`, `MRR = 0.833`이다. 상세 순위는 Git에 올리지 않는 `outputs/aks_retrieval_eval_v1_result.json`에 생성된다. 이 평가는 현재 임베딩·Pinecone 검색 조합의 기준선이며, 질문 세트를 늘려가며 계속 검증한다.

## 알아둘 점

- `data/raw/encykorea_full_75835_clean.jsonl`은 받은 원본이며, B는 이 파일을 읽기만 한다.
- `data/processed/aks_chunks.jsonl`은 B가 생성한 청크 결과다. 둘 다 용량이 커서 Git에 올리지 않는다.
- `.env`에 보이는 API 키 값은 절대 공유하거나 Git에 올리지 않는다.
- 기존 기본 namespace(`__default__`)의 179,028개 벡터는 이전 ID 체계(v1)로 적재된 데이터다. v2 청크를 새로 임베딩할 때는 `PINECONE_NAMESPACE=aks-chunk-v2`처럼 새 namespace를 지정해 적재·검색·평가한 뒤, 팀 합의 후 서비스 namespace를 전환한다. 기본 namespace에 v2를 바로 적재하려면 기존 벡터 정리 여부를 먼저 확인하고 `--allow-default-namespace`를 명시해야 한다.
