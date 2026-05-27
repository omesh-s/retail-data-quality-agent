from __future__ import annotations

from contextvars import ContextVar, Token

_REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> Token[str]:
    return _REQUEST_ID.set(request_id)


def get_request_id() -> str:
    return _REQUEST_ID.get()


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID.reset(token)
