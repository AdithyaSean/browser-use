Backend Integration Guide
=========================

This guide explains how to use browser-use as a pure backend automation/agent library without its CLI / Textual UI.

Quick Start
-----------
1. Install only core deps (avoid `[cli]` extra):
   pip install browser-use
2. Use the new wrapper API:
   from browser_use.api import run_task_sync
   result = run_task_sync(
       base_task="Find latest Python release notes",
       user_profile={"id": "123", "plan": "pro", "interests": ["python", "web"]},
       model="gpt-4o-mini",  # optional override
       headless=True,
   )
   print(result.final_result())

API Overview
------------
browser_use.api exposes:
 - build_task(base_task, user_profile, template_override=None) -> str
 - async run_task(...)
 - run_task_sync(...)

User Profile Injection
----------------------
User data is embedded into the task prompt in a structured preamble. Provide only non-sensitive fields or ensure you configure allowed_domains + sensitive_data as appropriate.

Customization Points
--------------------
 - model: LLM model name (auto-detects from available keys if omitted)
 - headless: whether browser runs headless
 - max_steps: cap agent exploration depth (default 50 here)
 - extend_system_message: pass through to Agent for extra instructions
 - include_recent_events: surface recent internal browser events to model
 - on_step: callback(agent, history) -> optional directives dict {'pause': True, 'stop': True, 'add_task': 'new task'}
 - on_browser_event: callback(event) to stream every internal browser/agent event
 - intervene: set False to make on_step read-only (ignores directives)

Planned Additions
-----------------
 - Structured output model passthrough
 - Simpler exception taxonomy
 - Optional lightweight HTTP service wrapper (FastAPI)

Security Notes
--------------
If you use sensitive_data with domain-scoped credentials, set BrowserProfile.allowed_domains to restrict exfiltration via prompt injection.

Observability & Intervention
----------------------------
You can mirror what the original CLI/TUI displayed by wiring hooks:

Example:
```python
from browser_use.api import run_task_sync

def on_step(agent, history):
   last = history.history[-1] if history.history else None
   if last and last.result and any(r.error for r in last.result):
      # Pause on first error to let external system inspect & decide
      return {'pause': True}

def on_browser_event(evt):
   # Stream to logs / websocket
   print(f"EVENT {evt.__class__.__name__}")

run_task_sync(
   base_task="Collect top 3 results for Python downloads",
   on_step=on_step,
   on_browser_event=on_browser_event,
)
```

Best Practices:
 - Keep callbacks fast; offload heavy processing to a queue.
 - Use intervene=False if you only want telemetry and no control surface.
 - For multi-tenant systems, sanitize events before broadcasting (screenshots / URLs).
