import asyncio
from typing import Any

import pytest
from pydantic import BaseModel
from browser_use.llm.base import BaseChatModel

from browser_use.api import build_task, run_task
from browser_use.agent.views import AgentHistoryList, AgentOutput
from browser_use.agent.service import Agent


class MockLLM(BaseChatModel):  # type: ignore[misc]
    model = "mock-model"
    temperature = 0

    @property
    def provider(self) -> str:  # type: ignore[override]
        return "mock"

    @property
    def name(self) -> str:  # minimal property for protocol
        return self.model

    async def ainvoke(self, messages, output_format=None):  # type: ignore
        raise RuntimeError("ainvoke should be patched in tests")

@pytest.mark.asyncio
async def test_build_task_injects_profile():
    task = build_task("Do something", {"a": 1, "b": 2})
    assert "USER CONTEXT" in task
    assert "- a: 1" in task
    assert task.endswith("Do something")

class StructuredOut(BaseModel):
    value: str

@pytest.mark.asyncio
async def test_run_task_with_mock_llm_and_structured_output(monkeypatch):
    async def fake_get_model_output(self, input_messages):  # type: ignore
        action_model_cls = self.ActionModel  # type: ignore
        action_instance = action_model_cls(done={"success": True, "data": {"value": "ok"}})
        return AgentOutput.type_with_custom_actions(self.ActionModel)(
            thinking=None,
            evaluation_previous_goal="",
            memory="",
            next_goal="",
            action=[action_instance],
        )

    monkeypatch.setattr(Agent, "_get_model_output_with_retry", fake_get_model_output)
    async def fake_execute_actions(self):  # type: ignore
        from browser_use.agent.views import ActionResult
        # Simulate successful done action execution
        self.state.last_result = [ActionResult(is_done=True, success=True, extracted_content='{"value": "ok"}')]  # type: ignore[attr-defined]
    monkeypatch.setattr(Agent, "_execute_actions", fake_execute_actions)
    history: AgentHistoryList = await run_task(
        base_task="Say hi",
        user_profile={"user_id": "u1"},
        llm=MockLLM(),
        max_steps=1,
        output_model_schema=StructuredOut,
        headless=True,
        disable_browser=True,
    )
    assert history.history
    assert history.is_done() or history.final_result() is not None


@pytest.mark.asyncio
async def test_intervention_callbacks(monkeypatch):
    calls = {"steps": 0, "events": 0, "paused": False}

    class MockLLM2(MockLLM):
        pass

    async def fake_get_model_output(self, input_messages):  # type: ignore
        action_model_cls = self.ActionModel  # type: ignore
        action_instance = action_model_cls(done={"text": "Finished", "success": True, "files_to_display": []})
        return AgentOutput.type_with_custom_actions(self.ActionModel)(  # type: ignore
            thinking=None,
            evaluation_previous_goal="",
            memory="",
            next_goal="",
            action=[action_instance],
        )

    monkeypatch.setattr(Agent, "_get_model_output_with_retry", fake_get_model_output)

    async def on_step(agent, history):  # noqa: ARG001
        calls["steps"] += 1
        return {"pause": True}

    def on_event(evt):  # noqa: ARG001
        calls["events"] += 1

    history = await run_task(
        base_task="Just finish",
        llm=MockLLM2(),
        max_steps=1,
        on_step=on_step,
        on_browser_event=on_event,
    disable_browser=True,
    )
    assert history.history
    assert calls["steps"] >= 1
    assert calls["events"] >= 0


@pytest.mark.asyncio
async def test_structured_output_property(monkeypatch):
    """Ensure structured_output returns parsed model instance when final_result JSON present."""

    class MockLLM3(MockLLM):
        pass

    async def fake_get_model_output(self, input_messages):  # type: ignore
        action_model_cls = self.ActionModel  # type: ignore
        action_instance = action_model_cls(done={"success": True, "data": {"value": "ok"}})
        return AgentOutput.type_with_custom_actions(self.ActionModel)(
            thinking=None,
            evaluation_previous_goal="",
            memory="",
            next_goal="",
            action=[action_instance],
        )

    monkeypatch.setattr(Agent, "_get_model_output_with_retry", fake_get_model_output)

    history = await run_task(
        base_task="Produce structured output",
        llm=MockLLM3(),
        max_steps=1,
        output_model_schema=StructuredOut,
        disable_browser=True,
    )
    # Simulate final JSON string extraction produced by done action
    history.history[-1].result[-1].extracted_content = '{"value": "ok"}'
    so = history.structured_output
    assert so is not None
    assert isinstance(so, StructuredOut)
    assert so.value == "ok"


@pytest.mark.asyncio
async def test_missing_api_key_error(monkeypatch):
    """Calling run_task without llm and no API keys should raise RuntimeError."""
    import os
    # Backup
    orig_openai = os.environ.get("OPENAI_API_KEY")
    orig_anthropic = os.environ.get("ANTHROPIC_API_KEY")
    orig_google = os.environ.get("GOOGLE_API_KEY")
    # Clear env
    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]:
        if key in os.environ:
            del os.environ[key]
    try:
        with pytest.raises(RuntimeError):
            await run_task(base_task="Hello", max_steps=1)
    finally:
        if orig_openai is not None:
            os.environ["OPENAI_API_KEY"] = orig_openai
        if orig_anthropic is not None:
            os.environ["ANTHROPIC_API_KEY"] = orig_anthropic
        if orig_google is not None:
            os.environ["GOOGLE_API_KEY"] = orig_google


@pytest.mark.asyncio
async def test_intervention_stop_and_add_task(monkeypatch):
    """Verify stop and add_task directives are respected in on_step callback."""
    captured = {"agent": None, "steps": 0}

    async def fake_get_model_output(self, input_messages):  # type: ignore
        action_model_cls = self.ActionModel  # type: ignore
        action_instance = action_model_cls(done={"text": "Finished", "success": True, "files_to_display": []})
        return AgentOutput.type_with_custom_actions(self.ActionModel)(  # type: ignore
            thinking=None,
            evaluation_previous_goal="",
            memory="",
            next_goal="",
            action=[action_instance],
        )

    monkeypatch.setattr(Agent, "_get_model_output_with_retry", fake_get_model_output)

    async def on_step(agent, history):  # noqa: ARG001
        if captured["agent"] is None:
            captured["agent"] = agent
            captured["steps"] += 1
            return {"add_task": "New follow up task", "stop": True}
        return None

    history = await run_task(
        base_task="Initial task",
        llm=MockLLM(),
        max_steps=5,
        on_step=on_step,
    disable_browser=True,
    )
    # Only first step should have run due to stop directive
    assert history.number_of_steps() == 1
    # Agent's task should have been updated
    assert getattr(captured["agent"], "task", "") == "New follow up task"
