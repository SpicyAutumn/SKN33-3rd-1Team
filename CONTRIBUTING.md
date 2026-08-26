# Git & GitHub 협업 가이드

## 1. 핵심 규칙

- `main` 브랜치는 항상 설치·실행 가능한 상태로 유지합니다.
- `main`에 직접 push하지 않고 기능 브랜치와 Pull Request를 사용합니다.
- 한 PR은 한 가지 목적만 다룹니다.
- 최소 1명의 팀원 승인을 받은 후 병합합니다.
- API 키, 개인정보, 허가받지 않은 문서, 대용량 벡터 인덱스는 커밋하지 않습니다.

## 2. 최초 1회 설정

```bash
git clone https://github.com/SpicyAutumn/SKN33-3rd-1Team.git
cd SKN33-3rd-1Team
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

본인 정보 확인:

```bash
git config user.name
git config user.email
```

## 3. 매 작업 시작 흐름

```bash
git switch main
git pull origin main
git switch -c feature/기능이름
```

Git 버전이 낮아 `switch`가 동작하지 않으면 다음을 사용합니다.

```bash
git checkout main
git pull origin main
git checkout -b feature/기능이름
```

### 브랜치 이름

| 종류 | 용도 | 예시 |
| :--- | :--- | :--- |
| `feature/*` | 새 기능 | `feature/document-loader` |
| `fix/*` | 오류 수정 | `fix/source-page-missing` |
| `docs/*` | 문서 | `docs/test-report` |
| `test/*` | 테스트 | `test/rag-evaluation-set` |
| `refactor/*` | 동작 변경 없는 구조 개선 | `refactor/retriever` |
| `chore/*` | 환경·설정 | `chore/add-gitignore` |

영문 소문자와 하이픈 사용을 권장합니다. 개인 이름보다 작업 목적을 사용합니다.

## 4. 작업과 커밋

작업 중 수시로 확인합니다.

```bash
git status
git diff
```

가능하면 변경 파일을 선택해 스테이징합니다.

```bash
git add src/retrieval/retriever.py tests/unit/test_retriever.py
git diff --staged
git commit -m "feat: 문서 검색기 구현"
```

`git add .`을 사용할 때는 `.env`, 원본 문서, 벡터 DB 파일이 제외되는지 먼저 확인합니다.

### 커밋 메시지

형식은 `type: 변경 내용`입니다.

| Type | 의미 | 예시 |
| :--- | :--- | :--- |
| `feat` | 기능 추가 | `feat: PDF 문서 로더 추가` |
| `fix` | 버그 수정 | `fix: 페이지 메타데이터 누락 수정` |
| `docs` | 문서 수정 | `docs: 설치 방법 보완` |
| `test` | 테스트 | `test: 답변 불가 질문 추가` |
| `refactor` | 구조 개선 | `refactor: 프롬프트 생성 함수 분리` |
| `style` | 포맷만 변경 | `style: import 순서 정리` |
| `chore` | 설정·패키지 | `chore: LangGraph 의존성 추가` |

좋은 커밋은 작고 실행 가능한 단위입니다. 코드와 무관한 대량 포맷 변경을 기능 커밋과 섞지 않습니다.

## 5. Push와 Pull Request

```bash
git push -u origin feature/기능이름
```

PR 작성 시 다음을 지킵니다.

- 제목도 커밋 형식처럼 작성합니다: `feat: PDF 문서 로더 추가`
- 구현 내용뿐 아니라 확인 방법과 결과를 적습니다.
- LLM/RAG 변경은 사용한 데이터, 모델, 청크, `top_k`, 프롬프트 등 재현 조건을 적습니다.
- 화면 변경은 캡처, 평가 변경은 전후 표를 첨부합니다.
- 비용이 발생하는 외부 API 테스트는 실행 횟수와 대략적인 범위를 알립니다.
- 본인이 먼저 `Files changed`를 검토한 뒤 리뷰를 요청합니다.

### 리뷰어 체크리스트

- [ ] PR 목적과 변경 범위가 일치한다.
- [ ] 설치·실행 또는 테스트 방법이 적혀 있다.
- [ ] 경로와 환경 변수가 하드코딩되지 않았다.
- [ ] API 키·개인정보·제한 문서가 없다.
- [ ] 답변이 문서 근거를 사용하고 출처를 반환한다.
- [ ] 근거가 없을 때의 동작이 있다.
- [ ] 새 패키지가 `requirements.txt`에 반영되었다.
- [ ] 관련 문서와 테스트가 갱신되었다.

## 6. 병합 방식과 브랜치 정리

팀에서는 GitHub의 **Squash and merge** 사용을 권장합니다. PR 단위로 `main` 이력을 읽기 쉽고 되돌리기도 쉽습니다. 팀이 다른 방식을 선택하면 착수 회의에서 하나로 통일합니다.

병합 후:

```bash
git switch main
git pull origin main
git branch -d feature/기능이름
```

GitHub의 `Delete branch`로 원격 브랜치도 삭제합니다.

## 7. 충돌 해결

충돌이 발생한 작업자가 최신 `main`을 반영하고, 해당 파일을 수정한 팀원과 함께 해결합니다.

```bash
git switch feature/기능이름
git fetch origin
git merge origin/main
```

충돌 표시를 직접 정리한 후 코드 또는 노트북이 정상 실행되는지 확인하고 커밋·push합니다. 이해하지 못한 쪽의 코드를 임의로 삭제하지 않습니다.

## 8. LLM 프로젝트 추가 규칙

### 데이터와 보안

- `.env`와 실제 비밀 값은 절대 commit/push하지 않습니다.
- 내부 문서와 개인정보는 공개 저장소에 업로드하지 않습니다.
- 원본 문서를 올릴 수 없다면 다운로드 방법, 스키마, 익명 샘플만 제공합니다.
- 이미 노출된 키는 Git 기록에서만 지우지 말고 즉시 폐기·재발급합니다.

### Notebook

- 탐색은 Notebook에서 하되 확정된 로직은 `src/`의 함수로 옮깁니다.
- 실행 순서를 위에서 아래로 맞추고, 불필요한 대용량 출력은 지웁니다.
- 개인 절대 경로 대신 프로젝트 루트 기준 상대 경로를 사용합니다.

### 실험

- 실험마다 데이터 버전, LLM, Embedding, 청크 크기·겹침, 검색 방식, `top_k`, 프롬프트 버전을 기록합니다.
- 한 번에 한 요소를 변경하고 동일한 평가 세트로 전후를 비교합니다.
- 좋은 사례만 제시하지 않고 실패 사례와 한계도 결과 보고서에 남깁니다.

## 9. GitHub 저장소 권장 설정

팀 리더가 `Settings → Branches`에서 `main` 보호 규칙을 설정합니다.

- Pull Request 없이 병합 금지
- 최소 승인 1명
- 대화가 해결되지 않으면 병합 금지
- 가능하면 상태 검사 통과 후 병합
- 강제 push와 브랜치 삭제 금지

권한과 메뉴는 저장소 설정에 따라 다를 수 있으므로 팀 리더가 실제 화면에서 확인합니다.
