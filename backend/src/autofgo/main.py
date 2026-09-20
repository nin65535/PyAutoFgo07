from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

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
from autofgo.execution import ExecutionUnavailableError, InvalidExecutionStateError
from autofgo.scenarios import ScenarioError, router, scenario_error_handler

app = FastAPI(title="autoFgo API", version="0.1.0")
app.include_router(router)
app.include_router(command_router)
app.add_exception_handler(ScenarioError, scenario_error_handler)
app.add_exception_handler(CommandConflictError, command_conflict_handler)
app.add_exception_handler(InvalidExecutionStateError, invalid_state_handler)
app.add_exception_handler(ExecutionUnavailableError, unavailable_handler)
app.add_exception_handler(RequestValidationError, request_validation_error_handler)


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
