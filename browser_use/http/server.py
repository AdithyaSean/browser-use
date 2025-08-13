from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from browser_use.api import build_task, run_task

app = FastAPI(title="browser-use HTTP API", version=os.getenv("BROWSER_USE_VERSION", "dev"))


class HealthResponse(BaseModel):
    status: str
    version: str


class BuildTaskRequest(BaseModel):
    base_task: str
    user_profile: Optional[Dict[str, Any]] = None
    template_override: Optional[str] = None


class BuildTaskResponse(BaseModel):
    task: str


class RunTaskRequest(BaseModel):
    base_task: str
    user_profile: Optional[Dict[str, Any]] = None
    provider: Optional[str] = None  # e.g., 'ollama'
    model: Optional[str] = None
    headless: bool = True
    disable_browser: Optional[bool] = None
    max_steps: int | None = None
    extend_system_message: Optional[str] = None
    include_recent_events: bool = False
    intervene: bool = True


class RunTaskResponse(BaseModel):
    steps: int
    success: bool | None
    final_result: str | None
    errors: list[str | None]
    urls: list[str | None]


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)


@app.post("/build_task", response_model=BuildTaskResponse)
async def api_build_task(req: BuildTaskRequest) -> BuildTaskResponse:
    task = build_task(req.base_task, req.user_profile, req.template_override)
    return BuildTaskResponse(task=task)


@app.post("/run_task", response_model=RunTaskResponse)
async def api_run_task(req: RunTaskRequest) -> RunTaskResponse:
    try:
        llm = None
        # Provider selection via request or env
        provider = (req.provider or os.getenv("BROWSER_USE_LLM_PROVIDER", "")).strip().lower()
        if provider == "ollama":
            try:
                from browser_use.llm.ollama.chat import ChatOllama  # type: ignore
            except Exception as e:  # pragma: no cover
                raise HTTPException(status_code=400, detail=f"Ollama provider unavailable: {e}")
            model = req.model or os.getenv("BROWSER_USE_LLM_MODEL") or "llama3.1"
            llm = ChatOllama(model=model)

        history = await run_task(
            base_task=req.base_task,
            user_profile=req.user_profile,
            model=None if llm is not None else req.model,
            llm=llm,
            headless=req.headless,
            disable_browser=req.disable_browser,
            max_steps=req.max_steps or 50,
            extend_system_message=req.extend_system_message,
            include_recent_events=req.include_recent_events,
            intervene=req.intervene,
        )
    except Exception as e:  # Return well-formed error message
        raise HTTPException(status_code=400, detail=str(e))

    return RunTaskResponse(
        steps=history.number_of_steps(),
        success=history.is_successful(),
        final_result=history.final_result(),
        errors=history.errors(),
        urls=history.urls(),
    )


# Optional: entrypoint for `uvicorn browser_use.http.server:app`
__all__ = ["app"]
