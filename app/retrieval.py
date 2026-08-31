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


def normalize_context(context: dict) -> dict:
    """검색 결과를 계약 0.3.0-draft 형식으로 맞춘다.

    [제거 예정] `pinecone_store.search()`가 0.3.0에 맞게 수정되면 이 함수는
    그대로 통과만 시키게 되므로 호출부에서 빼면 된다.
    현재 `search()`는 `source`를 반환하고 `page`를 아직 포함한다.
    """
    normalized = dict(context)
    if "source_url" not in normalized:
        normalized["source_url"] = normalized.get("source")
    normalized.pop("source", None)
    normalized.pop("page", None)
    return normalized


def search(question: str, top_k: int = 5) -> list[dict]:
    """실제 Pinecone 검색. 키가 없으면 RuntimeError."""
    absent = missing_env()
    if absent:
        raise RuntimeError(f"환경 변수 미설정: {', '.join(absent)}")

    from rag_indexing.pinecone_store import PineconeRetriever

    results = PineconeRetriever().search(question, top_k=top_k)
    return [normalize_context(item) for item in results]


def build_response(
    question: str, contexts: list[dict], audience_level: str = DEFAULT_AUDIENCE_LEVEL
) -> dict:
    """검색 결과로 ServiceResponse를 조립한다.

    답변 생성(Track B)이 아직 없으므로 문장을 지어내지 않는다.
    근거가 있으면 근거만 보여주고, 없으면 보류로 처리한다.
    """
    if not contexts:
        return {
            "response_type": "insufficient_evidence",
            "audience_level": audience_level,
            "message": (
                "현재 검색된 공식 자료만으로는 이 질문을 확인하기 어렵습니다. "
                "확인 가능한 다른 문화유산 관련 질문을 해 주세요."
            ),
            "retrieved_contexts": [],
            "used_chunk_ids": [],
            "related_keywords": [],
            "citations": [],
            "clarification": None,
            "premise_correction": None,
        }

    used = [contexts[0]["chunk_id"]]
    citations = [item for item in contexts if item["chunk_id"] in used]
    return {
        "response_type": "answered",
        "audience_level": audience_level,
        "message": (
            "아래 근거를 실제 검색으로 찾았습니다. "
            "답변 문장 생성은 아직 연결되지 않아 검색된 원문을 그대로 보여 드립니다."
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
