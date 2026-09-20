from fastapi import FastAPI

from autofgo.scenarios import ScenarioError, router, scenario_error_handler

app = FastAPI(title="autoFgo API", version="0.1.0")
app.include_router(router)
app.add_exception_handler(ScenarioError, scenario_error_handler)


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
