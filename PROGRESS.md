Backend Extraction & Integration Progress
========================================

Goal: Strip all UI (CLI / Textual TUI / example UI artifacts) and expose a clean, minimal, programmatic API to run browser-use agents by passing in a task prompt (optionally enriched with user information) from another backend service.

Legend: [ ] Not Started  [-] In Progress  [~] Partially Done  [x] Done  [!] Blocked
Last Update: 2025-08-13

Phase 1 – Analysis & Planning
---------------------------------
1. Inventory modules (core vs UI) .................................... [x]
2. Define keep/remove list ............................................ [x]
3. Decide minimal public API surface .................................. [x]
4. Add initial wrapper (run_task, run_task_sync) ...................... [x]
5. Create progress tracking document .................................. [x]

Phase 2 – API Extraction
---------------------------------
6. Implement user profile -> prompt injection helper .................. [x]
7. Provide sync + async convenience wrappers .......................... [x]
8. Support structured output option passthrough ....................... [x]
9. Expose simple config overrides (headless, model, timeouts) ......... [x]
10. Add integration guide docs ........................................ [x]
11a. Add observability & intervention hooks (on_step/on_browser_event) . [x]

Phase 3 – UI Decoupling
---------------------------------
11. Mark CLI (browser_use/cli.py) as deprecated internally ............ [x]
12. Guard textual/rich imports behind optional deps ................... [x] (isolated to cli.py via try/except)
13. Prune optional dependencies in pyproject ......................... [x] (provider libs moved to extra [providers]; backend alias added)
14. Remove /examples UI-specific helpers (keep minimal examples) ...... [ ] (defer – low priority while examples still useful)
15. Confirm no residual UI code paths in new API ...................... [x] (grep: textual/rich only in cli.py & examples/ui)

Phase 4 – Hardening & Tests
---------------------------------
16. Happy path run_task wrapper test .................................. [x]
17. User profile injection formatting test ............................ [x]
18. Structured output model test ...................................... [x]
19. Missing API key smoke test ........................................ [x]
20. Lint & type-check adjustments after removals ...................... [x]
20a. Intervention directive variants (pause/stop/add_task) ............ [x]
21. Update README / backend usage & extras docs ....................... [x]
22. Split extras: [backend], [providers], etc. ........................ [x]
23. Ensure no UI deps in base install ................................. [x]
24. Final audit (phases 1–4) .......................................... [x]

Phase 5 – Optional Enhancements (Planned / In Progress)
---------------------------------
25. Suppress telemetry & network in disable_browser test mode ......... [x] (disable_telemetry() auto-called in API)
26. Consolidate duplicate mock helpers in tests ....................... [ ]
27. Fix coroutine warning (_maybe_await un-awaited) ................... [x] (callbacks scheduled; no warnings in tests)
28. Expand coverage: add_task modifies queue / pause resume ........... [ ]
29. FastAPI/HTTP wrapper prototype (serve run_task) ................... [ ]
30. CI matrix: core vs providers extras ............................... [ ]
31. Privacy: screenshot redaction / event sanitization hooks .......... [ ]
32. Document synthetic (disable_browser) mode in README ............... [ ]
33. VS Code pytest discovery configuration stabilized ............... [x] (fixed pyenv shim interference; updated .vscode/settings.json)
34. Legacy browser session API shims (get_current_page, etc.) ......... [~] (added shims; still adapting multi-tab test)
35. SecurityWatchdog wildcard pattern fix (http(s)://*.domain) ........ [x]
36. Refactor CI tab management tests to new CDP API ................... [ ] (pending; interim shims in place)

Completion Summary
---------------------------------
- Backend API (build_task/run_task/run_task_sync) implemented with user profile injection, structured output, observability, and intervention.
- Tests cover: happy path, profile injection, structured output parsing, missing API key error, intervention (pause/stop/add_task).
- UI isolation: CLI guarded via try/except; no textual/rich imports in backend path.
- Dependency pruning: Providers moved to [providers] extra; added backend alias.
- README updated with backend usage, extras, intervention hooks.
- Type/lint adjustments applied (provider imports guarded, llm cast to Any in api wrapper).

Next (Optional Enhancements)
---------------------------------
- See Phase 5 list for tracked optional improvements.

Notes / Decisions
---------------------------------
- We keep Agent, Controller, BrowserSession, LLM abstractions.
- A thin wrapper consolidates common setup (model selection, BrowserProfile) for easier embedding.
- User profile injection currently prepends to base task via a deterministic template; can be swapped to extend_system_message later.
- No destructive deletions done yet—to allow iterative refactor & PR review.

Changelog Snippet (Recent)
---------------------------------
2025-08-13:
 - Structured output tests stabilized (monkeypatched _execute_actions in synthetic mode)
 - Progress file deduplicated & Phase 5 optional roadmap added
 - Identified telemetry suppression & coroutine warning cleanup as next focus
	- Added disable_telemetry() and auto-suppression for disable_browser mode
	- Fixed premature return bug in api.py event registration; scheduled async browser event callbacks to prevent coroutine warnings
	- Synthetic mode now fully suppresses telemetry & cloud sync (null telemetry + early disable)
 - Added .vscode/settings.json explicit pytest args -> VS Code discovery now aligns with pyproject testpaths
 - FIXED: VS Code pytest discovery was using global Python via pyenv shims; created absolute path config to force venv usage
 - VERIFIED: Both terminal and VS Code pytest execution working properly (6/6 API tests passing)
 - Added SecurityWatchdog glob pattern support for scheme-prefixed wildcards (http://*.example.com)
 - Introduced lightweight BrowserSession legacy helpers (create_new_tab, get_current_page, refresh, execute_javascript, take_screenshot, get_scroll_info, get_tabs_info, switch_to_tab)
 - Updated failing CI test for URL allowance; remaining multi-tab test still failing (investigating Target.createTarget behavior under test harness)
