"""화면과 RAG Service 사이의 얇은 연결 계층.

검색·근거판정·생성·Citation 조립은 `src/rag_service`의 RagService가 맡는다.
이 모듈은 설명 수준 상수와 실행 모드 판별, 그리고 호출 결과 전달만 담당한다.
"""

from __future__ import annotations

from typing import Any

import rag_client
from rag_client import (  # noqa: F401 - 화면에서 그대로 사용한다
    is_live,
    is_threshold_comparable,
    meets_threshold,
    missing_env,
)

REQUIRED_ENV = rag_client.REQUIRED_ENV
SOURCE_NAME = "한국민족문화대백과사전"

# 계약 0.3.0-draft: 내부 코드는 easy/general/advanced, UI 문구는 쉽게/일반/깊이 있게.
AUDIENCE_LEVELS = ("easy", "general", "advanced")
AUDIENCE_LABELS = {"easy": "쉽게 설명", "general": "일반 설명", "advanced": "깊이 있게"}
DEFAULT_AUDIENCE_LEVEL = "general"

# [제거 예정] 임시 근거 판정기가 쓰는 기준선. 화면에서 통과·탈락을 설명하는 데만 쓴다.
# 실제 EvidenceChecker가 붙으면 이 값과 관련 표시를 함께 걷어낸다.
EVIDENCE_MIN_SCORE = rag_client.TEMP_EVIDENCE_MIN_SCORE


def threshold_applies(contexts: list[dict[str, Any]]) -> bool:
    """이번 검색 결과에 기준선을 적용했는지.

    검색기가 바뀌어 점수 척도가 달라지면 기준선은 뜻을 잃는다.
    그때 화면에 `기준선 0.40`을 그대로 띄우면 틀린 설명이 되므로 여기서 걸러낸다.
    """
    return any(is_threshold_comparable(c) for c in contexts)


def score_label(contexts: list[dict[str, Any]]) -> str:
    """점수 종류에 맞는 화면 표기. 하이브리드 검색은 유사도가 아니다."""
    return "유사도" if threshold_applies(contexts) else "관련도"


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
