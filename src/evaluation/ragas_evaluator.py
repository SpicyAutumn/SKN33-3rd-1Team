"""RAGAS로 현재 RAG 응답의 답변 품질 지표를 계산한다.

context_precision과 context_recall은 검색 층 지표이고 계산에 정답 라벨이
필요하다. 기준 답안이 없는 임의 질문에서는 값이 나오지 않아 화면에서
제외하기로 하여, 여기서는 답변 층 지표 두 가지만 계산한다.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import sys
import types
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_PATH = (
    PROJECT_ROOT / "data" / "evaluation" / "aks_ragas_dev_reference_v1.jsonl"
)
METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
)
DEFAULT_JUDGE_MODEL = "gpt-4.1-mini-2025-04-14"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_API_TIMEOUT_SECONDS = 30.0
DEFAULT_METRIC_TIMEOUT_SECONDS = 60.0
DEFAULT_JUDGE_MAX_TOKENS = 4096
ANSWER_RELEVANCY_PROMPT_VERSION = "same-language-v1"

SAME_LANGUAGE_ANSWER_RELEVANCY_INSTRUCTION = """\
중요 언어 규칙:
- 생성하는 question은 입력 response와 반드시 같은 언어로 작성하세요.
- response가 한국어이면 question도 자연스러운 한국어로 작성하세요.
- 영어 예시는 출력 언어를 정하는 기준이 아닙니다.
- response의 표현을 다른 언어의 비슷한 철자나 다른 뜻으로 오해하지 마세요.

아래의 기존 Answer Relevancy 평가 절차와 출력 형식은 그대로 따르세요.
"""


class RagasEvaluationError(RuntimeError):
    """사용자 화면에 안전한 문구로 바꿔 표시할 RAGAS 초기화 오류."""


def _same_language_answer_relevancy_prompt(prompt: str) -> str:
    """RAGAS 공식 역질문 프롬프트 앞에 동일 언어 규칙만 추가한다.

    원래 질문을 알려 주면 생성 질문이 원문을 베껴 유사도가 부풀 수 있으므로,
    평가 대상 답변에 포함된 언어만 판단하도록 원래 질문은 추가하지 않는다.
    """
    return f"{SAME_LANGUAGE_ANSWER_RELEVANCY_INSTRUCTION}\n{prompt}"


def _wrap_same_language_answer_relevancy_llm(
    delegate: Any,
    instructor_base_type: type,
) -> Any:
    """공식 AnswerRelevancy 계산은 유지하고 LLM 입력 프롬프트만 보강한다."""

    class SameLanguageAnswerRelevancyLLM(instructor_base_type):
        def generate(self, prompt: str, response_model: type) -> Any:
            return delegate.generate(
                _same_language_answer_relevancy_prompt(prompt),
                response_model,
            )

        async def agenerate(self, prompt: str, response_model: type) -> Any:
            return await delegate.agenerate(
                _same_language_answer_relevancy_prompt(prompt),
                response_model,
            )

    return SameLanguageAnswerRelevancyLLM()


def find_reference_record(
    question: str,
    *,
    path: Path = DEFAULT_REFERENCE_PATH,
    approved_only: bool = True,
) -> dict[str, Any] | None:
    """질문과 정확히 일치하는 기준 답안을 찾는다.

    새로 만든 기준 답안은 별도 검수를 받아야 하므로 기본값에서는
    ``review_status=approved``인 행만 공식 기준 답안으로 인정한다.
    """
    normalized_question = question.strip()
    if not normalized_question or not path.is_file():
        return None

    with path.open(encoding="utf-8-sig") as file:
        for line_number, raw_line in enumerate(file, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise RagasEvaluationError(
                    f"기준 답안 파일 {path.name}:{line_number}의 JSON 형식이 잘못되었습니다."
                ) from error
            if str(record.get("question", "")).strip() != normalized_question:
                continue
            if approved_only and record.get("review_status") != "approved":
                return None
            reference = record.get("reference")
            if not isinstance(reference, str) or not reference.strip():
                return None
            return record
    return None


def prepare_retrieved_contexts(contexts: list[dict[str, Any]]) -> list[str]:
    """검색 결과를 RAGAS가 받는 순위 순 ``list[str]``로 바꾼다."""

    def rank(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, context = item
        value = context.get("retrieval_rank")
        if isinstance(value, int) and not isinstance(value, bool):
            return value, index
        return 10_000 + index, index

    prepared: list[str] = []
    for _, context in sorted(enumerate(contexts), key=rank):
        content = context.get("content")
        if isinstance(content, str) and content.strip():
            prepared.append(content.strip())
    return prepared


def evaluation_cache_key(
    *,
    question: str,
    response: str,
    contexts: list[dict[str, Any]],
    reference: str | None,
) -> str:
    """질문·답변·검색 결과가 같을 때 평가 API 재호출을 막는 키."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    payload = {
        "question": question.strip(),
        "response": response.strip(),
        "contexts": prepare_retrieved_contexts(contexts),
        "reference": reference,
        "judge_model": os.getenv("RAGAS_JUDGE_MODEL")
        or os.getenv("OPENAI_CHAT_MODEL")
        or DEFAULT_JUDGE_MODEL,
        "embedding_model": os.getenv("RAGAS_EMBEDDING_MODEL")
        or os.getenv("OPENAI_EMBEDDING_MODEL")
        or DEFAULT_EMBEDDING_MODEL,
        "ragas_version": "0.4.3",
        "answer_relevancy_prompt_version": ANSWER_RELEVANCY_PROMPT_VERSION,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluate_response(
    *,
    question: str,
    response: str,
    contexts: list[dict[str, Any]],
    reference: str | None = None,
) -> dict[str, Any]:
    """계산 가능한 지표를 실행하고 지표별 성공·불가·실패 상태를 반환한다.

    ``reference``는 현재 어떤 지표에도 쓰이지 않는다. 이 값을 쓰던
    context_recall이 빠졌지만, 화면과 캐시 키가 아직 전달하고 있어
    호출부를 깨뜨리지 않도록 인자만 유지한다.
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    judge_model = (
        os.getenv("RAGAS_JUDGE_MODEL", "").strip()
        or os.getenv("OPENAI_CHAT_MODEL", "").strip()
        or DEFAULT_JUDGE_MODEL
    )
    embedding_model = (
        os.getenv("RAGAS_EMBEDDING_MODEL", "").strip()
        or os.getenv("OPENAI_EMBEDDING_MODEL", "").strip()
        or DEFAULT_EMBEDDING_MODEL
    )

    if not api_key or api_key.startswith("{{"):
        raise RagasEvaluationError("OPENAI_API_KEY가 설정되지 않았습니다.")
    if judge_model.startswith("{{"):
        judge_model = DEFAULT_JUDGE_MODEL

    prepared_contexts = prepare_retrieved_contexts(contexts)
    return _run_async(
        _evaluate_async(
            question=question.strip(),
            response=response.strip(),
            retrieved_contexts=prepared_contexts,
            api_key=api_key,
            judge_model=judge_model,
            embedding_model=embedding_model,
        )
    )


def _run_async(coroutine: Any) -> dict[str, Any]:
    """일반 Streamlit 실행과 이미 이벤트 루프가 있는 환경을 모두 지원한다."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    # Jupyter처럼 현재 스레드에 이벤트 루프가 이미 있으면 별도 스레드에서 실행한다.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


