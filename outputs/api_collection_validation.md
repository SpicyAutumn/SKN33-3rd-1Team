# AKS API 원본·manifest 검증 보고서

- 실행 시각(UTC): `2026-08-28T06:16:09Z`
- 원본 JSON: 9,962건
- JSON 파싱 성공: 9,962건
- JSON 파싱 실패: 0건
- 파일 EID/API 응답 EID 불일치: 0건
- 본문 누락: 2건
- SHA-256 불일치: 0건
- 원본은 있으나 manifest 없음: 0건
- manifest 원본 경로가 없거나 누락: 0건
- API 상세 무응답/오류 manifest 행: 38건

## 판정

검증에 통과한 JSON은 원본 보관·추적 단위로 다음 담당자에게 전달할 수 있다. `api_error` 행은 원문이 없어 corpus에서 제외하며, 재시도 시에도 EID와 오류 이력을 유지한다.
