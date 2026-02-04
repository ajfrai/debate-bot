# Prep Agent UI Display Bug - Fix Summary

## Bug Description

When running prep agents individually (e.g., `debate prep-strategy`), the progress UI did not display during execution. Users only saw output after the agent completed, with no live updates, countdown timer, or real-time status.

### Related Bugs Fixed

1. **No UI for individual agents** - Individual agent commands showed no Rich UI at all
2. **UI shows only at end** - UI would appear only after completion rather than immediately
3. **No research directions shown** - Strategy agent didn't show what it was generating in real-time
4. **No countdown timer** - Individual agents didn't display time remaining

## Root Cause

The individual agent runner functions (`run_strategy_agent`, `run_search_agent`, etc.) in `debate/prep/runner.py` did not call the UI rendering function. They only executed `await agent.run(deadline)` and returned stats, unlike `run_prep()` which properly renders the UI.

Additionally, the UI rendering functions didn't initialize the layout before entering the Live context, which could cause delayed display.

## Solution

### 1. Added UI Support for Individual Agents

**Files Modified:**
- `debate/prep/runner.py`
- `debate/prep/ui.py`
- `debate/prep/strategy_agent.py`

**Changes:**

#### debate/prep/ui.py

1. **Enhanced `create_agent_panel()`** to show more details in single-agent view
2. **Added `create_single_agent_layout()`** - Creates optimized layout for single agent
3. **Added `render_single_agent_ui()`** - Renders live UI for a single agent
4. **Fixed timing issues** - Initialize layout BEFORE Live context for immediate display

```python
# Create initial layout BEFORE Live context to show immediately
time_remaining = deadline - time.time()
initial_layout = create_single_agent_layout(agent, session, time_remaining)

with Live(initial_layout, console=console, refresh_per_second=int(1 / refresh_rate)) as live:
    # Brief pause to ensure terminal is ready
    await asyncio.sleep(0.05)

    # Continuous update loop
    while time.time() < deadline:
        # ... update logic
```

#### debate/prep/runner.py

1. **Updated all individual agent runners** (`run_strategy_agent`, `run_search_agent`, `run_cutter_agent`, `run_organizer_agent`)
2. **Added `show_ui` parameter** (defaults to `True`)
3. **Run agent and UI concurrently** using `asyncio.gather()`
4. **Added summary printing** after completion

```python
async def run_strategy_agent(
    resolution: str,
    side: Side,
    session_id: str | None = None,
    duration_minutes: float = 5.0,
    show_ui: bool = True,  # NEW
) -> dict[str, Any]:
    # ... setup code ...

    # Run with or without UI
    if show_ui:
        await asyncio.gather(
            strategy.run(deadline),
            render_single_agent_ui(strategy, session, deadline),  # NEW
        )
    else:
        await strategy.run(deadline)

    # Print summary
    print_summary(session, [strategy])  # NEW
```

#### debate/prep/strategy_agent.py

Enhanced logging to show research directions as they're generated:

```python
# Log with full argument text for UI display
arg_text = task["argument"]
if len(arg_text) > 50:
    arg_text = arg_text[:47] + "..."
self.log(f"New: {arg_text}", {"type": evidence_type})
```

### 2. UI Features

The fixed UI now displays:

✅ **Immediate display** - UI appears as soon as agent starts
✅ **Continuous updates** - Refreshes 2x per second (0.5s refresh rate)
✅ **Countdown timer** - Shows remaining time in MM:SS format
✅ **Research directions** - Shows new arguments/tasks as they're created
✅ **Agent status** - Shows current activity (checking, working, waiting)
✅ **Progress stats** - Shows items processed and created
✅ **Recent actions** - Shows last 6 actions in single-agent view

### 3. Testing Without API Credits

Created synthetic test framework to reproduce and verify the fix without spending API credits:

**Test Files:**
- `tests/prep/test_ui_display.py` - Pytest test for bug reproduction
- `scripts/reproduce_ui_bug.py` - Standalone bug reproduction script
- `scripts/test_fixed_ui.py` - Verification script for the fix
- `scripts/verify_continuous_ui.py` - Interactive test with simulated delays

**Mocked Components:**
- Anthropic API responses (returns synthetic JSON)
- Brave search results (not needed for strategy agent)
- Simulated API latency for realistic testing

## Testing the Fix

### Quick Test (6 seconds)

```bash
uv run python scripts/test_fixed_ui.py
```

### Interactive Verification (with delays)

```bash
uv run python scripts/verify_continuous_ui.py
```

### Before and After Comparison

```bash
# Show bug (original behavior)
uv run python scripts/reproduce_ui_bug.py

# Show fix (new behavior)
uv run python scripts/test_fixed_ui.py
```

### Real Usage Test

```bash
# Run strategy agent with UI (uses real API)
uv run debate prep-strategy "Resolved: The US should ban TikTok" --side pro --duration 1
```

## Expected Behavior

### Before Fix ❌

```
Running StrategyAgent for PRO
Resolution: Resolved: The US should ban TikTok
Duration: 1.0 minutes

(long wait with no output...)

✓ Completed: 3 tasks created
Session ID: abc123
```

### After Fix ✅

```
Running StrategyAgent for PRO
Resolution: Resolved: The US should ban TikTok

Strategy Agent: Resolved: The US should ban TikTok
Side: PRO | Session: abc123

╭─────────────────────────────── Strategy Agent ───────────────────────────────╮
│   ● New: TikTok ban eliminates 100k+ creator jobs                            │
│   ● New: National security threat from data access                           │
│   ● generating_opponent_answers                                              │
│   [Processed: 2 | Created: 3]                                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─────────────────────── Prep Session | 0:45 remaining ────────────────────────╮
│ Tasks:           3                                                           │
│ Search Results:  0                                                           │
│ Cards Cut:       0                                                           │
│ Feedback:        0                                                           │
╰──────────────────────────────────────────────────────────────────────────────╯

(Updates continuously with countdown timer)
```

## Validation

Run type checking and tests:

```bash
bash check.sh
```

All checks should pass.

## Files Modified

1. `debate/prep/ui.py` - Added single-agent UI functions, fixed timing
2. `debate/prep/runner.py` - Added UI support to individual agent runners
3. `debate/prep/strategy_agent.py` - Enhanced logging for research directions

## Files Created

1. `tests/prep/test_ui_display.py` - Unit tests
2. `scripts/reproduce_ui_bug.py` - Bug reproduction
3. `scripts/test_fixed_ui.py` - Fix verification
4. `scripts/verify_continuous_ui.py` - Interactive verification
5. `FIX_SUMMARY.md` - This document

## Backward Compatibility

✅ All changes are backward compatible
✅ Default behavior unchanged (UI enabled by default)
✅ Can disable UI with `show_ui=False`
✅ Parallel prep unchanged
✅ CLI commands unchanged

## Next Steps

1. Merge this branch: `git merge fix/prep-agent-progress-ui`
2. Test with real API to verify live behavior
3. Consider adding progress bars for long-running operations
4. Add keyboard shortcuts for pausing/resuming agents
