import json
from pathlib import Path

from evaluation.ragas_evaluator import (
    _positive_float_env,
    _positive_int_env,
    _same_language_answer_relevancy_prompt,
    _wrap_same_language_answer_relevancy_llm,
    evaluation_cache_key,
    find_reference_record,
    prepare_retrieved_contexts,
)


def test_positive_float_env_uses_valid_value_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("RAGAS_TEST_TIMEOUT", "12.5")
    assert _positive_float_env("RAGAS_TEST_TIMEOUT", 30.0) == 12.5

    monkeypatch.setenv("RAGAS_TEST_TIMEOUT", "not-a-number")
    assert _positive_float_env("RAGAS_TEST_TIMEOUT", 30.0) == 30.0

    monkeypatch.setenv("RAGAS_TEST_TIMEOUT", "0")
    assert _positive_float_env("RAGAS_TEST_TIMEOUT", 30.0) == 30.0


def test_positive_int_env_uses_valid_value_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("RAGAS_TEST_MAX_TOKENS", "4096")
    assert _positive_int_env("RAGAS_TEST_MAX_TOKENS", 1024) == 4096

    monkeypatch.setenv("RAGAS_TEST_MAX_TOKENS", "12.5")
    assert _positive_int_env("RAGAS_TEST_MAX_TOKENS", 1024) == 1024

    monkeypatch.setenv("RAGAS_TEST_MAX_TOKENS", "-1")
    assert _positive_int_env("RAGAS_TEST_MAX_TOKENS", 1024) == 1024


def test_prepare_retrieved_contexts_keeps_rank_order_and_nonempty_content() -> None:
    contexts = [
        {"retrieval_rank": 2, "content": " 두 번째 근거 "},
        {"retrieval_rank": 1, "content": "첫 번째 근거"},
        {"retrieval_rank": 3, "content": ""},
    ]

    assert prepare_retrieved_contexts(contexts) == ["첫 번째 근거", "두 번째 근거"]


def test_reference_lookup_uses_only_approved_records_by_default(tmp_path: Path) -> None:
    path = tmp_path / "references.jsonl"
    rows = [
        {
            "case_id": "draft-case",
            "question": "초안 질문",
            "reference": "초안 답안",
            "review_status": "draft",
        },
        {
            "case_id": "approved-case",
            "question": "승인 질문",
            "reference": "승인 답안",
            "review_status": "approved",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    assert find_reference_record("초안 질문", path=path) is None
    approved = find_reference_record("승인 질문", path=path)
    assert approved is not None
    assert approved["reference"] == "승인 답안"
    assert find_reference_record("초안 질문", path=path, approved_only=False) is not None


def test_evaluation_cache_key_changes_with_answer_or_context() -> None:
    common = {
        "question": "경복궁은 언제 지어졌나요?",
        "contexts": [{"retrieval_rank": 1, "content": "근거"}],
        "reference": None,
    }
    first = evaluation_cache_key(response="첫 답변", **common)
    second = evaluation_cache_key(response="다른 답변", **common)
    third = evaluation_cache_key(
        question=common["question"],
        response="첫 답변",
        contexts=[{"retrieval_rank": 1, "content": "다른 근거"}],
        reference=None,
    )

    assert first != second
    assert first != third


def test_evaluation_cache_key_tracks_answer_relevancy_prompt_version(
    monkeypatch,
) -> None:
    import evaluation.ragas_evaluator as evaluator

    inputs = {
        "question": "길쌈노래에 대해 설명해줘.",
        "response": "길쌈노래는 노동요이다.",
        "contexts": [{"retrieval_rank": 1, "content": "근거"}],
        "reference": None,
    }
    first = evaluation_cache_key(**inputs)
    monkeypatch.setattr(
        evaluator,
        "ANSWER_RELEVANCY_PROMPT_VERSION",
        "same-language-v2",
    )

    assert evaluation_cache_key(**inputs) != first
