# Search Agent Improvements Plan

## Problem Statement

Strategy agent generates ~100 research tasks per 30s, but search agent only completes 1-2. Current bottlenecks:
- Sequential URL fetches (10 URLs × 0.5s delay = 5s+ per task)
- LLM query generation (~1.5s per task, one call per task)
- No task prioritization (stock arguments may not get researched)
- No visibility into actual work done (UI shows "2 results" when 12 articles fetched)

Brave API rate limit is 1 req/sec (free tier), which is NOT the bottleneck.

---

## Design Decisions

| Question | Decision |
|----------|----------|
| Early termination? | **No.** Do post-timer fetches instead. Harvest URLs during timer, fetch after. |
| Priority ratio? | **4:1 stock:non-stock.** Interleave to ensure coverage. |
| Parallel fetch limit? | **Cap at 3**, make configurable. |
| Batch query generation? | **Yes.** Use streaming parsing like strategy agent. Persist for resume. |
| Same-domain URLs? | **Skip duplicates** from same domain (take first only). |
| Partial fetch failure? | **Accept successes, move on.** Don't retry failures. |

---

## Improvement 1: Strategy Agent - Add `arg_type` Field

**Files:** `debate/prep/strategy_agent.py`

**Problem:** Current `source` and `priority` fields are not useful for prioritization. Need explicit argument type.

**Changes:**

1. Add `arg_type` field to task generation with values: `stock`, `creative`, `niche`, `opportunistic`
2. Remove unused `source` field from task JSON
3. Remove unused `priority` field from task JSON

**Task format before:**
```json
{
  "id": "a1b2c3",
  "argument": "TikTok ban eliminates creator jobs",
  "evidence_type": "support",
  "source": "enumerate_support",
  "priority": "high",
  "ts": 1234567890
}
```

**Task format after:**
```json
{
  "id": "a1b2c3",
  "argument": "TikTok ban eliminates creator jobs",
  "evidence_type": "support",
  "arg_type": "stock",
  "ts": 1234567890
}
```

---

## Improvement 2: Priority Queue (4:1 Stock Ratio)

**File:** `debate/prep/session.py`

**Current behavior:** `get_pending_tasks()` returns tasks in glob order (arbitrary).

**New behavior:** Interleave 4 stock tasks for every 1 non-stock task.

```python
def get_pending_tasks(self) -> list[dict]:
    """Get pending tasks with 4:1 stock:non-stock interleaving."""
    tasks = self._load_pending_tasks()

    # Separate by arg_type
    stock = [t for t in tasks if t.get("arg_type") == "stock"]
    non_stock = [t for t in tasks if t.get("arg_type") != "stock"]

    # Interleave 4:1
    result = []
    stock_idx = 0
    non_stock_idx = 0

    while stock_idx < len(stock) or non_stock_idx < len(non_stock):
        # Add up to 4 stock tasks
        for _ in range(4):
            if stock_idx < len(stock):
                result.append(stock[stock_idx])
                stock_idx += 1
        # Add 1 non-stock task
        if non_stock_idx < len(non_stock):
            result.append(non_stock[non_stock_idx])
            non_stock_idx += 1

    return result
```

**Impact:** Stock arguments always prioritized. Creative/niche/opportunistic still get researched.

---

## Improvement 3: Streaming Batch Query Generation

**Files:** `debate/prep/search_agent.py`, new `debate/prep/query_generator.py`

**Current behavior:** One LLM call per task for query generation.

**New behavior:**
- Stream-generate queries for batches of 10 tasks
- Parse queries as they stream (like strategy agent's `_stream_tags()`)
- Persist generated queries to `staging/{session_id}/search/queries/query_{task_id}.json`
- On resume, load existing queries instead of regenerating
- Show 10 most recent queries in UI

**Query persistence format:**
```json
{
  "task_id": "a1b2c3",
  "argument": "TikTok ban eliminates creator jobs",
  "query": "TikTok ban creator economy job losses 2024 2025",
  "ts": 1234567890
}
```

**Streaming prompt:**
```
Generate targeted search queries for these debate arguments.
Output one query per line in format: TASK_ID|QUERY

Arguments:
- a1b2c3: TikTok ban eliminates creator jobs
- d4e5f6: Chinese government accesses user data
...
```

**UI display:** Show 10 most recent queries in search agent panel (similar to strategy agent's recent arguments).

---

## Improvement 4: Parallel URL Fetches

**Files:** `debate/prep/search_agent.py`

**Leverage existing infrastructure:** `debate/article_fetcher.py` already has `fetch_all_sources_async()` with `asyncio.gather()`.

**Changes:**

1. Use `fetch_all_sources_async()` instead of sequential loop
2. Add configurable concurrency limit (default: 3)
3. Deduplicate URLs by domain (take first URL per domain)
4. Accept partial successes (don't retry failures)

```python
# Config
PARALLEL_FETCH_LIMIT = 3  # Make configurable

# Deduplicate by domain
def _dedupe_by_domain(urls: list[str]) -> list[str]:
    """Take first URL from each domain."""
    seen_domains = set()
    result = []
    for url in urls:
        domain = urlparse(url).netloc
        if domain not in seen_domains:
            seen_domains.add(domain)
            result.append(url)
    return result

# In process_item:
urls = _dedupe_by_domain(search_result_urls)[:PARALLEL_FETCH_LIMIT]
results = await fetch_all_sources_async(urls)
# Accept whatever succeeded, move on
sources = [r for r in results if r.get("success")]
```

**Impact:** Fetch phase drops from ~5s to ~1-2s per task.

---

## Improvement 5: Post-Timer Fetch Phase

**Files:** `debate/prep/search_agent.py`, `debate/prep/ui.py`, `debate/prep/orchestrator.py` (if exists)

**Concept:** Separate the work into two phases:
1. **Timed phase:** Query generation + Brave searches (collect URLs)
2. **Post-timer phase:** Fetch all collected URLs (no time pressure)

**Implementation:**

1. During timed phase:
   - Generate queries (streaming batch)
   - Execute Brave searches (1 req/sec)
   - Collect URLs into a pool (don't fetch yet, or fetch in parallel opportunistically)

2. After timer expires:
   - UI shows "⏳ Fetching collected URLs..."
   - Fetch all URLs from pool with parallel fetches
   - No time pressure, can take as long as needed

**URL pool storage:**
```
staging/{session_id}/search/url_pool.json
```

```json
{
  "urls": [
    {"task_id": "a1b2c3", "url": "https://...", "title": "..."},
    ...
  ],
  "collected_at": 1234567890
}
```

**UI indication:**
```
┌─ Search Agent ─────────────────────────┐
│ ⏳ Post-timer: Fetching 47 URLs...     │
│ Progress: 12/47 fetched                │
│ Sources: 8 success, 4 failed           │
└────────────────────────────────────────┘
```

---

## Improvement 6: UI - Sources Fetched + Recent Queries

**File:** `debate/prep/base_agent.py`

Add counters to AgentState:
```python
@dataclass
class AgentState:
    # ... existing fields ...
    sources_fetched: int = 0
    sources_failed: int = 0
    urls_collected: int = 0
    recent_queries: list[str] = field(default_factory=list)  # Last 10
```

**File:** `debate/prep/ui.py`

Search agent panel shows:
```
┌─ Search Agent ─────────────────────────┐
│ 🔍 Researching: TikTok ban impacts     │
│                                        │
│ Recent queries:                        │
│   📎 tiktok ban creator jobs 2024      │
│   📎 chinese government data access    │
│   📎 bytedance national security       │
│   ... (up to 10)                       │
│                                        │
│ URLs: 23 collected | Sources: 8 (2 ✗)  │
└────────────────────────────────────────┘
```

Stats panel shows:
```
Tasks Generated:    100
URLs Collected:     47
Sources Fetched:    12 (4 failed)
Cards Cut:          8
```

---

## Implementation Order

| Order | Improvement | Complexity | Dependencies | Status |
|-------|-------------|------------|--------------|--------|
| 1 | Strategy agent: add `arg_type`, remove `source`/`priority` | Low | None | ✅ Done |
| 2 | Session: 4:1 priority interleaving | Low | #1 | ✅ Done |
| 3 | UI: sources fetched counter | Low | None | ✅ Done |
| 4 | Parallel fetches (use existing infra) | Medium | None | ✅ Done |
| 5 | Query caching for resume | Medium | None | ✅ Done |
| 6 | UI: recent queries display | Low | #5 | ✅ Done |
| 7 | Post-timer fetch phase | High | #4, #5 | 🔮 Future |

**Note:** Post-timer fetch phase requires significant architectural changes to separate
query/search from fetch phases. Deferred to future implementation.

---

## Files to Modify

| File | Changes |
|------|---------|
| `debate/prep/strategy_agent.py` | Add `arg_type` field, remove `source`/`priority` |
| `debate/prep/session.py` | Add 4:1 priority interleaving to `get_pending_tasks()` |
| `debate/prep/search_agent.py` | Streaming batch queries, parallel fetches, post-timer phase |
| `debate/prep/base_agent.py` | Add `sources_fetched`, `urls_collected`, `recent_queries` to AgentState |
| `debate/prep/ui.py` | Show sources counter, recent queries, post-timer indication |
| `debate/prep/orchestrator.py` | Coordinate post-timer fetch phase (if needed) |

---

## Expected Impact

| Metric | Before | After (Implemented) |
|--------|--------|---------------------|
| Time per task | ~10-15s | ~3-5s (parallel fetches) |
| Tasks in 30s | ~2-3 | ~6-10 |
| Stock coverage | Random | 80% guaranteed (4:1 ratio) |
| User visibility | "2 results" | "Sources: 12 (4 failed)" |
| Resume support | None | Cached queries persist |

**Future (post-timer phase):**

| Metric | Current | With Post-Timer |
|--------|---------|-----------------|
| URLs collected in 30s | ~15-20 | ~50-75 |
| Total sources fetched | ~10-15 | ~30-50 |
