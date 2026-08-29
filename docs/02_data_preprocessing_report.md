# 수집 데이터 및 데이터 전처리 보고서

## 1. 목적과 범위

- 질의응답 대상 지식 범위: 한국민족문화대백과사전 항목 원고 기반 문화·역사 질의응답
- 수집 시작일 / 종료일: 2026-08-28 / 2026-08-28 (팀 공유 드라이브 전달 JSONL 기준)
- 초기 인덱싱 범위: 성공 응답 기준 파일 순서상 첫 10,000건으로 기준을 검증한 뒤, 최종 전체 75,835건으로 확장
- 포함 기준: `status=success`, 유효한 EID, `body`가 존재하는 항목
- 제외 기준: JSON 파싱 오류, 실패 응답, 유효하지 않은 EID, 본문이 비어 있거나 너무 짧은 항목

## 2. 데이터 출처와 권한

| ID | 문서명 | 제공 기관/작성자 | URL/입수 경로 | 게시·개정일 | 수집일 | 라이선스/허가 | 공개 가능 여부 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| AKS-JSONL-20260828 | `encykorea_full_75835_clean.jsonl` | 한국학중앙연구원 | 팀 공유 드라이브 | API 응답의 `lastModifiedTime` | 2026-08-28 | 항목 원고는 출처 표기 조건으로 이용, 미디어는 별도 확인 | 원본은 Git 제외, 생성 산출물만 팀 내부 공유 |

개인정보, 사내 기밀, 저작권 제한 자료가 있으면 실제 내용을 보고서에 복사하지 않고 처리 기준과 결과만 기록합니다.

## 3. 원본 데이터 구성

| 구분 | 문서 수 | 페이지/행 수 | 용량 | 형식 | 비고 |
| :--- | ---: | ---: | ---: | :--- | :--- |
| 전체 처리 대상 | 75,835 | JSONL 75,835행 | 약 647MB | JSONL | 성공 응답 기준 |
| 최종 포함 | 75,820 | 179,028 청크 | 생성 청크 파일은 Git 제외 | JSONL | 본문이 있는 항목만 포함 |
| 제외 |  |  |  |  |  |

### 제외 문서

| 문서 ID | 제외 이유 | 처리일 |
| :--- | :--- | :--- |
|  | 중복 / 손상 / 권한 / 범위 밖 / 품질 |  |

## 4. 전처리 파이프라인

```mermaid
flowchart LR
    A[원본 수집] --> B[형식·권한 검사]
    B --> C[텍스트 추출]
    C --> D[정제·정규화]
    D --> E[Chunk 분할]
    E --> F[Metadata 부여]
    F --> G[Embedding]
    G --> H[Vector DB 저장]
```

### 단계별 처리

1. 문서 로딩: `{eid, payload, status}` JSONL을 한 줄씩 읽고 `status=success`인 항목만 선택한다.
2. 텍스트 추출/OCR: API가 제공한 `definition`, `body`를 사용하므로 OCR은 적용하지 않는다.
3. 정제·정규화: Unicode NFC, HTML 엔티티, CRLF, Markdown 링크·제목, 과도한 공백을 정리한다. 문단 경계는 유지한다.
4. 표·목록·줄바꿈 처리: 문단 단위 우선으로 합치며, 과도하게 긴 문단만 문장/공백 경계에서 분리한다.
5. 개인정보 비식별화: 공개 백과사전 원고를 사용한다. 새 개인정보를 수집하거나 생성하지 않는다.
6. 청크 분할: `body`가 있는 문서만 포함하며, `definition`과 `body`를 섞지 않고 각각 최대 1,500자, 겹침 200자로 분할한다.
7. 메타데이터 생성: EID, 출처 URL, 분야, 시대, 유형, 별칭, 수정일, 라이선스, 원문 지문을 유지한다.
8. 품질 검증: 청크 ID 재현성·필수 출처 필드·JSONL 직렬화를 단위 테스트로 확인한다.

## 5. 청크 설계

### 5.1 설계 원칙

