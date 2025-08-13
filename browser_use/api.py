"""Minimal backend-facing API wrappers for running browser-use agents without the CLI/TUI.

Public Functions:
 - build_task: create a composite task string from user_profile + base_task
 - async run_task: run an agent and return its history
 - run_task_sync: sync wrapper around run_task

These helpers intentionally avoid importing heavy CLI / textual modules.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, Optional, cast, Type

from browser_use.agent.service import Agent  # type: ignore
from browser_use.browser import BrowserProfile, BrowserSession
from browser_use.controller.service import Controller
from browser_use.llm.openai.chat import ChatOpenAI  # Fallback; auto-detect for others similar to cli later
from browser_use.config import CONFIG
from browser_use.telemetry.service import disable_telemetry

DEFAULT_MAX_STEPS = 50


def build_task(base_task: str, user_profile: Optional[Dict[str, Any]] = None, template_override: Optional[str] = None) -> str:
	"""Return a composite task including optional user profile context.

	The template is intentionally simple so callers can reproduce or override it externally.
	"""
	if not user_profile:
		return base_task.strip()

	if template_override:
		return template_override.format(user_profile=user_profile, base_task=base_task).strip()

	profile_lines: Iterable[str] = []
	try:
		# Deterministic key ordering for reproducibility
		items = sorted(user_profile.items(), key=lambda kv: kv[0])
		lines = []
		for k, v in items:
			lines.append(f"- {k}: {v}")
		profile_lines = lines
	except Exception:  # pragma: no cover - defensive
		profile_lines = [str(user_profile)]

	preamble = [
		"You are assisting with a task for the following user context.",
		"Use the context only when relevant. Do not hallucinate missing fields.",
		"USER CONTEXT:",
		*profile_lines,
		"---",
		base_task.strip(),
	]
	return "\n".join(preamble)


async def run_task(
	base_task: str,
	user_profile: Optional[Dict[str, Any]] = None,
	*,
	model: Optional[str] = None,
	llm: Any | None = None,
	headless: bool = True,
	disable_browser: bool | None = None,
	max_steps: int = DEFAULT_MAX_STEPS,
	extend_system_message: Optional[str] = None,
	include_recent_events: bool = False,
	output_model_schema: Type[Any] | None = None,
	on_step: Optional[Any] = None,
	on_browser_event: Optional[Any] = None,
	intervene: bool = True,
	**agent_kwargs: Any,
):
	"""Run a task asynchronously and return the AgentHistoryList.

	Parameters:
		base_task: Core instruction text.
		user_profile: Optional dict to enrich prompt.
		model: LLM model name. If None, default heuristic based on available keys.
		headless: Browser headless mode.
		max_steps: Safety cap on steps.
		extend_system_message: Additional system prompt content.
		include_recent_events: Pass through to Agent for context enrichment.
		**agent_kwargs: Forwarded to Agent(...).
	"""
	task = build_task(base_task, user_profile)

	# Allow explicit llm injection (useful for testing / custom providers)
	if llm is None:
		# Basic LLM selection (simplified vs cli.get_llm). Extend later for other providers.
		if model is None:
			# Preference order similar to CLI: OpenAI -> Anthropic -> Google
			if CONFIG.OPENAI_API_KEY:
				model = "gpt-4o-mini"
			elif CONFIG.ANTHROPIC_API_KEY:
				try:
					from browser_use.llm.anthropic.chat import ChatAnthropic
				except ImportError as e:  # pragma: no cover - environmental
					raise ImportError(
						"Anthropic provider not installed. Install with: pip install 'browser-use[providers]'"
					) from e
				llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)
			elif CONFIG.GOOGLE_API_KEY:
				try:
					from browser_use.llm.google.chat import ChatGoogle
				except ImportError as e:  # pragma: no cover - environmental
					raise ImportError(
						"Google provider not installed. Install with: pip install 'browser-use[providers]'"
					) from e
				llm = ChatGoogle(model="gemini-2.0-flash-exp", temperature=0)
			else:
				raise RuntimeError("No supported LLM API keys found (OpenAI / Anthropic / Google). Provide one or pass model explicitly.")

		# If we didn't set llm in Anthropic/Google branch, create OpenAI llm.
		if 'llm' not in locals():  # noqa: SIM116
			llm = ChatOpenAI(model=model, temperature=0, api_key=CONFIG.OPENAI_API_KEY)

	browser_profile = BrowserProfile(headless=headless)
	browser_session = BrowserSession(browser_profile=browser_profile)

	# Suppress telemetry automatically in synthetic disable_browser mode (tests) BEFORE any controller/agent creation
	if disable_browser:
		disable_telemetry()

	controller = Controller()

	# Attach browser event observer if provided (schedule async if coroutine to avoid warnings)
	if on_browser_event is not None and getattr(browser_session, 'event_bus', None):
		def _wrap_event(ev):
			res = _maybe_await(on_browser_event, ev)
			if asyncio.iscoroutine(res):  # schedule to avoid un-awaited coroutine warnings
				asyncio.create_task(res)
		browser_session.event_bus.on('*', _wrap_event)

	# Instantiate Agent (generic parameters not specified for simplicity here)
	agent = Agent(  # type: ignore[call-arg]
		task=task,
		llm=cast(Any, llm),
		browser_session=browser_session,
		controller=controller,
		extend_system_message=extend_system_message,
		include_recent_events=include_recent_events,
		output_model_schema=output_model_schema,
		disable_browser=bool(disable_browser),
		**agent_kwargs,
	)

	# Step end hook applying intervention directives
	async def _on_step_end(a: Any):  # Agent instance
		if on_step is None:
			return
			# user didn't supply callback
		res = await _maybe_await(on_step, a, a.history)
		if not intervene or res is None:
			return
		if isinstance(res, dict):  # interpret directives
			if res.get('pause'):
				a.pause()
			if res.get('stop'):
				a.stop()
			new_task = res.get('add_task') or res.get('new_task')
			if new_task:
				a.add_new_task(str(new_task))

	# Cast to Any to avoid pyright generic binding issues
	history = await cast(Any, agent).run(max_steps=max_steps, on_step_end=_on_step_end)  # type: ignore[attr-defined]
	return history


def run_task_sync(**kwargs):
	"""Synchronous convenience wrapper around run_task.

	Usage:
		history = run_task_sync(base_task="Check the Python downloads page", user_profile={"tier": "pro"})
	"""
	return asyncio.run(run_task(**kwargs))


__all__ = ["build_task", "run_task", "run_task_sync"]


# ---------------- internal helpers -----------------
async def _maybe_await(func: Any, *args, **kwargs):
	"""Call sync or async callback uniformly."""
	if asyncio.iscoroutinefunction(func):
		return await func(*args, **kwargs)
	return func(*args, **kwargs)
