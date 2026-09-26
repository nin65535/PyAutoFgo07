from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from autofgo.api_errors import request_validation_error_handler
from autofgo.commands import (
    CommandConflictError,
    command_conflict_handler,
    invalid_state_handler,
    unavailable_handler,
)
from autofgo.commands import (
    router as command_router,
)
from autofgo.config import get_settings
from autofgo.events import router as event_router
from autofgo.execution import ExecutionUnavailableError, InvalidExecutionStateError
from autofgo.scenarios import ScenarioError, router, scenario_error_handler
from autofgo.security import ApiSecurityMiddleware, origin_from_url

app = FastAPI(title="autoFgo API", version="0.1.0")
allowed_origin = origin_from_url(get_settings().chrome_app_url)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[allowed_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-AutoFgo-Session-Id"],
)
app.add_middleware(ApiSecurityMiddleware, allowed_origin=allowed_origin)
app.include_router(router)
app.include_router(command_router)
app.include_router(event_router)
app.add_exception_handler(ScenarioError, scenario_error_handler)
app.add_exception_handler(CommandConflictError, command_conflict_handler)
app.add_exception_handler(InvalidExecutionStateError, invalid_state_handler)
app.add_exception_handler(ExecutionUnavailableError, unavailable_handler)
app.add_exception_handler(RequestValidationError, request_validation_error_handler)

static_directory = get_settings().static_directory
if static_directory is not None:
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
