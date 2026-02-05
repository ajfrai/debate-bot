# Search Agent Bug Report

**Date**: 2026-02-05
**Source**: Simulation with fixtures + analysis of previous run logs
**Status**: ALL BUGS FIXED

## Executive Summary

The search agent had **3 critical bugs** and **2 medium issues** that together caused:
- Only getting 1 search result (or zero) despite multiple tasks
- UI appearing frozen, updating only every ~10 seconds
- Timer appearing broken
- Infinite retry loops consuming resources

**All issues have been fixed.** See "Fix Applied" sections below.

## Bug #1: Mock Format Mismatch (CRITICAL)

### Symptom
Search returns `urls_found: 0` for every query, triggering immediate error handling.

### Root Cause
The `mock_brave_search()` function in `tests/fixtures/__init__.py` returns **JSON format**:
```python
return json.dumps({"results": results})
```

But `_extract_urls_from_search_results()` in `debate/research_agent.py` expects **markdown format**:
```python
# Real _brave_search returns:
## Search Results

1. **Title**
   URL: https://example.com
   Description: ...
```

The URL extraction uses regex looking for `URL: ` prefix which doesn't exist in JSON.

### Evidence from Event Log
```json
{"action": "search_success", "query": "...", "urls_found": 0, "urls_to_fetch": 0}
{"action": "task_error", "error": "All URLs already tried", "retry_count": 1}
```

Every search "succeeds" but returns 0 URLs, immediately triggering error handling.

### Fix Required
Update `mock_brave_search()` to return markdown format matching `_brave_search()`.

### Fix Applied ✓
**File**: `tests/fixtures/__init__.py`

Changed `mock_brave_search()` to return markdown format with `URL:` prefix instead of JSON. Also added realistic delays (0.3-0.8s for search, 0.5-1.5s for fetch) and configurable error simulation.

---

## Bug #2: Infinite Retry Loop (CRITICAL)

### Symptom
Tasks continue being reprocessed indefinitely even after `max_retries_reached` is logged.

### Root Cause
Two issues combine:

1. **Retry counter doesn't prevent re-selection**: `get_pending_tasks()` returns tasks regardless of retry count. It only checks the `_read_log.json` which is only updated on **successful** completion.

2. **max_retries check has no persistent effect**: After logging `max_retries_reached`, the task moves to "error" stage but:
   - The task file still exists in `strategy/tasks/`
   - On next `check_for_work()` cycle, it's returned again
   - Retry counter is per-agent-instance (lost on restart)

### Evidence from Event Log
```json
{"action": "max_retries_reached", "task_id": "task_1"}  // retry_count: 3
{"action": "processing_task", "task_id": "task_2"}
{"action": "max_retries_reached", "task_id": "task_2"}  // retry_count: 3
{"action": "processing_task", "task_id": "task_1"}       // BACK TO task_1!
{"action": "task_error", "retry_count": 4}              // Counter keeps going!
```

The same two tasks cycle endlessly, with retry_count going to 4, 5, 6, 7, 8...

### Fix Applied ✓
**Files**: `debate/prep/session.py`, `debate/prep/search_agent.py`

1. Added `_failed_tasks.json` persistent storage in session
2. Added `mark_task_failed()`, `is_task_failed()`, `reset_failed_tasks()` methods
3. Updated `_handle_error()` to call `mark_task_failed()` when max retries reached
4. Updated `get_pending_tasks()` to exclude failed task IDs

---

## Bug #3: Tasks Don't Stay in Error State (CRITICAL)

### Symptom
After a task hits max retries, it should stay in the "error" column permanently. Instead, it gets picked up again.

### Root Cause
The `task_stages` dict is in-memory only. When `check_for_work()` runs:
1. It calls `session.get_pending_tasks()`
2. This returns ANY task file not in `_read_log.json`
3. Failed tasks aren't in the read log, so they're returned
4. Agent resets their stage to "queued"

