"""검색 연동 계층.

`.env`에 키가 설정되면 실제 Pinecone 검색으로, 없으면 Mock 응답으로 자동 전환한다.
화면 코드는 이 모듈만 호출하고 어느 쪽인지 신경 쓰지 않는다.

키를 받은 뒤 정리할 곳은 파일 안에 `[제거 예정]`으로 표시해 두었다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# scripts/search_aks.py와 같은 방식으로 src/ 를 import 경로에 추가한다.
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

REQUIRED_ENV = ("OPENAI_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME")

SOURCE_NAME = "한국민족문화대백과사전"

# 계약 0.3.0-draft: 내부 코드는 easy/general/advanced, UI 문구는 쉽게/일반/깊이 있게.
AUDIENCE_LEVELS = ("easy", "general", "advanced")
AUDIENCE_LABELS = {"easy": "쉽게 설명", "general": "일반 설명", "advanced": "깊이 있게"}
DEFAULT_AUDIENCE_LEVEL = "general"

# [제거 예정] 근거 충분성 판정은 계약상 RAG Chain 책임이다.
# RAG Chain에 grounding_decision이 들어오면 이 임시 방어를 걷어낸다.
# 값 근거: 범위 안 질문 최저 0.440, 범위 밖 질문 최고 0.335 (2026-08-31 실측)
SCORE_THRESHOLD = 0.40

# 답변 생성이 붙기 전까지 몇 건을 근거로 보여 줄지. 1위 하나만 고르면 검색 순위가
# 뒤집혔을 때 틀린 문서 하나로 출처·지도·평가가 모두 어긋난다. 서로 다른 문서를
# 이만큼 보여 주고 판단은 사람에게 맡긴다.
# [제거 예정] 생성이 연결되면 used_chunk_ids는 생성 결과가 정한다.
EVIDENCE_DOCUMENT_LIMIT = 3


def shift_level(level: str, step: int) -> str:
    """설명 수준을 한 단계 옮긴다. 양 끝에서는 그대로 둔다."""
    index = AUDIENCE_LEVELS.index(level) if level in AUDIENCE_LEVELS else 1
    return AUDIENCE_LEVELS[min(max(index + step, 0), len(AUDIENCE_LEVELS) - 1)]


def load_env() -> None:
    """`.env`를 읽어 환경 변수에 넣는다. 이미 설정된 값은 덮어쓰지 않는다."""
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip("'\"")
        if key and value:
            os.environ.setdefault(key, value)


def missing_env() -> list[str]:
    """비어 있는 필수 환경 변수 이름 목록. 값은 절대 반환하지 않는다."""
    load_env()
    return [name for name in REQUIRED_ENV if not os.getenv(name, "").strip()]


def is_live() -> bool:
    """실제 검색을 쓸 수 있으면 True."""
    return not missing_env()


def search(question: str, top_k: int = 5) -> list[dict]:
    """실제 Pinecone 검색. 키가 없으면 RuntimeError."""
    absent = missing_env()
    if absent:
        raise RuntimeError(f"환경 변수 미설정: {', '.join(absent)}")

    from rag_indexing.pinecone_store import PineconeRetriever

    return PineconeRetriever().search(question, top_k=top_k)


def _score_of(context: dict) -> float:
    """점수가 없으면 판단 불가로 보고 통과시킨다."""
    score = context.get("retrieval_score")
    return float(score) if isinstance(score, (int, float)) else 1.0


def build_response(
    question: str, contexts: list[dict], audience_level: str = DEFAULT_AUDIENCE_LEVEL
) -> dict:
    """검색 결과로 ServiceResponse를 조립한다.

    답변 생성(Track B)이 아직 없으므로 문장을 지어내지 않는다.
    유사도가 기준에 못 미치면 근거로 쓰지 않고 보류한다.
    """
    strong = [c for c in contexts if _score_of(c) >= SCORE_THRESHOLD]
    if not strong:
        return {
            "response_type": "insufficient_evidence",
            "audience_level": audience_level,
            "message": (
                "현재 검색된 공식 자료만으로는 이 질문을 확인하기 어렵습니다. "
                "확인 가능한 다른 문화유산 관련 질문을 해 주세요."
            ),
            # 걸러낸 결과도 그대로 넘겨 "답변 과정" 탭에서 왜 보류했는지 보이게 한다.
            "retrieved_contexts": contexts,
            "used_chunk_ids": [],
            "related_keywords": [],
            "citations": [],
            "clarification": None,
            "premise_correction": None,
        }

    # 같은 문서의 여러 조각 중 순위가 앞선 하나씩만, 최대 EVIDENCE_DOCUMENT_LIMIT개 문서.
    picked: list[dict] = []
    seen_documents: set[str] = set()
    for item in strong:
        key = item.get("document_id") or item["chunk_id"]
        if key in seen_documents:
            continue
        seen_documents.add(key)
        picked.append(item)
        if len(picked) >= EVIDENCE_DOCUMENT_LIMIT:
            break
    used = [item["chunk_id"] for item in picked]
    citations = list(picked)
    return {
        "response_type": "answered",
        "audience_level": audience_level,
        "message": (
            f"검색으로 찾은 근거 {len(picked)}건입니다. "
            "답변 문장 생성은 아직 연결되지 않아 검색된 원문을 그대로 보여 드립니다. "
            "어느 자료가 질문에 맞는지 직접 확인해 주세요."
        ),
        "retrieved_contexts": contexts,
        "used_chunk_ids": used,
        "related_keywords": [],
        "citations": citations,
        "clarification": None,
        "premise_correction": None,
    }


def answer(
    question: str, top_k: int = 5, audience_level: str = DEFAULT_AUDIENCE_LEVEL
) -> dict:
    """질문 하나를 받아 ServiceResponse까지 돌려준다."""
    return build_response(question, search(question, top_k=top_k), audience_level)
