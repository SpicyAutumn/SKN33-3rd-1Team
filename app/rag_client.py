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

REQUIRED_ENV = (
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "PINECONE_INDEX_NAME",
    "OLLAMA_BASE_URL",
)

# 로컬 BM25 인덱스. Pinecone과 달리 공용이 아니라 각자 만들어야 한다.
DEFAULT_BM25_INDEX_PATH = PROJECT_ROOT / "data" / "processed" / "aks_bm25_v1.sqlite3"

# [제거 예정] 생성이 붙으면 used_chunk_ids는 생성 결과가 정한다.
# 팀 결정(2026-09-01): 문서당 제한은 두지 않는다. 같은 문서의 여러 청크가
# 필요한 질문에서 검색이 살려 놓은 근거를 화면 직전에 버리지 않기 위해서다.
EVIDENCE_CHUNK_LIMIT = 3


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


def _is_unset(value: str) -> bool:
    """값이 비었거나 `.env.example`의 자리표시자 그대로인지.

    `OLLAMA_BASE_URL={{your_ollama_base_url}}`처럼 예시를 복사만 하고
    값을 바꾸지 않으면, 비어 있지 않으니 검사를 통과해 버린다. 그러면
    화면에는 연결됨으로 뜨고 질문할 때가 되어서야 접속 오류가 난다.
    """
    text = value.strip()
    return not text or (text.startswith("{{") and text.endswith("}}"))


def missing_env() -> list[str]:
    """비어 있거나 아직 채우지 않은 필수 환경 변수 이름 목록.

    값은 절대 반환하지 않는다.
    """
    load_env()
    return [name for name in REQUIRED_ENV if _is_unset(os.getenv(name, ""))]


def is_live() -> bool:
    return not missing_env()


def _score(context: dict[str, Any]) -> float | None:
    value = context.get("retrieval_score")
    return float(value) if isinstance(value, (int, float)) else None


def pick_evidence(contexts: list[dict[str, Any]], limit: int = EVIDENCE_CHUNK_LIMIT) -> list[dict[str, Any]]:
    """내용이 있는 조각을 검색 순서대로 고른다. 같은 문서인지는 보지 않는다.

    팀 결정(2026-09-01): 문서당 제한은 검색 단계에서 다룰 일이지 화면 직전에
    자를 일이 아니다. 같은 문서의 여러 청크가 필요한 질문이 있다.
    출처 카드는 `group_by_document()`가 문서 단위로 묶어 보여 준다.
    """
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for context in contexts:
        chunk_id = str(context.get("chunk_id") or "")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
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


# 이 서비스의 근거는 한국민족문화대백과사전 한 벌뿐이다. 아래 낱말이 묻는
# 값은 어느 시점의 백과사전에도 들어 있지 않다. 검색은 성공할 수 있어서
# 점수로는 걸러지지 않는다. `현대자동차㈜`도 `서울특별시`도 실제 항목이다.
NEVER_IN_SOURCE = (
    "주가", "시세", "환율", "코스피", "코스닥", "시가총액", "금리",
    "항공권", "예매", "맛집", "실시간",
    "파이썬", "자바스크립트", "코딩", "소스코드", "프로그래밍",
    "번역해", "레시피",
)

# 아래 낱말은 백과사전 표제어이기도 하다. `조선시대 날씨 기록`은 답할 수 있고,
# `강수`·`기온`은 전통 인물, `주식`은 고려 관직, `배송`은 불교 의례,
# `분양가 상한제`는 제도 항목이다. 지금을 묻는 표시가 함께 있을 때만 막는다.
LIVE_ONLY = ("날씨", "기온", "강수", "미세먼지", "주식", "가격", "배송", "분양가")
NOW_MARKERS = ("오늘", "지금", "현재", "요즘", "내일", "이번 주", "올해", "최신")

# 낱말 뒤에 이만큼 붙어도 같은 낱말로 본다. 조사와 흔한 종결·명령 어미다.
# 목록 밖의 글자가 붙으면 다른 낱말로 본다. `주가`와 `주가교`, `금리`와
# `금리자유화`를 가르는 것이 이 목록이다.
TERM_TAILS = frozenset((
    "", "은", "는", "이", "가", "을", "를", "의", "에", "에서", "에게",
    "으로", "로", "와", "과", "도", "만", "부터", "까지", "나", "이나",
    "라도", "처럼", "보다", "밖에", "조차", "마저", "요", "란", "이란",
    "야", "이야", "인가", "인가요", "인지", "입니까", "입니다", "냐", "니",
    "줘", "해줘", "주세요", "해주세요", "알려줘", "한다", "했다",
))

