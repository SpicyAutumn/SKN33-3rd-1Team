from __future__ import annotations

import re


_INJECTION_PATTERNS = (
    re.compile(r"(?:이전|위의|앞의)\s*(?:지시|규칙|명령).{0,12}(?:무시|잊어)", re.IGNORECASE),
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions?|rules?)", re.IGNORECASE),
    re.compile(r"(?:system|developer)\s*prompt", re.IGNORECASE),
    re.compile(r"(?:시스템|개발자)\s*(?:프롬프트|지시|메시지).{0,24}(?:보여|출력|공개|복사)", re.IGNORECASE),
)
_SECRET_REQUEST_PATTERNS = (
    re.compile(r"(?:api\s*key|access\s*token|secret\s*key).{0,12}(?:보여|출력|알려|공개)", re.IGNORECASE),
    re.compile(r"(?:키|토큰|비밀번호|환경\s*변수).{0,12}(?:보여|출력|알려|공개)", re.IGNORECASE),
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bpcsk_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\brpa_[A-Za-z0-9_-]{16,}\b"),
)


def is_unsafe_request(question: str) -> bool:
    return any(pattern.search(question) for pattern in (*_INJECTION_PATTERNS, *_SECRET_REQUEST_PATTERNS))


def contains_secret_value(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_VALUE_PATTERNS)
