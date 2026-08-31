from __future__ import annotations


class RagServiceError(RuntimeError):
    """An application error that must not be counted as a semantic refusal."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
