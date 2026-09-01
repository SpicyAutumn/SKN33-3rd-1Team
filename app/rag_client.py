"""화면에서 쓰는 RAG Service 조립.

검색·근거판정·생성·Citation 조립은 모두 `src/rag_service`의 RagService가 맡는다.
아직 구현되지 않은 생성 컴포넌트와 근거 판정기는 이 파일의 임시 구현으로 채운다.
계약 인터페이스를 그대로 따르므로 실제 구현이 나오면 여기만 교체하면 된다.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

REQUIRED_ENV = ("OPENAI_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME")

# 로컬 BM25 인덱스. Pinecone과 달리 공용이 아니라 각자 만들어야 한다.
DEFAULT_BM25_INDEX_PATH = PROJECT_ROOT / "data" / "processed" / "aks_bm25_v1.sqlite3"

# [제거 예정] 근거 충분성 판정은 생성·평가 담당의 EvidenceChecker가 맡는다.
# 그 구현이 나오기 전까지 화면이 무엇도 답하지 못하는 상태를 막기 위한 임시값이다.
# 값 근거: 범위 안 질문 최저 0.440, 범위 밖 질문 최고 0.335 (2026-08-31 실측)
TEMP_EVIDENCE_MIN_SCORE = 0.40

# 위 기준선을 적용해도 되는 점수 종류. 이 외의 척도는 비교하지 않고 통과시킨다.
THRESHOLD_SCORE_TYPE = "similarity"

# [제거 예정] 생성이 붙으면 used_chunk_ids는 생성 결과가 정한다.
EVIDENCE_DOCUMENT_LIMIT = 3


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
    return not missing_env()


def _score(context: dict[str, Any]) -> float | None:
    value = context.get("retrieval_score")
    return float(value) if isinstance(value, (int, float)) else None


def is_threshold_comparable(context: dict[str, Any]) -> bool:
    """이 조각의 점수를 기준선과 견줘도 되는지 판단한다.

    기준선 0.40은 코사인 유사도(`similarity`)를 재서 정한 값이다.
    하이브리드 검색이 돌려주는 RRF 점수(`relevance`)는 척도가 완전히 달라
    이론상 최댓값이 0.041뿐이므로, 같은 값을 들이대면 모든 조각이 미달이 되어
    어떤 질문에도 답하지 못하는 상태가 된다.
    """
    return str(context.get("score_type", "")).strip() == THRESHOLD_SCORE_TYPE


def meets_threshold(context: dict[str, Any], min_score: float = TEMP_EVIDENCE_MIN_SCORE) -> bool:
    """기준선 판정 한 곳.

    점수 척도가 다르거나 점수가 없으면 판단 불가로 보고 통과시킨다.
    `0.0`은 실제 점수이므로 `or` 대신 `is None`으로 구분한다.
    화면·근거 판정·근거 선택이 모두 이 함수를 쓴다.
    """
    if not is_threshold_comparable(context):
        return True
    score = _score(context)
    return score is None or score >= min_score


def pick_documents(contexts: list[dict[str, Any]], limit: int = EVIDENCE_DOCUMENT_LIMIT) -> list[dict[str, Any]]:
    """서로 다른 문서를 순위 순으로 고른다. 같은 문서의 조각은 앞선 하나만 쓴다."""
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for context in contexts:
        key = str(context.get("document_id") or context.get("chunk_id") or "")
        if key in seen:
            continue
        seen.add(key)
        picked.append(context)
        if len(picked) >= limit:
            break
    return picked


# [제거 예정] 복합 질문 처리. 팀 합의(2026-09-01)는 여러 질문을 한 번에 받으면
# 나눠서 답하지 않고 하나만 물어봐 달라고 되돌려주는 것이다.
# 계약의 needs_clarification을 그대로 쓰므로 새 응답 유형은 만들지 않는다.
COMPOUND_REASON_CODE = "compound_question"
_COMPOUND_LIST_MIN_ITEMS = 3


def split_questions(question: str) -> list[str]:
    """한 번에 들어온 여러 질문을 나눈다. 복합 질문이 아니면 빈 목록.

    잘못 걸러내면 멀쩡한 질문을 막게 되므로 확실한 신호만 본다.
    `창덕궁과 덕수궁은 같은 궁궐이야?`처럼 대상이 둘이어도 묻는 것이
    하나면 복합 질문으로 보지 않는다.
    """
    text = question.strip()
    if not text:
        return []

    # 신호 1: 물음표가 둘 이상이다. 나뉜 조각이 그대로 독립된 질문이 된다.
    if len(re.findall(r"[?？]", text)) >= 2:
        parts = [part.strip() for part in re.split(r"[?？]", text) if part.strip()]
        if len(parts) >= 2:
            return [f"{part}?" for part in parts]

    # 쉼표 나열(신호 2)은 복합 질문으로 보되 선택지는 만들지 않는다.
    # `경복궁의 건립 시기, 만든 사람, 주요 건물…`의 뒤쪽 조각에는 주어가 없어
    # 그대로 버튼에 올리면 혼자서는 뜻이 통하지 않는 질문이 된다.
    return []


def is_compound(question: str) -> bool:
    """여러 질문이 한 번에 들어왔는지."""
    text = question.strip()
    if len(re.findall(r"[?？]", text)) >= 2:
        return len([p for p in re.split(r"[?？]", text) if p.strip()]) >= 2
    items = [item.strip(" ·,、") for item in re.split(r"[,、·]", text)]
    return len([item for item in items if item]) >= _COMPOUND_LIST_MIN_ITEMS


def compound_clarification(question: str) -> dict[str, Any]:
    """복합 질문에 되돌려줄 확인 요청. 계약의 clarification 형식 그대로."""
    options = [
        {"id": f"part-{index}", "label": part, "source_chunk_ids": []}
        for index, part in enumerate(split_questions(question)[:3], start=1)
    ]
    return {
        "reason_code": COMPOUND_REASON_CODE,
        "question": (
            "한 번에 여러 가지를 물어보셨습니다. "
            "지금은 입력 전체를 하나의 질문으로 검색해서 일부 근거가 빠질 수 있습니다. "
            "하나만 골라 다시 물어봐 주세요."
        ),
        "options": options,
    }


class ScoreEvidenceChecker:
    """[제거 예정] 유사도만 보는 임시 근거 판정기.

    점수만으로는 그 조각이 질문에 답하는지 증명할 수 없다. 실제 판정기가
    준비되면 이 클래스를 지우고 RagService에 그 구현을 넘긴다.
    """

    def __init__(self, min_score: float = TEMP_EVIDENCE_MIN_SCORE) -> None:
        self.min_score = min_score

    def decide(self, question: str, contexts: list[dict[str, Any]]) -> str:
        return "sufficient" if any(meets_threshold(c, self.min_score) for c in contexts) else "insufficient"


class EvidencePassthroughGenerator:
    """[제거 예정] 답변 문장을 만들지 않고 검색 근거만 그대로 넘기는 임시 생성기.

    생성 담당의 구현이 나오면 이 클래스를 지우고 그 컴포넌트를 넘긴다.
    근거 밖 문장을 지어내지 않는 것이 이 임시 구현의 유일한 규칙이다.
    """

    def _clarification_result(self, request: dict[str, Any]) -> dict[str, Any]:
        """복합 질문에 되돌려줄 결과. 계약상 근거를 인용하면 안 된다."""
        return {
            "schema_version": request["schema_version"],
            "request_id": request["request_id"],
            "interaction_id": request["interaction_id"],
            "candidate_response_type": "needs_clarification",
            "draft_message": "한 번에 하나씩 물어봐 주세요.",
            "audience_level": request["audience_level"],
            "used_chunk_ids": [],
            "clarification": compound_clarification(request["question"]),
            "premise_correction": None,
            "related_topic_candidates": [],
            "generation_metadata": {
                "prompt_version": "track-c-passthrough",
                "model_id": None,
                "temperature": None,
                "finish_reason": None,
                "latency_ms": None,
                "token_usage": None,
            },
        }

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        contexts = request["retrieved_contexts"]
        # 복합 질문은 나눠서 답하지 않고 하나만 물어봐 달라고 되돌려준다.
        if request.get("clarification_context") is None and is_compound(request["question"]):
            return self._clarification_result(request)
        # 근거 판정이 통과시킨 검색이라도, 기준선에 못 미치는 개별 조각은 근거로 쓰지 않는다.
        usable = [c for c in contexts if str(c.get("content", "")).strip() and meets_threshold(c)]
        picked = pick_documents(usable)
        message = (
            f"검색으로 찾은 근거 {len(picked)}건입니다. "
            "답변 문장 생성은 아직 연결되지 않아 검색된 원문을 그대로 보여 드립니다. "
            "어느 자료가 질문에 맞는지 직접 확인해 주세요."
        )
        return {
            "schema_version": request["schema_version"],
            "request_id": request["request_id"],
            "interaction_id": request["interaction_id"],
            "candidate_response_type": "answered",
            "draft_message": message,
            "audience_level": request["audience_level"],
            "used_chunk_ids": [item["chunk_id"] for item in picked],
            "clarification": None,
            "premise_correction": None,
            "related_topic_candidates": [],
            "generation_metadata": {
                "prompt_version": "track-c-passthrough",
                "model_id": None,
                "temperature": None,
                "finish_reason": None,
                "latency_ms": None,
                "token_usage": None,
            },
        }


def bm25_index_path() -> Path:
    """로컬 BM25 인덱스 위치. `AKS_BM25_INDEX_PATH`로 덮어쓸 수 있다."""
    load_env()
    override = os.getenv("AKS_BM25_INDEX_PATH", "").strip()
    return Path(override) if override else DEFAULT_BM25_INDEX_PATH


def retrieval_mode() -> str:
    """이번 실행이 쓰는 검색 방식. `hybrid` 또는 `dense`."""
    return "hybrid" if bm25_index_path().is_file() else "dense"


def bm25_index_chunk_count() -> int | None:
    """BM25 인덱스에 든 조각 수. 인덱스가 없거나 읽을 수 없으면 `None`.

    전체 말뭉치의 일부만 넣은 인덱스로도 검색은 된다. 그러면 낱말 검색이
    닿지 못하는 문서가 생기는데 화면에는 아무 차이가 안 보인다.
    그래서 조각 수를 읽어 공정 견학 탭에 그대로 띄운다.
    """
    path = bm25_index_path()
    if not path.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT value FROM index_info WHERE key = 'chunk_count'"
            ).fetchone()
    except sqlite3.Error:
        return None
    try:
        return int(row[0]) if row else None
    except (TypeError, ValueError):
        return None


def build_retriever():
    """BM25 인덱스가 있으면 하이브리드, 없으면 Pinecone 단독으로 검색한다.

    BM25 인덱스는 Pinecone과 달리 공용이 아니라 각자 로컬에서 만들어야 한다
    (`scripts/build_aks_bm25.py`). 인덱스가 없다고 화면이 죽으면 아직 만들지
    않은 사람은 아무것도 볼 수 없으므로, 없으면 조용히 단독 검색으로 내린다.
    어느 쪽으로 검색했는지는 공정 견학 탭에 그대로 표시한다.
    """
    from rag_indexing.pinecone_store import PineconeRetriever

    dense = PineconeRetriever()
    path = bm25_index_path()
    if not path.is_file():
        return dense

    from rag_indexing.bm25_store import BM25Retriever
    from rag_indexing.hybrid_retriever import HybridRetriever

    return HybridRetriever(dense, BM25Retriever(path))


def build_service():
    """RagService를 조립한다. 키가 없으면 RuntimeError."""
    absent = missing_env()
    if absent:
        raise RuntimeError(f"환경 변수 미설정: {', '.join(absent)}")

    from rag_service.service import RagService

    return RagService(
        retriever=build_retriever(),
        generator=EvidencePassthroughGenerator(),
        evidence_checker=ScoreEvidenceChecker(),
    )
