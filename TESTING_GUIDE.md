# Testing the Prep Agent UI Fix

## Quick Start

### 1. Test Without API Credits (Recommended First)

Run the synthetic test to verify the fix without spending API credits:

```bash
# Quick test (6 seconds)
uv run python scripts/test_fixed_ui.py
```

**What you should see:**
- UI appears immediately
- Countdown timer updates continuously (6 seconds → 0)
- New research directions appear:
  - "New: TikTok ban eliminates 100k+ creator jobs"
  - "New: National security threat from data access"
  - "New: AT: Privacy protections sufficient"
- Agent status updates in real-time
- Final summary with statistics

### 2. Interactive Verification (With Simulated Delays)

For a more realistic test with API call simulation:

```bash
uv run python scripts/verify_continuous_ui.py
```

This test:
- Simulates API latency (0.5s per call)
- Runs for ~6 seconds
- Shows UI updating as responses arrive
- Helps verify continuous updates

### 3. Reproduce Original Bug (Before Fix)

To see what the bug looked like:

```bash
uv run python scripts/reproduce_ui_bug.py
```

This compares:
- **TEST 1**: Individual agent (simulating old buggy behavior)
- **TEST 2**: Parallel prep (working before the fix)

### 4. Test With Real API (Uses Credits)

To test with actual Anthropic API:

```bash
# Strategy agent only (cheapest)
uv run debate prep-strategy "Resolved: The US should ban TikTok" --side pro --duration 0.5

# Search agent (requires existing session)
uv run debate prep-search "Resolved: The US should ban TikTok" --side pro --session <session_id> --duration 0.5

# Cutter agent (requires existing session with search results)
uv run debate prep-cutter "Resolved: The US should ban TikTok" --side pro --session <session_id> --duration 0.5

# Organizer agent (requires existing session with cards)
uv run debate prep-organizer "Resolved: The US should ban TikTok" --side pro --session <session_id> --duration 0.5
```

## What to Look For

### ✅ Fixed Behavior

1. **Immediate UI Display**
   - UI appears as soon as command runs
   - No blank screen or waiting period
   - Header shows immediately with resolution and session ID

2. **Continuous Updates**
   - UI refreshes every 0.5 seconds
   - Countdown timer decrements smoothly
   - Agent status changes in real-time

3. **Research Directions**
   - Strategy agent shows "New: [argument]" as tasks are created
   - Recent actions panel shows last 6 actions
   - Phase information displayed (generating_initial_arguments, etc.)

4. **Countdown Timer**
   - Displayed in footer panel
   - Format: "M:SS remaining"
   - Updates continuously until 0:00

5. **Agent Status**
   - Shows current status with symbols:
     - ● (green) = working
     - ○ (yellow) = checking
     - ◌ (blue) = waiting
     - ◐ (cyan) = starting
     - ■ (red) = stopped

### ❌ Bug Symptoms (If Still Present)

If you see any of these, the fix didn't work:
- Blank screen during execution, output only at end
- UI appears but doesn't update
- No countdown timer
- No research directions shown
- Only final statistics displayed

## Testing Checklist

Before merging this branch, verify:

- [ ] Individual strategy agent shows UI
- [ ] Individual search agent shows UI (with existing session)
- [ ] Individual cutter agent shows UI (with existing session)
- [ ] Individual organizer agent shows UI (with existing session)
- [ ] Parallel prep still works (4-panel layout)
- [ ] Countdown timer displays and updates
- [ ] Research directions appear in strategy agent
- [ ] UI appears immediately, not at end
- [ ] UI updates continuously during execution
- [ ] All validation checks pass (`bash check.sh`)

## Run Validation

Always run validation before committing:

```bash
bash check.sh
```

Should show:
```
✓ Type checking passed
✓ Linting passed
✓ Formatting check passed
✓ Syntax check passed
✓ Tests passed
✓ All checks passed!
```

## Troubleshooting

### Issue: UI still doesn't show

**Check:**
1. Are you on the `fix/prep-agent-progress-ui` branch?
   ```bash
   git branch --show-current
   ```

2. Are all changes pulled?
   ```bash
   git status
   ```

3. Is the environment up to date?
   ```bash
   uv sync
   ```

### Issue: UI shows at end, not during execution

This was fixed by initializing the layout before the Live context. Check:
1. Is `debate/prep/ui.py` updated with the fix?
2. Look for `initial_layout = create_single_agent_layout(...)` before `with Live(...)`

### Issue: No research directions shown

Check:
1. Is `debate/prep/strategy_agent.py` updated?
2. Look for enhanced logging: `self.log(f"New: {arg_text}", ...)`

### Issue: Tests fail

Run:
```bash
uv run pytest tests/prep/test_ui_display.py -v
```

All 3 tests should pass:
- `test_strategy_agent_no_ui` (UI disabled)
- `test_strategy_agent_with_ui` (UI enabled)
- `test_parallel_prep_has_ui` (parallel mode)

## Performance Notes

- UI refresh rate: 0.5 seconds (2 FPS)
- Minimal performance impact
- Same behavior in parallel and individual modes
- Can disable with `show_ui=False` if needed

## Next Steps After Verification

1. Merge to main:
   ```bash
   git checkout main
   git merge fix/prep-agent-progress-ui
   ```

2. Test in production environment

3. Consider future enhancements:
   - Progress bars for long operations
   - Keyboard shortcuts for pause/resume
   - More detailed metrics display
   - Log streaming to file