async def _evaluate_async(
    *,
    question: str,
    response: str,
    retrieved_contexts: list[str],
    api_key: str,
    judge_model: str,
    embedding_model: str,
) -> dict[str, Any]:
    started = perf_counter()
    metric_results = {
        name: _not_applicable("평가 입력이 부족합니다.") for name in METRIC_NAMES
    }

    _install_ragas_vertexai_import_compat()
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import InstructorBaseRagasLLM, llm_factory
        from ragas.metrics.collections import AnswerRelevancy, Faithfulness
    except ImportError as error:
        # 미설치뿐 아니라 버전 불일치로 심볼이 사라진 경우도 여기로 들어온다.
        # 어느 쪽인지 구분할 수 있도록 원래 import 오류를 그대로 보여 준다.
        logger.error("RAGAS import failed", exc_info=error)
        raise RagasEvaluationError(
            f"RAGAS 평가 모듈을 불러오지 못했습니다: {error}. "
            "requirements.txt의 버전 조합으로 다시 설치해 주세요."
        ) from error

    api_timeout = _positive_float_env(
        "RAGAS_API_TIMEOUT_SECONDS", DEFAULT_API_TIMEOUT_SECONDS
    )
    metric_timeout = _positive_float_env(
        "RAGAS_METRIC_TIMEOUT_SECONDS", DEFAULT_METRIC_TIMEOUT_SECONDS
    )
    judge_max_tokens = _positive_int_env(
        "RAGAS_JUDGE_MAX_TOKENS", DEFAULT_JUDGE_MAX_TOKENS
    )
    llm_client = AsyncOpenAI(
        api_key=api_key,
        timeout=api_timeout,
        max_retries=1,
    )
    # AnswerRelevancy.ascore는 embeddings의 aembed_text/aembed_texts를 await
    # 하므로 임베딩 클라이언트도 비동기여야 한다. 동기 OpenAI를 넘기면
    # "Cannot use aembed_text() with a synchronous client"로 실패한다.
    # 다만 LLM과 HTTP 연결 풀을 공유하면 WriteTimeout이 날 수 있어
    # 같은 비동기 클라이언트를 재사용하지 않고 별도 인스턴스를 만든다.
    embedding_client = AsyncOpenAI(
        api_key=api_key,
        timeout=api_timeout,
        max_retries=1,
    )
    evaluator_llm = llm_factory(
        judge_model,
        provider="openai",
        client=llm_client,
        max_tokens=judge_max_tokens,
        temperature=0.0,
    )
    answer_relevancy_llm = _wrap_same_language_answer_relevancy_llm(
        evaluator_llm,
        InstructorBaseRagasLLM,
    )
    evaluator_embeddings = embedding_factory(
        "openai",
        model=embedding_model,
        client=embedding_client,
    )

    jobs: dict[str, Any] = {}
    if response and retrieved_contexts:
        jobs["faithfulness"] = Faithfulness(llm=evaluator_llm).ascore(
            user_input=question,
            response=response,
            retrieved_contexts=retrieved_contexts,
        )
    elif not retrieved_contexts:
        metric_results["faithfulness"] = _not_applicable("검색 문맥이 없습니다.")

    if question and response:
        jobs["answer_relevancy"] = AnswerRelevancy(
            # 점수 계산은 RAGAS 0.4.3의 공식 AnswerRelevancy를 그대로
            # 사용하고, 역질문 생성 언어만 답변과 동일하게 고정한다.
            llm=answer_relevancy_llm,
            embeddings=evaluator_embeddings,
        ).ascore(
            user_input=question,
            response=response,
        )

    if jobs:
        names = list(jobs)
        completed = await asyncio.gather(
            *(
                asyncio.wait_for(job, timeout=metric_timeout)
                for job in jobs.values()
            ),
            return_exceptions=True,
        )
        for name, result in zip(names, completed, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "RAGAS metric failed: %s",
                    name,
                    exc_info=(type(result), result, result.__traceback__),
                )
                metric_results[name] = {
                    "score": None,
                    "status": "failed",
                    "message": "평가 호출 실패",
                }
                continue
            value = (
                float(result)
                if isinstance(result, (int, float))
                else float(result.value)
            )
            if not math.isfinite(value):
                metric_results[name] = {
                    "score": None,
                    "status": "failed",
                    "message": "유효한 점수를 받지 못했습니다.",
                }
                continue
            metric_results[name] = {
                "score": value,
                "status": "completed",
                "message": None,
            }

    return {
        "status": "completed",
        "metrics": metric_results,
        "judge_model": judge_model,
        "embedding_model": embedding_model,
        "elapsed_ms": round((perf_counter() - started) * 1000),
    }


