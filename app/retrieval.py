"""화면과 RAG Service 사이의 얇은 연결 계층.

검색·근거판정·생성·Citation 조립은 `src/rag_service`의 RagService가 맡는다.
이 모듈은 설명 수준 상수와 실행 모드 판별, 그리고 호출 결과 전달만 담당한다.
"""

from __future__ import annotations

from typing import Any

import rag_client
from rag_client import (  # noqa: F401 - 화면에서 그대로 사용한다
    bm25_index_chunk_count,
    bm25_index_path,
    generation_mode,
    generation_model_id,
    is_live,
    missing_env,
    retrieval_mode,
)

REQUIRED_ENV = rag_client.REQUIRED_ENV
SOURCE_NAME = "한국민족문화대백과사전"

# 계약 0.3.0-draft: 내부 코드는 easy/general/advanced, UI 문구는 쉽게/일반/깊이 있게.
AUDIENCE_LEVELS = ("easy", "general", "advanced")
AUDIENCE_LABELS = {"easy": "쉽게 설명", "general": "일반 설명", "advanced": "깊이 있게"}
DEFAULT_AUDIENCE_LEVEL = "general"

# 화면에 적는 점수 이름. 임베딩 코사인 유사도이지 최종 순위 점수가 아니다.
SCORE_NAME = "의미 유사도"


def format_score(score: Any) -> str:
    """의미 유사도 표기. 잰 적이 없으면 `—`.

    낱말 검색으로만 올라온 조각은 유사도를 계산하지 않았다.
    없는 숫자를 0으로 적으면 가장 안 비슷한 것처럼 보이므로 비워 둔다.
    """
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return "—"
    return f"{score:.3f}"


def score_is_reference_only() -> bool:
    """화면 숫자가 순위를 설명하지 못하는 상태인지.

    하이브리드는 의미와 낱말 일치를 합쳐 순위를 정하는데 화면에 적는 숫자는
    의미 유사도뿐이다. 그래서 1위 숫자가 2·3위보다 낮게 보일 수 있다.
    숫자 옆에 그 사실을 붙이지 않으면 순위가 잘못된 것처럼 읽힌다.
    """
    return retrieval_mode() == "hybrid"


def score_caption() -> str:
    """점수 옆에 붙이는 설명 한 줄."""
    if score_is_reference_only():
        return (
            f"{SCORE_NAME}는 뜻이 얼마나 가까운지만 나타내는 **참고값**입니다. "
            "순위는 여기에 낱말 일치까지 더해 정하므로 숫자 순서와 다를 수 있습니다."
        )
    return f"{SCORE_NAME}가 높을수록 질문과 뜻이 가깝습니다. 순위는 이 값 순서입니다."


RETRIEVAL_LABELS = {
    "hybrid": "하이브리드 검색 (의미 + 단어)",
    "dense": "의미 검색 단독",
}


def retrieval_label() -> str:
    """이번 실행의 검색 방식 표기."""
    return RETRIEVAL_LABELS.get(retrieval_mode(), "알 수 없음")


def shift_level(level: str, step: int) -> str:
    """설명 수준을 한 단계 옮긴다. 양 끝에서는 그대로 둔다."""
    index = AUDIENCE_LEVELS.index(level) if level in AUDIENCE_LEVELS else 1
    return AUDIENCE_LEVELS[min(max(index + step, 0), len(AUDIENCE_LEVELS) - 1)]


def answer(
    question: str,
    *,
    audience_level: str = DEFAULT_AUDIENCE_LEVEL,
    interaction_id: str | None = None,
    clarification_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """RagService를 호출해 응답과 실행 추적을 함께 돌려준다.

    반환 형식은 `RagService.answer_with_trace()` 그대로다.
      {response, retrieved_contexts, used_chunk_ids, retrieval_top_k}
    """
    service = rag_client.build_service()
    return service.answer_with_trace(
        question,
        audience_level=audience_level,
        interaction_id=interaction_id,
        clarification_context=clarification_context,
    )