# 어절 양 끝에서 떼어 낼 문장 부호.
TERM_PUNCTUATION = "·,.?!\"'()[]{}<>「」『』…~-"


def mentions_term(question: str, terms: tuple[str, ...]) -> bool:
    """질문이 그 낱말을 실제로 말하고 있는지 본다.

    글자가 들어 있는지만 보면 안 된다. `중금리 삼층석탑`이 `금리`로,
    `권주가`가 `주가`로, `마마배송굿`이 `배송`으로, `강강수월래`가
    `강수`로 막혔다. 고분군·석탑·굿은 이 서비스의 한복판이다.

    그래서 어절 단위로 본다. 어절이 그 낱말로 시작하고, 뒤에 붙은 것이
    조사나 어미일 때만 같은 낱말로 친다. 막으려던 `현대자동차 주가`,
    `파이썬으로 코드 짜줘`는 그대로 막힌다.
    """
    for raw in str(question or "").split():
        word = raw.strip(TERM_PUNCTUATION)
        if not word:
            continue
        for term in terms:
            if word.startswith(term) and word[len(term):] in TERM_TAILS:
                return True
    return False


class TopicScopeChecker:
    """검색 전에 범위 밖 질문을 걸러낸다.

    범위 판정은 근거 충분성과 다른 문제다. `현대자동차 주가`는 검색이
    성공한다. 백과사전에 `현대자동차㈜` 항목이 실제로 있기 때문이다.
    그러면 생성기는 회사 연혁으로 답을 만들어 버린다. 물어본 것은 주가인데
    엉뚱한 것을 답하는 셈이다. `오늘 서울 날씨`는 더 나쁘다. `서울특별시`
    항목의 기후 설명을 근거 삼아 오늘 날씨를 지어냈다.

    여기서 막으면 검색도 생성도 하지 않으므로 지어낼 여지가 없다.

    복합 질문에서는 멀쩡한 질문을 막지 않는 쪽을 택했지만 여기서는 반대다.
    걸러진 질문은 자료에 답이 없어 어차피 답할 수 없고, 사용자는 다시
    물으면 된다. 반대로 놓치면 없는 사실을 지어낸다.
    """

    def is_in_scope(self, question: str) -> bool:
        if mentions_term(question, NEVER_IN_SOURCE):
            return False
        if mentions_term(question, LIVE_ONLY) and mentions_term(question, NOW_MARKERS):
            return False
        return True


class ContentEvidenceChecker:
    """[제거 예정] 내용이 있으면 통과시키고, 생성기가 부족하다고 하면 그 판단을 따른다.

    점수나 규칙만으로는 그 조각이 질문에 답하는지 알 수 없다. 실제로 판단할 수
    있는 것은 근거를 읽는 생성기뿐이다. 그래서 처음에는 통과시켜 생성기가 보게
    하고, 같은 질문·같은 근거로 다시 물어오면 그 판단을 따른다. RagService는
    생성기가 `insufficient_evidence`를 낸 경우에만 다시 물어본다.

    그냥 늘 통과시키면 RagService가 판정기와 생성기의 불일치를 오류로 보고
    `generator rejected evidence that passed the service grounding policy`를
    던진다. 범위 밖 질문에서는 반드시 그렇게 된다.

    실제 EvidenceChecker가 준비되면 이 클래스를 지운다.
    """

    def __init__(self) -> None:
        self._approved: tuple[str, tuple[str, ...]] | None = None

    def begin_request(self) -> None:
        """새 요청이 시작됐다. 지난 요청의 판단은 버린다.

        이 상태는 한 요청 안에서 RagService가 같은 근거로 두 번 물어볼 때만
        쓰라고 둔 것이다. 요청 사이에 남겨 두면 같은 질문을 두 번째 할 때
        곧바로 `insufficient`가 나와 멀쩡한 답변이 막힌다. 설명 수준만
        바꿔 다시 물어도 마찬가지다. 서비스 객체는 캐시되어 계속 살아 있다.
        """
        self._approved = None

    def decide(self, question: str, contexts: list[dict[str, Any]]) -> str:
        usable = [c for c in contexts if str(c.get("content", "")).strip()]
        if not usable:
            self._approved = None
            return "insufficient"

        key = (question, tuple(str(c.get("chunk_id", "")) for c in usable))
        if self._approved == key:
            # 생성기가 이 근거로는 답할 수 없다고 했다. 그 판단이 더 정확하다.
            self._approved = None
            return "insufficient"

        self._approved = key
        return "sufficient"


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
        usable = [c for c in contexts if str(c.get("content", "")).strip()]
        picked = pick_evidence(usable)
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