- **검색 단위와 출처 단위의 분리:** Vector DB의 `top-k`와 점수는 청크 단위로 계산되므로, 긴 원문은 애플리케이션에서 미리 청킹하고 각 청크를 부모 문서 ID로 연결해야 한다. 이는 Pinecone의 데이터 모델링 권고와 일치한다. [Pinecone Data modeling](https://docs.pinecone.io/guides/index-data/data-modeling)
- **문서 구조 우선:** AKS는 `definition`(짧은 정의)과 `body`(상세 원고)의 기능이 다르다. 두 필드를 섞지 않고 별도 `section`으로 유지해, 검색 결과가 정의인지 상세 근거인지와 원문 URL을 함께 추적한다.
- **문단 우선 분할:** 빈 줄 문단을 가능한 한 보존하고, 최대 길이를 넘는 단일 문단만 문장 부호·공백 경계에서 나눈다. Pinecone도 내용 구조에 따른 의미적으로 일관된 구간을 권장하며, 단순 문자 수만으로 자르는 방식은 문맥을 희석할 수 있다. [Pinecone RAG guide](https://docs.pinecone.io/guides/get-started/build-a-rag-chatbot)
- **크기·중복의 균형:** 청크 크기의 보편적 최적값은 없으며 질문의 복잡도·문서 길이·생성에 전달할 결과 수에 따라 달라진다. 여러 데이터셋 연구에서도 짧고 사실적인 답에는 작은 청크가, 설명형 답에는 큰 청크가 유리했으므로 AKS 질의 세트로 비교 평가한다. [Bhat et al. (2025)](https://arxiv.org/abs/2505.21700)

### 5.2 AKS 1만 건 길이 분석

정규화된 `body`가 있는 9,998건을 분석했다. `definition`은 중앙값 36자, 90백분위 57자여서 대부분 하나의 짧은 정의 청크로 유지된다. 반면 `body`는 길이 편차가 크므로 문단 우선 분할이 필요하다.

| 본문 길이(문자 수) | 값 |
| :--- | ---: |
| 중앙값 | 769자 |
| 75백분위 | 1,292자 |
| 90백분위 | 2,283자 |
| 95백분위 | 3,545자 |
| 최댓값 | 67,548자 |
| 1,000자 이하 | 6,311건 (63.1%) |
| 1,500자 이하 | 8,032건 (80.3%) |
| 2,000자 이하 | 8,768건 (87.7%) |

따라서 1,500자는 본문 약 80%를 하나의 문맥 단위로 유지하면서, 상위 약 20%의 장문 항목만 세분화하는 **합리적인 기본선**이다. 이는 최종 최적값을 의미하지 않는다.

### 5.3 현재 기본선과 후보 실험

- Splitter: 자체 문단 우선 문자 기반 splitter (`src/rag_indexing/pipeline.py`)
- 현재 기본선(CH-02): 최대 1,500자, 긴 단일 문단을 분할할 때만 200자 overlap
- 구분자/문서 구조 활용 방식: `definition`, `body`를 별도 `section`으로 유지하고 빈 줄 문단을 먼저 보존한다.
- overlap 비율: 200/1,500 = 약 13.3%. 다만 최근 RAG 평가 연구에서는 overlap의 평균적인 효과가 작고 중복 비용을 증가시킬 수 있다고 보고하므로, 0 overlap 대조군과 함께 평가한다. [RAGChecker](https://arxiv.org/abs/2408.08067)

| 실험 ID | 최대 길이 | overlap | 생성 청크 수 | 목적 | 상태 |
| :--- | ---: | ---: | ---: | :--- | :--- |
| CH-01 | 1,000자 | 150자 | 28,705 | 짧은 사실형 근거의 정밀도 비교 | 미평가 |
| CH-02 | 1,500자 | 200자 | 24,030 (1만 건 기준) | 문맥·저장량 균형 기본선 | 전체 179,028청크 적재·검색 확인 완료 |
| CH-03 | 2,000자 | 200자 | 22,171 | 설명형 질문의 넓은 문맥 비교 | 미평가 |
| CH-04 | 1,500자 | 0자 | 24,025 | overlap의 실제 이득 검증 | 미평가 |

### 5.4 최종 기준 확정 방법

1. 정의형·세부 사실형·설명형·동명이인 구분형을 고르게 포함한 AKS 질문 20~30개를 만든다.
2. 각 질문에 정답이 있는 `document_id` 또는 `chunk_id`를 사람이 미리 표시한다.
3. CH-01~04에 같은 임베딩 모델·같은 `top_k=3`을 적용한다.
4. `정답 청크가 top-3에 포함된 비율(Recall@3)`, 상위 순위, 청크 수(저장·임베딩 비용), 검색 지연을 비교한다.
5. 점수 우위가 없으면 더 적은 청크를 만드는 설정을 선택한다. 고유명사·EID 검색이 약하면 청크 크기만 키우기보다 metadata 필터, 키워드/하이브리드 검색 또는 reranking을 별도로 검토한다. Pinecone도 chunking 외 reranking·metadata filtering·hybrid search를 검색 정확도 개선 수단으로 제시한다. [Pinecone Increase relevance](https://docs.pinecone.io/guides/optimize/increase-relevance)

## 6. 메타데이터 스키마

| 필드 | 자료형 | 설명 | 예시 | 검색/출처 활용 |
| :--- | :--- | :--- | :--- | :--- |
| `document_id` | string | 문서 식별자 | `DOC-001` | 중복·갱신 관리 |
| `title` | string | 문서명 |  | 출처 표시 |
| `page` | integer | 원본 페이지 | 12 | 출처 표시 |
| `source` | string | URL 또는 경로 |  | 출처 표시 |
| `category` | string | 문서 분류 |  | 필터 검색 |
| `version` | string | 게시일/개정 번호 |  | 최신성 관리 |
| `chunk_id` | string | 청크 식별자 | `aks:E0002452:…:body:0001` | upsert·출처 연결 |
| `section` | string/null | `definition` 또는 `body` | `body` | 근거 구역 표시 |
| `metadata.document_fingerprint` | string | 정제 원문 지문 | SHA-256 앞 12자리 | 재실행·갱신 판별 |

## 7. 인덱싱 설정

- Embedding 모델: `OPENAI_EMBEDDING_MODEL` (기본값 `text-embedding-3-small`)
- 벡터 차원: 인덱스 생성 시 선택한 embedding 모델의 차원과 일치해야 함
- Vector DB / Index 이름: Pinecone, `PINECONE_INDEX_NAME`
- Distance metric: Pinecone cosine similarity를 MVP 기본값으로 권장
- ID 생성 규칙: `aks:{eid}:{document_fingerprint}:{section}:{ordinal}`
- Insert / Upsert 기준: 같은 `chunk_id`를 upsert하므로 동일 원문·설정 재실행은 중복이 생기지 않는다.
- 문서 삭제·갱신 방법: 원문 지문이 달라진 EID의 이전 chunk ID를 삭제한 뒤 새 chunk ID를 upsert한다. 삭제 실행 전 EID별 기존 ID 목록을 반드시 확인한다.

## 8. 전처리 결과와 검증

| 검증 항목 | 기대 결과 | 실제 결과 | 통과 여부 |
| :--- | :--- | :--- | :--- |
| 성공 원본 처리 | 75,835건 | 75,835건 | PASS |
| 본문 없는 항목 제외 | 0건 포함 | 15건 제외, 75,820문서 포함 | PASS |
| 빈 청크 없음 | 0건 | 0건 생성 | PASS |
| 필수 출처 필드 | `chunk_id`, `document_id`, `title`, `content`, `source_url`, `section`, `metadata` | 단위 테스트 통과 | PASS |
| 청크 재현성 | 동일 입력·설정에서 동일 ID | 단위 테스트 통과 | PASS |
| 청크 수 | 기록 | 179,028 | PASS |
| 벡터 검색 | 예상 출처가 top-k에 포함 | `길쌈노래에 대해 설명해줘`에서 같은 원문 EID의 definition·body 청크가 top-3에 포함 | PASS |

전처리 전후 예시를 개인정보나 제한 정보가 없는 범위에서 2~3건 제시합니다.

## 9. 재현 방법

```bash
# 팀 공유 드라이브의 JSONL 경로를 지정한다.
python scripts/build_aks_chunks.py --input "<downloaded-jsonl-path>"

# 외부 API 호출 없이 생성 청크를 확인한다.
python scripts/index_aks_pinecone.py --dry-run

# .env 설정 후 100개 청크로 적재·검색을 먼저 검증한다.
python scripts/index_aks_pinecone.py --limit 100
python scripts/search_aks.py "1928년 대구에서 조직된 비밀결사는 무엇이야?" --top-k 3

# 결과가 정상이면 전체 청크를 적재한다.
python scripts/index_aks_pinecone.py
```

- 필요한 환경 변수: `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`
- 입력 위치: 팀 공유 드라이브에서 내려받은 원본 JSONL (Git 제외)
- 출력 위치: `data/processed/aks_chunks.jsonl`, `outputs/aks_chunking_report.json` (Git 제외)
- 예상 실행 시간/비용: 전체 179,028개 청크 적재는 Pinecone Standard Trial에서 완료했다. 모델·배치·네트워크에 따라 달라 재실행 전 Pinecone Usage를 확인한다.

## 10. 한계 및 향후 개선

- 스캔 PDF/OCR 오류:
- 표·이미지 정보 손실:
- 문서 최신성:
- 데이터 편향/누락:
- 이후 개선 계획:
