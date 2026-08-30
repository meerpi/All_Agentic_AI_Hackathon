# Fix Progress Tracking — Live Test Findings

| Bug / Component | File | Status | What Was Verified | What's Left |
|---|---|---|---|---|
| **1. Dynamic Arg Resolution** | `agent/orchestrator.py` | ✅ FIXED | Verified step-number indexed lookup & regex substitution for `$step_3.document_id` and `"https://$step_1.url/embed"` | Completed |
| **2. HITL Resume Loop** | `agent/orchestrator.py` | ✅ FIXED | Verified live: pauses at `WAITING_APPROVAL`, resume sets `is_approved=True`, executes step to `COMPLETED` | Completed |
| **3. Self-Correction Boundary** | `agent/orchestrator.py`, `agent/prompts.py` | ✅ FIXED | Verified: definitive 404/not-found errors reject cross-tool substitution to unrelated tools | Completed |
| **4. Sheets Unresolved ID Fallback** | `agent/tools/google_sheets_tool.py` | IN_PROGRESS | Diagnosed: silent orphan spreadsheet creation on missing ID | Replace silent fallback with explicit ValueError naming unresolved ID; verify live |
| **5. Jira Default Project Override** | `agent/tools/jira_tool.py` | PENDING | Diagnosed: invalid project key gets overridden with default `KAN` | Replace silent override with explicit ValueError for invalid key; verify live |
| **6. Media Controller Action Names & Errors** | `agent/tools/media_controller.py` | PENDING | Diagnosed: prompt/schema mismatch causing invalid action generation; generic error on unauth Spotify | Align prompt schema & actions; return explicit error for inactive Spotify session; verify live |
| **7. OS Desktop Tool App Launch** | `agent/tools/os_desktop_tool.py` | PENDING | Diagnosed: `launch_application` not routed in `run()`, simulated hotkey fallback | Route `launch_application`/`open_app` to driver; remove simulated hotkey fallback; verify live |
| **8. YouTube Ad-Skip Timeout** | `agent/browser/youtube_driver.py` | PENDING | Diagnosed: waiting on ad button times out when no ad is present | Check button presence before waiting; treat "no ad" as expected; verify live |
| **9. Bot HITL Error Messaging** | `discord_bot.py`, `agent/telegram_trigger.py` | PENDING | Diagnosed: bot swallows HITL ValueError into generic internal error | Surface explicit approval requirement message in bot handlers; verify live |
