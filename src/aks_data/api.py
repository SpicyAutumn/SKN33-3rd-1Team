from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import EID_RE, normalize_text


DEFAULT_API_BASE_URL = "https://devin.aks.ac.kr:8080/api"


@dataclass
class ApiResponse:
    api_url: str
    raw: bytes
    payload: Any


class ApiRequestError(RuntimeError):
    def __init__(self, reason: str, *, status_code: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


Transport = Callable[[str, dict[str, str], float], bytes]


def _urllib_transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return response.read()


class AksApiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_API_BASE_URL,
        *,
        timeout: float = 30.0,
        retries: int = 2,
        transport: Transport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("AKS_API_KEY가 설정되지 않았습니다.")
        self._api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self._transport = transport or _urllib_transport

    def article_url(self, eid: str) -> str:
        canonical = eid.strip().upper()
        if not EID_RE.fullmatch(canonical):
            raise ValueError(f"잘못된 EID 형식: {eid!r}")
        return f"{self.base_url}/articles/{canonical}"

    def fetch_article(self, eid: str) -> ApiResponse:
        url = self.article_url(eid)
        headers = {"X-API-Key": self._api_key, "Accept": "application/json"}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                raw = self._transport(url, headers, self.timeout)
                try:
                    payload = json.loads(raw.decode("utf-8-sig"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ApiRequestError("invalid_json_response") from exc
                return ApiResponse(api_url=url, raw=raw, payload=payload)
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.retries:
                    raise ApiRequestError(f"http_{exc.code}", status_code=exc.code) from exc
                last_error = exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt >= self.retries:
                    raise ApiRequestError(f"network_error:{type(exc).__name__}") from exc
                last_error = exc
            if attempt < self.retries:
                time.sleep(min(2**attempt, 4))
        raise ApiRequestError(f"network_error:{type(last_error).__name__}")


def _unwrap_article(payload: Any) -> dict[str, Any]:
    value = payload
    for _ in range(4):
        if not isinstance(value, dict):
            return {}
        lowered = {str(key).lower(): key for key in value}
        moved = False
        for candidate in ("article", "data", "result", "item"):
            key = lowered.get(candidate)
            nested = value.get(key) if key is not None else None
            if isinstance(nested, dict):
                value = nested
                moved = True
                break
        if not moved:
            return value
    return value if isinstance(value, dict) else {}


def _walk(value: Any, prefix: str = "") -> list[tuple[str, str, Any]]:
    result: list[tuple[str, str, Any]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            result.append((path, key_text.lower().replace("_", ""), nested))
            result.extend(_walk(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            result.extend(_walk(nested, f"{prefix}[{index}]"))
    return result


def _first_value(article: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized_aliases = tuple(alias.lower().replace("_", "") for alias in aliases)
    for _path, key, value in _walk(article):
        if key in normalized_aliases and value not in (None, "", [], {}):
            return value
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(part for part in (_text(item) for item in value) if part)
    if isinstance(value, dict):
        return " ".join(part for part in (_text(item) for item in value.values()) if part)
    return normalize_text(value)


def parse_article(payload: Any) -> dict[str, Any]:
    article = _unwrap_article(payload)
    eid_value = _text(_first_value(article, ("eid", "article_id", "articleId"))).upper()
    if not EID_RE.fullmatch(eid_value):
        match = re.search(r"E\d{7}", eid_value, re.IGNORECASE)
        eid_value = match.group(0).upper() if match else ""
    title = _text(
        _first_value(
            article,
            ("title", "headword", "article_name", "articleName", "item_name", "itemName", "name"),
        )
    )
    field = _text(_first_value(article, ("field", "field_name", "fieldName", "category", "categoryName", "category_name")))
    body_value = _first_value(article, ("content", "contents", "body", "article_content", "articleContent", "text"))
    body = _text(body_value)
    item_type = _text(
        _first_value(
            article,
            ("item_type", "itemType", "primaryType", "primary_type", "secondaryType", "secondary_type", "type", "typeName"),
        )
    )
    period = _text(_first_value(article, ("period", "era", "age", "periodName")))
    keywords = _text(_first_value(article, ("keywords", "keyword", "tags", "hashtags")))
    mapped = {
        "eid", "articleid", "title", "headword", "articlename", "itemname", "name", "field", "fieldname",
        "category", "categoryname", "content", "contents", "body", "articlecontent", "text",
        "itemtype", "primarytype", "secondarytype", "type", "typename", "period", "era", "age", "periodname", "keywords",
        "keyword", "tags", "hashtags",
    }
    api_only = [str(key) for key in article if str(key).lower().replace("_", "") not in mapped]
    return {
        "eid": eid_value,
        "title": title,
        "field": field,
        "body": body,
        "content_length": len(body),
        "has_body": bool(body),
        "item_type": item_type,
        "period": period,
        "keywords": keywords,
        "api_only_fields": sorted(api_only),
        "response_root_fields": sorted(str(key) for key in article),
    }
