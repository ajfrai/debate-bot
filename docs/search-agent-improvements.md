# Search Agent Improvements Plan

## Problem Statement

Strategy agent generates ~100 research tasks per 30s, but search agent only completes 1-2. Current bottlenecks:
- Sequential URL fetches (10 URLs × 0.5s delay = 5s+ per task)
- LLM query generation (~1.5s per task)
- No task prioritization (stock arguments may not get researched)

Brave API rate limit is 1 req/sec (free tier), which is NOT the bottleneck.

---

## Improvement 1: Parallel URL Fetches

**File:** `debate/prep/search_agent.py`

**Current behavior (lines 192-273):**
```python
for url in urls_to_try:
    # Sequential fetch with 0.5s delay each
    await asyncio.sleep(self.fetch_delay)
    result = await asyncio.to_thread(self._fetch_article, url)
```

**New behavior:**
```python
async def _fetch_with_delay(self, url: str, delay: float) -> dict:
    """Fetch a single URL with staggered delay."""
    await asyncio.sleep(delay)
    return await asyncio.to_thread(self._fetch_article, url)

# In process_item:
fetch_tasks = [
    self._fetch_with_delay(url, i * 0.2)  # Stagger by 0.2s
    for i, url in enumerate(urls_to_try[:5])  # Limit to 5 concurrent
]
results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
```

**Impact:** Fetch phase drops from ~5s to ~1-2s per task (~3x faster)

---

## Improvement 2: Early Termination on Success

**File:** `debate/prep/search_agent.py`

**Current behavior:** Fetches ALL URLs from search results.

**New behavior:** Stop after N successful fetches with sufficient content.

```python
MIN_GOOD_SOURCES = 2
MIN_WORD_COUNT = 300

# After processing fetch results:
good_sources = [s for s in sources if s.get("word_count", 0) >= MIN_WORD_COUNT]
if len(good_sources) >= MIN_GOOD_SOURCES:
    break  # Don't fetch remaining URLs
```

**Impact:** Skip unnecessary fetches, ~2x faster on successful searches

---

## Improvement 3: Priority Queue (Stock First)

**File:** `debate/prep/session.py`

**Current behavior:** `get_pending_tasks()` returns tasks in glob order (arbitrary).

**New behavior:** Sort tasks by priority before returning.

```python
def _task_priority(self, task: dict) -> tuple:
    """Return sort key (lower = higher priority)."""
    source = task.get("source", "")

    # Priority 1: Stock arguments (most important)
    is_stock = "STOCK" in source or "stock" in source

    # Priority 2: Base tasks before variants
    is_variant = "variant" in source

    # Priority 3: Phase order (initial > impact > deep_dive)
    phase_order = {
        "initial": 0,
        "impact": 1,
        "deep": 2,
        "opponent": 3,
    }
    phase = 2  # default
    for key, val in phase_order.items():
        if key in source:
            phase = val
            break

    return (not is_stock, is_variant, phase)

def get_pending_tasks(self) -> list[dict]:
    tasks = self._load_pending_tasks()
    return sorted(tasks, key=self._task_priority)
```

**Impact:** Ensures critical stock arguments researched first within time budget.

---

## Improvement 4: Batch Query Generation

**File:** `debate/prep/search_agent.py`

**Current behavior:** One LLM call per task for query generation (~1.5s each).

**New behavior:** Batch 5-10 tasks into one LLM call.

```python
async def _generate_queries_batch(self, tasks: list[dict]) -> dict[str, str]:
    """Generate search queries for multiple tasks at once."""
    arguments = [t["argument"] for t in tasks]

    prompt = f"""Generate a focused search query for each argument.
Return as JSON: {{"argument": "query", ...}}

Arguments:
{chr(10).join(f'- {arg}' for arg in arguments)}
"""

    response = await self._call_llm(prompt)
    return json.loads(response)

# In check_for_work or process loop:
pending = self.session.get_pending_tasks()[:10]
if len(pending) >= 3:
    queries = await self._generate_queries_batch(pending)
    # Cache queries for use in process_item
    for task in pending:
        self._query_cache[task["id"]] = queries.get(task["argument"])
```

**Impact:** Reduces LLM overhead from ~15s (10 tasks) to ~2s (1 batch call).

---

## Improvement 5: UI - Show Sources Fetched Count

**File:** `debate/prep/base_agent.py`

Add counter to AgentState:
```python
@dataclass
class AgentState:
    # ... existing fields ...
    sources_fetched: int = 0
    sources_failed: int = 0
```

**File:** `debate/prep/search_agent.py`

Increment on fetch (around line 228):
```python
if fetch_result.get("success"):
    self.state.sources_fetched += 1
else:
    self.state.sources_failed += 1
```

**File:** `debate/prep/ui.py`

Update stats panel (lines 257-276):
```python
def create_stats_panel(session: "PrepSession", time_remaining: float, agents: list["BaseAgent"] = None) -> Panel:
    stats = session.get_stats()

    # Get sources count from search agent
    sources_fetched = 0
    sources_failed = 0
    if agents:
        for agent in agents:
            if agent.name == "search":
                sources_fetched = agent.state.sources_fetched
                sources_failed = agent.state.sources_failed

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left")
    table.add_column(justify="right")

    table.add_row("Tasks Generated:", str(stats["tasks"]))
    table.add_row("Sources Fetched:", f"{sources_fetched} ({sources_failed} failed)")
    table.add_row("Cards Cut:", str(stats["cards"]))
```

**Impact:** User sees meaningful progress (12 sources fetched) instead of discouraging "2 tasks completed".

---

## Implementation Order

1. **UI fix (Improvement 5)** - Quick win, immediate visibility improvement
2. **Early termination (Improvement 2)** - Simple change, good impact
3. **Parallel fetches (Improvement 1)** - Moderate complexity, high impact
4. **Priority queue (Improvement 3)** - Moderate complexity, quality improvement
5. **Batch query gen (Improvement 4)** - More complexity, good impact

---

## Expected Combined Impact

| Metric | Before | After |
|--------|--------|-------|
| Time per task | ~10-15s | ~3-5s |
| Tasks in 30s | ~2-3 | ~6-10 |
| Stock coverage | Random | Guaranteed first |
| User visibility | "2 results" | "15 sources fetched" |
