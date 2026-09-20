from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _json_pointer(location: tuple[Any, ...]) -> str:
    parts = location[1:] if location and location[0] in {"body", "query", "path"} else location
    escaped = (str(part).replace("~", "~0").replace("/", "~1") for part in parts)
    return "/" + "/".join(escaped)


def _issue_code(error_type: str) -> str:
    if error_type == "missing":
        return "REQUIRED"
    if error_type == "extra_forbidden":
        return "UNKNOWN_FIELD"
    if error_type in {"greater_than_equal", "less_than_equal", "too_long"}:
        return "OUT_OF_RANGE"
    if error_type.startswith(("int_", "list_", "string_", "model_")):
        return "INVALID_TYPE"
    if error_type in {"literal_error", "union_tag_invalid", "string_pattern_mismatch"}:
        return "INVALID_FORMAT"
    return "INVALID_COMBINATION"


async def request_validation_error_handler(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    errors = error.errors()
    if errors and errors[0]["type"] == "json_invalid":
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_JSON", "message": "JSONの形式が不正です。"}},
        )

    issues = [
        {
            "path": _json_pointer(item["loc"]),
            "code": _issue_code(item["type"]),
            "message": "入力値が仕様を満たしていません。",
        }
        for item in errors
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "入力値が不正です。",
                "details": {"issues": issues},
            }
        },
    )
