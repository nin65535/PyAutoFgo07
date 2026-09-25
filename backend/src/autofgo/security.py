from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

SESSION_HEADER = "X-AutoFgo-Session-Id"
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_REQUEST_TARGET_LENGTH = 2048


@dataclass(slots=True)
class SessionSecurity:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    _token: str | None = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    @property
    def token(self) -> str:
        if self._token is None:
            raise RuntimeError("The autoFgo session is no longer active")
        return self._token

    def authenticate(self, session_id: str | None, authorization: str | None) -> bool:
        token = self._token
        if token is None or session_id is None or authorization is None:
            return False
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            return False
        return secrets.compare_digest(session_id, self.session_id) and secrets.compare_digest(
            authorization[len(prefix) :], token
        )

    def invalidate(self) -> None:
        self._token = None


session_security = SessionSecurity()


def origin_from_url(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def session_fragment() -> str:
    return f"autofgoSession={session_security.session_id}&autofgoToken={session_security.token}"


class ApiSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, allowed_origin: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed_origin = allowed_origin

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin is not None and origin != self.allowed_origin:
            return self._error(403, "ORIGIN_FORBIDDEN", "この接続元からは利用できません。")

        if request.method == "OPTIONS":
            return await call_next(request)

        if len(request.url.path) + len(request.url.query) > MAX_REQUEST_TARGET_LENGTH:
            return self._error(414, "REQUEST_TOO_LARGE", "要求が長すぎます。")
        if request.url.query:
            return self._error(422, "VALIDATION_ERROR", "未対応のクエリ指定があります。")

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    return self._error(413, "REQUEST_TOO_LARGE", "要求データが大きすぎます。")
            except ValueError:
                return self._error(400, "INVALID_REQUEST", "要求形式が不正です。")

        body = await request.body()
        if len(body) > MAX_REQUEST_BODY_BYTES:
            return self._error(413, "REQUEST_TOO_LARGE", "要求データが大きすぎます。")
        if body and not (request.method == "POST" and request.url.path == "/api/commands"):
            return self._error(422, "VALIDATION_ERROR", "このAPIは要求データを受け付けません。")

        session_id = request.headers.get(SESSION_HEADER)
        authorization = request.headers.get("authorization")
        if (session_id is not None and len(session_id) > 36) or (
            authorization is not None and len(authorization) > 128
        ):
            return self._error(401, "AUTHENTICATION_REQUIRED", "接続を確認できません。")

        if not session_security.authenticate(session_id, authorization):
            return self._error(401, "AUTHENTICATION_REQUIRED", "接続を確認できません。")

        return await call_next(request)

    @staticmethod
    def _error(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status, content={"error": {"code": code, "message": message}}
        )