```python
# In check_for_work()
for task in tasks:
    task_id = task.get("id", "")
    if task_id and task_id not in self.state.task_stages:
        self.state.task_stages[task_id] = "queued"  # Overwrites error state!
```

### Fix Applied ✓
**File**: `debate/prep/search_agent.py`

The core fix is in Bug #2 - failed tasks are now excluded at the session level via `get_pending_tasks()`, which checks `_failed_tasks.json`. Tasks that hit max retries are persisted and won't be returned on subsequent calls or agent restarts.

---

## Issue #4: UI Updates Too Slow (MEDIUM)

### Symptom
UI appears to update every ~10 seconds instead of 0.5 seconds as configured.

### Root Cause
When mocks run instantly (no delays), the agent completes all work before the UI has a chance to render intermediate states. The actual workflow is:

1. `render_single_agent_ui()` starts with `refresh_rate=0.5`
2. `agent.run()` processes items in a tight loop
3. Mock operations complete in <1ms
4. UI refresh only catches final state

### Evidence from Simulation
With simulated delays (0.5-2s per operation):
- 14 UI state changes captured in 30 seconds
- Updates every ~2 seconds on average

Without delays (original mocks):
- <5 UI changes captured
- Mostly just "starting" and "done" states

### Fix Applied ✓
**File**: `tests/fixtures/__init__.py`

Added configurable delays to all mock functions:
- `SEARCH_DELAY_RANGE = (0.3, 0.8)` - Network latency for search
- `FETCH_DELAY_RANGE = (0.5, 1.5)` - Article download time
- `QUERY_DELAY = 0.1` - LLM response time
- `FETCH_ERROR_RATE = 0.2` - 20% of fetches fail

---

## Issue #5: Timer Display Issues (MEDIUM)

### Symptom
Timer appears stuck or jumps erratically.

### Root Cause
The timer calculation in `format_time_remaining()` works correctly, but when the agent loop blocks on synchronous operations, the UI coroutine doesn't run.

The `agent.run()` and `render_single_agent_ui()` run as concurrent tasks via `asyncio.gather()`, but:
- `_generate_query()` uses `asyncio.to_thread()` ✓
- `_brave_search()` is called synchronously ✗
- `fetch_source()` is called synchronously ✗

Synchronous calls block the event loop, preventing UI updates.

### Fix Applied ✓
**File**: `debate/prep/search_agent.py`

Wrapped synchronous calls in `asyncio.to_thread()`:
- `_brave_search()` / `mock_brave_search()` now run in thread pool
- `fetch_source()` / `mock_fetch_source()` now run in thread pool

This allows the event loop to continue running and update the UI while I/O operations complete.

---

## Summary of Fixes Applied

| Bug | File | Severity | Status |
|-----|------|----------|--------|
| Mock format mismatch | `tests/fixtures/__init__.py` | CRITICAL | ✓ FIXED |
| Infinite retry loop | `debate/prep/search_agent.py` | CRITICAL | ✓ FIXED |
| Tasks don't stay failed | `debate/prep/session.py` | CRITICAL | ✓ FIXED |
| Mocks lack delays | `tests/fixtures/__init__.py` | MEDIUM | ✓ FIXED |
| Sync calls block UI | `debate/prep/search_agent.py` | MEDIUM | ✓ FIXED |

## Verification

Run the simulation script to verify all fixes:
```bash
uv run python tests/simulate_search_agent.py
```

Expected output:
- **0 critical issues** detected
- **URLs found > 0** in search_success events
- **Tasks stay in error state** after max retries
- **~20+ UI updates** in 30 seconds
- **task_permanently_failed** events logged for failed tasks

## Test Validation

All fixes validated:
- [x] Mock search returns markdown format with extractable URLs
- [x] Tasks stop after 3 retries and stay in error state
- [x] Failed tasks are persisted and not re-processed on restart
- [x] UI updates smoothly (~1-2 seconds between updates)
- [x] Timer counts down accurately (no blocking)
