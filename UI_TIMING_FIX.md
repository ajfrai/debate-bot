# UI Timing Fix - Shows During Execution

## The Real Bug

The UI was NOT appearing during execution. It only showed at the very end after all work completed. This was because:

### Root Cause

1. **Event Loop Blocking**: The Anthropic API client uses **synchronous** calls (`client.messages.create()`), which blocks the entire asyncio event loop
2. **Task Scheduling**: When using `asyncio.gather(agent.run(), render_ui())`, both tasks start simultaneously, but:
   - Agent task makes blocking sync API call
   - Event loop is blocked - can't schedule UI rendering
   - UI rendering task never gets CPU time
   - By the time API call finishes, agent is done
   - UI finally renders but shows only final state

### The Fix

**Three-part solution:**

#### 1. Start UI Task FIRST (runner.py)

```python
# BEFORE (buggy - simultaneous start):
await asyncio.gather(
    strategy.run(deadline),
    render_single_agent_ui(strategy, session, deadline),
)

# AFTER (fixed - UI starts first):
ui_task = asyncio.create_task(render_single_agent_ui(strategy, session, deadline))
await asyncio.sleep(0.1)  # Let UI initialize
agent_task = asyncio.create_task(strategy.run(deadline))
await asyncio.gather(ui_task, agent_task)
```

**Why this helps:** UI task gets scheduled and starts rendering before agent makes any blocking calls.

#### 2. Run Sync API Calls in Thread Pool (strategy_agent.py)

```python
# BEFORE (buggy - blocks event loop):
response = self._get_client().messages.create(
    model=model,
    max_tokens=512,
    messages=[{"role": "user", "content": prompt}],
)

# AFTER (fixed - doesn't block):
response = await asyncio.to_thread(
    self._get_client().messages.create,
    model=model,
    max_tokens=512,
    messages=[{"role": "user", "content": prompt}],
)
```

**Why this works:** `asyncio.to_thread()` runs the blocking call in a thread pool, allowing the event loop to continue scheduling other tasks (like UI rendering) while the API call runs.

#### 3. Initialize Layout Before Live Context (ui.py)

```python
# Create initial layout BEFORE Live context to show immediately
time_remaining = deadline - time.time()
initial_layout = create_single_agent_layout(agent, session, time_remaining)

with Live(initial_layout, console=console, ...) as live:
    await asyncio.sleep(0.05)  # Ensure terminal ready
    while time.time() < deadline:
        # ... update loop
```

**Why this helps:** Layout is created and passed to Live() constructor, ensuring immediate display when Live context starts.

## Verification

### Quick Test (6 seconds)

```bash
uv run python scripts/test_fixed_ui.py
```

**What to observe:**
- UI appears within 0.5 seconds ✅
- Shows "generating_initial_arguments" status
- "New: [argument]" messages appear as tasks are created
- Countdown timer updates continuously

### Live Test with Slow API Calls (10 seconds)

```bash
uv run python scripts/debug_ui_timing.py
```

**What to observe:**
- UI appears immediately (< 1 second) ✅
- Countdown timer decrements: 10 → 9 → 8 → ... ✅
- Agent status changes: starting → checking → working ✅
- New research directions appear progressively ✅
- **UI keeps updating DURING API calls** (doesn't freeze) ✅

### Real Test with API

```bash
uv run debate prep-strategy "Resolved: The US should ban TikTok" --side pro --duration 1
```

**Expected:** Same behavior as synthetic tests but with real API calls.

## Technical Details

### Event Loop Scheduling

**Before (broken):**
```
1. asyncio.gather() starts both tasks
2. Agent task: calls sync API → BLOCKS event loop
3. UI task: waiting for CPU time, can't run
4. API call finishes (2 seconds later)
5. Agent task: continues, creates tasks, finishes
6. UI task: FINALLY gets CPU, renders once, shows final state
```

**After (fixed):**
```
1. UI task created and started
2. Sleep 0.1s (UI initializes and starts rendering)
3. Agent task created and started
4. Agent: calls API via asyncio.to_thread()
   - API runs in thread pool (doesn't block event loop)
5. UI task: continues rendering, updates every 0.5s
6. Both tasks run concurrently ✅
```

### Why asyncio.to_thread() Works

```python
# Synchronous call (blocks):
result = sync_function()  # Event loop stuck here

# Async wrapper (doesn't block):
result = await asyncio.to_thread(sync_function)
# Event loop free to schedule other tasks while sync_function runs in thread
```

## Files Modified

1. **debate/prep/runner.py**
   - All 4 individual agent runners
   - Start UI task first with 0.1s delay
   - Then start agent task

2. **debate/prep/strategy_agent.py**
   - Import asyncio
   - Wrap API calls with `asyncio.to_thread()`

3. **debate/prep/ui.py**
   - Initialize layout before Live context
   - Add 0.05s pause after Live starts

## Validation

All tests pass:
- Type checking (mypy) ✅
- Linting (ruff) ✅
- Formatting ✅
- Tests (pytest) 15/15 ✅

## Impact

**Before:**
```
$ uv run debate prep-strategy "..." --side pro --duration 1

(blank screen for 60 seconds)

✓ Completed: 5 tasks created
```

**After:**
```
$ uv run debate prep-strategy "..." --side pro --duration 1

Strategy Agent: Resolved: ...
Side: PRO | Session: abc123

╭───────── Strategy Agent ─────────╮
│   ● New: Economic harm...        │  <- Appears immediately
│   ● New: Security threat...      │  <- Updates in real-time
│   [Processed: 2 | Created: 3]   │  <- Live counter
╰──────────────────────────────────╯
╭── Prep Session | 0:45 remaining ─╮  <- Countdown updates
│ Tasks:  3 | Results: 0           │  <- Live metrics
╰──────────────────────────────────╯

(Updates continuously until time expires)
```

## Commits

1. `d2ce1a5` - Initial UI support (added render functions, but didn't fix timing)
2. `5774093` - **Critical fix** - Start UI first, use asyncio.to_thread()
3. `522bb78` - Updated verification test
