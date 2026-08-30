# Remediation TODO — Grouped by File

## Phase 0 — Setup
- [x] Create branch `remediation/fix-audit-findings`
- [x] .gitignore: add `client_secret_*.json` pattern (was missing)
- [x] git ls-files check: `.env`, `token.json`, `client_secret_*.json` — none tracked
- [x] Write this TODO

## Phase 1–4 — Fixes by File

### `agent/orchestrator.py`
- [ ] **Top1 — HITL gates hardcoded off (L231):** Add `require_approval` field to TaskGoal, thread it to `approval_mode` param. Currently `approval_mode=False` always.
- [ ] **Top1b — Guardrail violation falls through (L241-249):** After guardrail violation, execution continues unconditionally. Must return/raise instead of logging and proceeding.
- [ ] **Top4 — Sequential DAG execution (L213):** `for step_num in topo_order:` ignores parallel groups from TaskDAG. Implement concurrent execution within each parallel group.
- [ ] **Top2b — Retries/backoff (L288, L422):** Single self-correction attempt, no retry loop, no backoff. Add exponential backoff with cap, distinguish retryable vs non-retryable failures.
- [ ] **Phase 3 — Call prompt injection screening on browser observations:** Invoke `screen_page_content_injection` on browser-observed content before it reaches the LLM.
- [ ] **PII redaction on intermediate results (L327-328):** Extend PII redaction to intermediate tool results, not just final summary.

### `agent/models.py`
- [ ] Add `require_approval: bool = False` field to `TaskGoal` model (needed for HITL fix).

### `agent/llm_client.py`
- [ ] **OpenAI support missing:** Add OpenAI provider branch alongside Gemini.
- [ ] **Schema repair missing (L107-110):** On JSON parse failure, send invalid output back with schema for correction before falling back to another model.

### `agent/task_graph.py`
- [ ] Verify parallel groups are properly exposed for the orchestrator to consume (may already be fine).

### `agent/browser/session_manager.py`
- [ ] **Unused asyncio.Lock (L37):** Acquire the lock in `get_page()` to prevent concurrent context initialization race.

### `agent/browser/spotify_driver.py`
- [ ] **create_playlist mocked (L83-88):** Actually type the supplied name and description into the UI after clicking create.

### `agent/browser/desktop_driver.py`
- [ ] **Native Desktop App Runner MISSING:** Add binary existence pre-check (`shutil.which`), detached process spawning (`subprocess.Popen`), display forwarding alongside existing PyAutoGUI/MSS code.

### `agent/browser/vision_grounding.py`
- [ ] **SoM renderer swallows exceptions (L127-130):** Don't silently return original image on rendering failure — propagate or log a clear warning.

### `agent/browser/youtube_driver.py`
- [ ] **seek_seconds no negative validation (L36):** Add bounds check.

### `agent/guardrails/__init__.py`
- [ ] **Prompt injection screen never called in production (L179-188):** Ensure `screen_page_content_injection` is called on browser observations (integration point is in orchestrator/browser pipeline).

### `agent/security/__init__.py`
- [ ] Verify `requires_approval` works correctly when `approval_mode=True` is actually passed (functional, just needs the orchestrator caller fixed).

### `agent/memory/__init__.py`
- [ ] **Silent exception swallowing (L41, L87, L144):** Don't silently reset to empty list on JSON load failure. Log the error with the filepath so corruption is visible.

### `agent/evals/__init__.py`
- [ ] **Silent exception swallowing (L109):** Don't silently discard LLM evaluation failure. Log the error.

### `agent/streaming.py`
- [ ] **SSE streaming faked (L68-78):** Emit real per-step progress events during actual execution instead of batch-emitting upfront then blocking.

### `agent/tools/youtube_api.py`
- [ ] **Hardcoded URL bug (L124):** Change `kYJzX9a9_mE` to actual `video_id` variable.

### `agent/tools/gmail_tool.py`
- [ ] **Draft creation MISSING:** Implement `create_draft` via Gmail API.
- [ ] **Thread reading MISSING:** Implement thread reading (list messages in a thread).
- [ ] **Exception swallowing (L59-66):** Don't return errors as "successful" tool results.

### `agent/tools/google_docs_tool.py`
- [ ] **Structured text/header insertion MISSING (L75-78, L123-126):** Add proper formatting requests (headings, bold, etc.) via Docs API `batchUpdate`.

### `agent/tools/google_sheets_tool.py`
- [ ] **Hardcoded demo row on empty input (L119):** Remove, raise error instead.
- [ ] **Orphan spreadsheet creation on error (L148-172):** Remove fallback that creates new spreadsheets on failure.

### `agent/tools/google_calendar_tool.py`
- [ ] **Unsafe date defaults (L115-118, L145-150):** Don't silently default to tomorrow 10AM or 2PM. Raise a clear error if date parsing fails.

### `agent/tools/jira_tool.py`
- [ ] **Status transitions MISSING (L173):** Implement issue status transition via Jira REST API.
- [ ] **Hardcoded demo tickets (L213-218):** Remove the 3 pre-fabricated tickets on empty input. Raise error instead.

### `agent/tools/github_tool.py` [NEW FILE]
- [ ] **Entirely MISSING:** Build from scratch — PR creation, issue queries, branch management against real GitHub API. Follow auth/config pattern of existing tools.

### `agent/tools/slack_tool.py`
- [ ] **Chat history MISSING:** Implement message history retrieval via Slack API.

### `agent/tools/action_dispatcher.py`
- [ ] **Fakes success on HTTP failure (L34-42):** Remove `simulated: True` fallback. Raise or return explicit error on failure.

### `agent/tools/validator.py`
- [ ] **Substring matching instead of real validation (L28-44):** Implement proper schema/payload validation.

### `agent/tools/registry.py`
- [ ] **Schema validation missing:** Add schema validation when registering tools (validate `execute` signature, required parameters).

### `app.py`
- [ ] **Task cancellation endpoint MISSING:** Add `/api/agent/cancel/{workflow_id}` endpoint.

### `discord_bot.py`
- [ ] **No guardrails on input:** Call shared guardrail function before passing to orchestrator.
- [ ] **Raw str(e) leaked to chat (L44):** Return generic error message, log real error server-side.

### `agent/telegram_trigger.py`
- [ ] **No guardrails on input:** Call shared guardrail function.
- [ ] **Raw exception text leaked to chat (L144):** Return generic error, log real error server-side.

### `static/index.html`
- [ ] **DAG canvas MISSING (L1044-1058):** Replace linear div list with actual SVG/canvas DAG rendering of node/edge structure.

### Test files
- [ ] Move `test_automated_pm_workflow.py`, `test_multi_agent_council.py`, `test_pipeline_execution.py` from root to `tests/`.
- [ ] Add failure-path tests for each fix (not just happy-path mocks).
- [ ] Fix HITL test to exercise production config (`approval_mode` threaded from `TaskGoal`).

## Phase 6 — Self-verification
- [ ] Write REMEDIATION_REPORT.md with updated scorecard