class CompoundAwareGenerator:
    """복합 질문 팀 규칙을 먼저 적용하고 단일 질문만 실제 생성기로 보낸다."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("clarification_context") is None and is_compound(request["question"]):
            return EvidencePassthroughGenerator()._clarification_result(request)
        return self.delegate.invoke(request)


def bm25_index_path() -> Path:
    """로컬 BM25 인덱스 위치. `AKS_BM25_INDEX_PATH`로 덮어쓸 수 있다."""
    load_env()
    override = os.getenv("AKS_BM25_INDEX_PATH", "").strip()
    return Path(override) if override else DEFAULT_BM25_INDEX_PATH


def retrieval_mode() -> str:
    """이번 실행이 쓰는 검색 방식. `hybrid` 또는 `dense`."""
    return "hybrid" if bm25_index_path().is_file() else "dense"


def generation_model() -> str:
    """답변을 만드는 모델 이름.

    화면 문구에 이름을 박아 두면 모델이 바뀔 때마다 어긋난다. 실제로 Qwen에서
    exaone으로 바뀌었을 때 화면만 옛 이름을 붙들고 있었다. `.env`에서 읽는다.
    """
    load_env()
    return os.getenv("OLLAMA_MODEL", "").strip() or "미설정"


def bm25_index_chunk_count() -> int | None:
    """BM25 인덱스에 든 조각 수. 인덱스가 없거나 읽을 수 없으면 `None`.

    전체 말뭉치의 일부만 넣은 인덱스로도 검색은 된다. 그러면 낱말 검색이
    닿지 못하는 문서가 생기는데 화면에는 아무 차이가 안 보인다.
    그래서 조각 수를 읽어 파이프라인 탭에 그대로 띄운다.
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


class HybridWithSimilarity:
    """하이브리드로 순위를 정하고, 점수는 코사인 유사도를 그대로 돌려준다.

    RRF 점수는 순위를 합치기 위한 장치라 그 자체로는 읽을 뜻이 없다.
    기본 가중치에서 최댓값이 0.041이라 화면에 띄우면 `0.0397` 같은 숫자가
    나오는데, 팀의 다른 검색 결과는 모두 `0.4~0.5`대 유사도를 보여 준다.
    같은 대상을 두고 자릿수가 다른 숫자를 보면 비교가 불가능하다.

    그래서 순위만 하이브리드에서 가져오고, 점수는 융합 전 밀집 검색이
    매긴 유사도를 되살려 넣는다. 낱말 검색으로만 올라온 조각은 유사도를
    잰 적이 없으므로 계약대로 `score_type="unknown"`으로 둔다.
    """

    def __init__(self, dense, bm25, **options) -> None:
        from rag_indexing.hybrid_retriever import HybridRetriever

        self.dense = dense
        self.hybrid = HybridRetriever(dense, bm25, **options)

    def search(self, question: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        candidate_k = max(top_k, self.hybrid.candidate_k)
        candidates = self.dense.search(question, top_k=candidate_k)
        similarity = {
            str(c["chunk_id"]): c.get("retrieval_score")
            for c in candidates
            if str(c.get("score_type", "")) == "similarity"
        }
        fused = self.hybrid.search_from_dense_results(question, candidates, top_k=top_k)
        for item in fused:
            score = similarity.get(str(item["chunk_id"]))
            item["retrieval_score"] = score
            item["score_type"] = "similarity" if score is not None else "unknown"
        return fused


def build_retriever():
    """BM25 인덱스가 있으면 하이브리드, 없으면 Pinecone 단독으로 검색한다.

    BM25 인덱스는 Pinecone과 달리 공용이 아니라 각자 로컬에서 만들어야 한다
    (`scripts/build_aks_bm25.py`). 인덱스가 없다고 화면이 죽으면 아직 만들지
    않은 사람은 아무것도 볼 수 없으므로, 없으면 조용히 단독 검색으로 내린다.
    어느 쪽으로 검색했는지는 파이프라인 탭에 그대로 표시한다.
    """
    from rag_indexing.pinecone_store import PineconeRetriever

    dense = PineconeRetriever()
    path = bm25_index_path()
    if not path.is_file():
        return dense

    from rag_indexing.bm25_store import BM25Retriever

    return HybridWithSimilarity(dense, BM25Retriever(path))


def build_service():
    """RagService를 조립한다. 키가 없으면 RuntimeError."""
    absent = missing_env()
    if absent:
        raise RuntimeError(f"환경 변수 미설정: {', '.join(absent)}")

    from rag_service.ollama_generator import OllamaGenerator
    from rag_service.service import RagService

    return RagService(
        retriever=build_retriever(),
        generator=CompoundAwareGenerator(OllamaGenerator()),
        evidence_checker=ContentEvidenceChecker(),
        scope_checker=TopicScopeChecker(),
    )
