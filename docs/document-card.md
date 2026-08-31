# AKS 원본 데이터 문서 카드

## 데이터 출처

- 기관: 한국학중앙연구원(AKS, Academy of Korean Studies)
- 서비스: 한국민족문화대백과사전
- 목록 API: `GET https://devin.aks.ac.kr:8080/api/articles?p={pageNo}&ps={pageSize}`
- 상세 API: `GET https://devin.aks.ac.kr:8080/api/articles/{eid}`
- 인증: 요청 헤더 `X-API-Key`; 실제 키는 `.env`에만 보관하고 Git·로그·manifest에 기록하지 않는다.

## 원본 보관 구조

- `data/raw/api/`: EID별 상세 API 원본 JSON. 본문(`body`)이 있는 최종 corpus 원본 기준이다.
- `data/raw/api_list_metadata/`: 목록 API 메타데이터 JSON. EID·제목·분야 확인용이며 본문이 비어 있을 수 있어 corpus 입력으로 사용하지 않는다.
- `data/raw/aks_full_content.jsonl`: 상세 JSON을 한 줄에 하나씩 합친 전처리 전달용 파일이다.
- `data/manifest.csv`: 원본 경로, 체크섬, 본문 길이, 상태, 출처 표기를 추적한다.

원본 JSON·JSONL은 Git에 올리지 않는다. 팀 전용 Google Drive에 전달하며, 외부 공개 링크로 공유하지 않는다. 팀원은 [공유 데이터 폴더](https://drive.google.com/drive/folders/1suuH0gytA1T2ht0OEyvpvpHH1kM4nkVM)에서 `aks_full_content.jsonl`, `aks_full_content_json.zip`을 내려받아 `data/raw/`에 둔다. `manifest.csv`는 원본 추적표이므로 Git과 Drive 양쪽에 보관한다.

## 데이터 규모와 실제 corpus 사용 기준

상세 API 수집·검증 기준으로 상세 원본 JSON은 75,835건이며, JSONL은 75,835줄이다. JSONL 파싱 오류·중복 EID·누락 EID는 모두 0건이었다.

| 파일/집합 | 형식·규모 | 보관 위치 |
| --- | --- | --- |
| 상세 원본 | EID별 JSON 75,835건 | `data/raw/api/` 또는 Drive ZIP |
| 통합 원본 | JSONL 75,835줄, 620,482,345 bytes | `data/raw/aks_full_content.jsonl` |
| 상세 원본 전달본 | ZIP, 244,008,885 bytes | `data/raw/aks_full_content_json.zip` 및 Drive |
| 추적표 | CSV, 51,158,587 bytes | `data/manifest.csv` 및 Drive |

후속 정제·청킹·검색 corpus에는 상세 API JSON만 사용한다. `manifest.csv`에서 `has_body=true`이고 `status`가 `ok`인 항목만 사용한다. 검증 시 본문(`body`)이 없는 15건은 manifest에 이력으로 남기되 corpus에서는 제외한다. 목록 API 메타데이터와 미디어는 corpus 입력이 아니다.

## 상세 JSON 구조

상세 API 응답의 원본 식별자는 `eid`이며, 대표 텍스트 필드는 `headword`(항목명), `definition`(정의), `body`(본문), `url`(원문 URL)이다. 분류·검색 보조 메타데이터로는 `field`, `era`, `primaryType`, `articleAliases`, `hashtags`, `lastModifiedTime` 등이 있을 수 있다. 원본 JSON은 수정하지 않으며, manifest와 후속 청킹 단계가 필요한 값을 별도 메타데이터로 관리한다.

## API 호출·갱신 정책

- 목록 조회: `GET /api/articles?p={pageNo}&ps={pageSize}`. `p`는 페이지 번호, `ps`는 페이지당 항목 수다.
- 상세 조회: `GET /api/articles/{eid}`. 목록에서 확인한 EID별 원문을 받는다.
- 인증: 모든 호출은 `X-API-Key` 헤더를 사용한다. 실제 키는 `.env`에만 저장한다.
- 수집 스크립트 기본값: 페이지 크기 100, 요청 제한시간 30초, 일시 오류 재시도 2회, 상세 조회 동시 요청 3개다. 과도한 동시 호출은 하지 않는다.
- 호출 제한: 현재 문서 카드에는 AKS가 공개한 고정 숫자 제한을 기록하지 않는다. 수집 전에는 공식 OpenAPI 안내·발급 조건을 다시 확인하고, 오류가 반복되면 호출 속도를 낮춘다.
- 갱신: 새 수집을 할 때는 수집 시각, `lastModifiedTime`(있는 경우), SHA-256 체크섬을 새 manifest에 기록한다. 기존 원본을 무단 덮어쓰지 않고 수집 실행 단위와 변경 여부를 남긴다.

## 수집·변환·검증 실행

프로젝트 최상위 `.env`에 `AKS_API_KEY=...`를 입력한다. `.env`에는 실제 API 키가 있으므로 Git에 올리지 않는다.

```powershell
# 목록 API 메타데이터 수집
python scripts/download_aks_list.py

# EID별 상세 본문 JSON 수집
python scripts/download_aks_full_content.py

# 상세 JSON을 JSONL로 변환
python scripts/convert_aks_json_to_jsonl.py

# manifest 생성 및 JSONL 일치 검증
python scripts/build_aks_manifest.py --verify-jsonl
```


## 콘텐츠 이용 및 출처 표기

한국민족문화대백과사전은 공공저작물로서 공공누리 제도에 따라 이용할 수 있다고 안내한다. 텍스트를 인용·표시할 때는 다음 형식을 사용한다.

```text
출처: [항목명] - 한국민족문화대백과사전 (한국학중앙연구원)
```

항목별 집필 내용은 집필자의 학술적 견해일 수 있으므로, 서비스의 공식 입장과 동일하다고 단정하지 않는다. 서비스 내용은 보완·중단될 수 있으므로 수집 시각과 원본 체크섬을 manifest에 남긴다.

## 미디어 제외 기준

이번 corpus에는 `relatedMedias`, `headMedia`의 이미지·영상·음성 파일을 내려받거나 포함하지 않는다. 미디어는 공공누리 유형, 저작권자, 다운로드 가능 여부가 항목별로 다르며, 일부는 한국민족문화대백과사전 서비스 내에서만 이용하도록 허가돼 자유 이용이 불가하다. 미디어를 후속 사용하려면 각 미디어의 `koglType`, `copyrightDisplay`, 개별 이용 조건을 별도로 검토한다.

## 검증과 manifest 생성

```powershell
python scripts/build_aks_manifest.py --verify-jsonl
```

생성 결과:

- `data/manifest.csv`
- `outputs/aks_raw_validation.json`
- `outputs/aks_raw_validation_report.md`

이 스크립트는 JSON 파싱, 파일명·내부 EID 일치, 중복 EID, 본문 존재, SHA-256 체크섬, 임시 파일, JSONL 줄 수·EID 일치를 검사한다.

원본 감사와 청킹 감사는 구분한다. 이 문서와 `outputs/aks_raw_validation.*`은 원본 JSON·JSONL의 무결성을 다루며, 청크 수·길이 분포·너무 짧거나 긴 청크·원문과 청크의 표본 대조 결과는 [전처리 보고서](02_data_preprocessing_report.md)에 기록한다.

전체 청킹 전달본(`data/processed/aks_full_chunks.jsonl`)을 manifest와 대조했다. 결과는 75,820문서·179,028청크이며, JSON 파싱 오류·필수 필드 오류·빈 청크·중복 청크 ID는 모두 0건이었다. 또한 manifest의 `has_body=true`, `status=ok` 대상 75,820건과 청킹 문서 ID가 완전히 일치했고, 제외 대상이 청킹 결과에 섞인 경우도 0건이었다. 재검증 명령은 다음과 같다.

```powershell
python scripts/validate_aks_chunks.py --input data/processed/aks_full_chunks.jsonl --report outputs/aks_full_chunks_validation.json
```

## 공식 안내

- [AKS OpenAPI 신청·API 안내](https://encykorea.aks.ac.kr/Guide/OpenApiUse)
- [한국민족문화대백과사전 콘텐츠 이용 안내](https://encykorea.aks.ac.kr/Guide/ContentUse)
