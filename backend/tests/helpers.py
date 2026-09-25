from autofgo.security import SESSION_HEADER, session_security


def authentication_headers(*, origin: str | None = None) -> dict[str, str]:
    headers = {
        SESSION_HEADER: session_security.session_id,
        "Authorization": f"Bearer {session_security.token}",
    }
    if origin is not None:
        headers["Origin"] = origin
    return headers
