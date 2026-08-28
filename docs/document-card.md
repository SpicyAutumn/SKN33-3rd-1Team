# 데이터 문서 카드: 한국민족문화대백과사전

## 범위와 출처

- 데이터셋: 한국민족문화대백과사전 일반 항목 목록 및 공식 OpenAPI 상세 응답
- 제공기관: 한국학중앙연구원
- 항목 웹사이트: `https://encykorea.aks.ac.kr/Article/{EID}`
- 공식 OpenAPI: `https://devin.aks.ac.kr:8080/api/articles/{EID}`
- 원본 CSV 기준일: 파일명에 기록된 `2024-01-30`
- 현재 단계의 용도: 문화재·유산·유물 서비스 후보 corpus를 결정하기 전, 전체 분야의 CSV/API 구조 및 일치성 감사
- 범위 제외: 정제, 청킹, 임베딩, Vector DB, 검색, LLM, Fine-tuning, 웹 검색, TTS

## 콘텐츠 이용 조건과 출처 표기

한국민족문화대백과사전의 공식 [콘텐츠 이용 안내](https://encykorea.aks.ac.kr/Guide/ContentUse)에 따르면, 홈페이지 수록 자료 중 한국학중앙연구원이 저작재산권 전부를 보유한 저작물에 한해 별도 허락 없이 자유이용할 수 있다. 항목 원고(본문)는 이용 가능한 콘텐츠 범위로 안내되며 출처 표기는 다음 형식을 따른다.

```text
[항목명],『한국민족문화대백과사전』
```

API 접근 자체는 공식 [OpenAPI 신청 안내](https://encykorea.aks.ac.kr/Guide/OpenApiUse)에 따라 발급받은 키를 `X-API-Key` 헤더에 넣는다. 키는 `.env`에만 보관하고 로그, 결과 파일, Git에 남기지 않는다. API 사용 목적과 발급 조건도 계속 준수해야 한다.

## 원본 보관·추적 정책

- 표본 감사 응답은 `data/raw/api_audit/{EID}.json`에 HTTP 응답 본문 바이트 그대로 저장한다.
- 팀이 명시적으로 선택한 EID의 응답만 `data/raw/api/{EID}.json`에 저장한다. 전체 CSV 자동 전수 수집은 제공하지 않는다.
- `data/raw/`와 `outputs/`는 Git에서 제외한다. 공개·배포 전에는 이용 조건과 원문 재배포 범위를 다시 검토한다.
- `data/manifest.csv`에는 출처 URL, API URL, 수집 시각, SHA-256 체크섬, 원본 경로, 본문 길이, 라이선스 메모, 상태와 오류를 기록한다.
- 재수집 시 같은 `document_id`의 manifest 행을 갱신하며, 원본 변경 여부는 체크섬으로 확인한다.

## 미디어 제외 기준

미디어 메타데이터 CSV는 `제목·설명·키워드` 단위이고 일반 항목 CSV의 `항목명·분야·웹사이트 주소(EID)` 구조와 다르다. 항목 본문과 동일한 수집 단위로 결합할 근거가 없으므로 이번 본문 감사와 수집에서 제외한다.

또한 미디어는 자료별 권리자가 다를 수 있다. 공공누리 마크가 부착된 미디어만 안내된 자유이용 범위에 들어가며, 마크가 없는 미디어는 별도 저작권자의 허가가 필요하다. 향후 미디어를 사용할 때는 MID별 공공누리 표시, 권리자, 출처 표기, 다운로드 가능 여부를 별도로 검증해야 한다.

## API 감사 설계와 결과

- 기본 표본 크기: 25건
- seed: `20260828`
- 층화: CSV `분야` 값의 `/` 앞 대분야를 층으로 삼아 모든 대분야를 최소 1건 포함하고, 잔여 표본을 모집단 비율로 배분
- 비교: EID, 제목, 분야 문자열, 본문 존재/길이, API 전용 필드, CSV 중복·누락·URL 오류, API 오류 사유
- 최신 상세 결과: `outputs/csv_api_audit_report.md`, `outputs/csv_api_audit.json`, `outputs/csv_api_comparison.csv`

2026-08-28 실제 API 감사에서 전체 CSV 73,587행의 EID가 모두 유효하고 고유했으며, EID 중복·항목명 누락·분야 누락·잘못된 URL은 모두 0건이었다. seed `20260828`의 25건 표본은 13개 대분야를 모두 포함했고, API 응답 25건을 모두 `data/raw/api_audit/`에 원문 JSON으로 저장했다.

- EID 일치: 25/25
- 제목 완전 일치: 20/25. 차이 5건은 띄어쓰기, `료→요` 표기, 또는 지명 보강(예: `내원당`/`개성 내원당`)이었다.
- 분야 완전 일치: 23/25. 차이 2건은 `교육/교육`/`교육/학교교육`의 세부분류 변경 및 기존 분야에 `역사/조선시대사`가 추가된 복수 분야였다.
- 본문 존재: 25/25, 반환 본문 길이 399~4,150자(평균 1,203.96자)
- 공통 API 전용 필드: `definition`, `summary`, `era`, `primaryTypePartA/B`, `writerInfo`, `reference`, `relatedArticles`, `relatedMedias`, `headMedia`, `lastModifiedTime` 등

감사 결과는 표본 기반이며 전체 73,587개 항목의 API 상태를 보증하지 않는다. 최신 행별 비교와 오류는 `outputs/csv_api_comparison.csv`, 통계는 `outputs/csv_api_audit.json`에서 확인한다.

## 10,000건 원본 수집·무결성 검증 결과

사용자 승인으로 CSV의 EID 정렬 기준 첫 10,000건을 상세 API로 수집했다. 이 범위에서 API JSON이 저장된 항목은 9,962건이고, 38건은 JSON이 아닌 빈 응답으로 저장되지 않았다. 실패 38건은 manifest의 `status=api_error`, `error=invalid_json_response`으로 남겼다. 실패 EID `E0000048`의 직접 확인 결과는 HTTP `204 No Content`(0바이트)이므로, 적어도 일부 실패는 인증·네트워크 문제가 아니라 API 상세 원문 부재다.

`scripts/validate_aks_collection.py`의 전수 검증 결과는 다음과 같다.

- JSON 파싱 성공: 9,962/9,962
- 파일명 EID와 API 응답 EID 일치: 9,962/9,962
- SHA-256과 manifest 일치: 9,962/9,962
- 원본 JSON과 manifest 경로 연결 누락: 0건
- 본문이 비어 있는 JSON: 2건 (`E0007445`, `E0007458`)

따라서 현재 확보된 원문 기반 corpus 후보는 9,960건이다. 38건의 API 무응답과 본문이 없는 2건은 원문 근거가 없으므로 검색·답변 corpus에서 제외하되, EID와 실패 이력은 manifest에 유지한다. 상세 검증 결과는 `outputs/api_collection_validation.json`과 `outputs/api_collection_validation.md`에 보관한다.