def _not_applicable(message: str) -> dict[str, Any]:
    return {"score": None, "status": "not_applicable", "message": message}


def _positive_float_env(name: str, default: float) -> float:
    """양수 환경 변수만 허용하고 잘못된 값은 안전한 기본값으로 돌린다."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_int_env(name: str, default: int) -> int:
    """양의 정수 환경 변수만 허용하고 잘못된 값은 안전한 기본값으로 돌린다."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _install_ragas_vertexai_import_compat() -> None:
    """RAGAS가 하드 import하는, 이미 삭제된 VertexAI 모듈 자리를 채운다.

    ragas 0.4.3의 ``ragas/llms/base.py``는 여전히
    ``langchain_community.chat_models.vertexai``를 import하지만, 이 모듈은
    langchain-community 0.4.x에서 제거되었다. 이 자리를 채우지 않으면
    ``import ragas`` 자체가 ModuleNotFoundError로 실패한다.

    ``langchain-google-vertexai``를 설치해도 해결되지 않는다. 그 패키지는
    ``langchain_google_vertexai``라는 다른 네임스페이스를 제공할 뿐이며,
    ragas는 이를 참조하지 않는다(설치 후 실측으로 확인).
    같은 파일의 ``langchain_community.llms.VertexAI``는 아직 존재하므로
    chat_models 쪽만 채우면 된다.

    이 프로젝트의 평가기는 OpenAI provider만 사용하므로 실제 VertexAI
    구현을 대신하지 않고 타입 확인용 자리만 제공한다.
    """
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return
    try:
        __import__(module_name)
        return
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise

    compatibility_module = types.ModuleType(module_name)
    compatibility_module.ChatVertexAI = type("ChatVertexAI", (), {})
    sys.modules[module_name] = compatibility_module
