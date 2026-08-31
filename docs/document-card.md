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

## 공식 안내

- [AKS OpenAPI 신청·API 안내](https://encykorea.aks.ac.kr/Guide/OpenApiUse)
- [한국민족문화대백과사전 콘텐츠 이용 안내](https://encykorea.aks.ac.kr/Guide/ContentUse)
