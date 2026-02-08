"""SearchAgent: Writes search queries and stages results."""

import asyncio
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import anthropic

from debate.article_fetcher import FetchedArticle, fetch_source
from debate.config import Config
from debate.prep.base_agent import BaseAgent
from debate.prep.session import PrepSession
from debate.research_agent import _brave_search, _extract_urls_from_search_results


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    return (prompts_dir / f"{name}.md").read_text()


# Configurable parallel fetch limit
PARALLEL_FETCH_LIMIT = 3


class SearchAgent(BaseAgent):
    """Generates search queries and fetches article content.

    Responsibilities:
    - Read research tasks from StrategyAgent
    - Generate targeted search queries (LLM responsibility ends here)
    - Execute searches via Brave API
    - Fetch top article content
    - Stage results for CutterAgent

    Token efficiency:
    - LLM only generates query (~20 tokens output)
    - Everything else is algorithmic
    """

    def __init__(self, session: PrepSession, parallel_fetch_limit: int = PARALLEL_FETCH_LIMIT) -> None:
        super().__init__(session, poll_interval=2.0)
        self._client: anthropic.Anthropic | None = None
        self._last_search_time: float = 0.0
        self._search_delay: float = 1.0  # Brave Free: 1 req/sec (was 3.0s - too conservative!)
        self._parallel_fetch_limit: int = parallel_fetch_limit  # Max concurrent fetches
        self._query_cache: dict[str, str] = {}  # task_id -> query
        self._queries_dir = self.session.staging_dir / "search" / "queries"
        self._queries_dir.mkdir(parents=True, exist_ok=True)
        self._load_cached_queries()

    @staticmethod
    def _dedupe_urls_by_domain(urls: list[str]) -> list[str]:
        """Take first URL from each domain to avoid rate limiting single sites.

        Args:
            urls: List of URLs to deduplicate

        Returns:
            List with at most one URL per domain
        """
        seen_domains: set[str] = set()
        result: list[str] = []
        for url in urls:
            domain = urlparse(url).netloc
            if domain not in seen_domains:
                seen_domains.add(domain)
                result.append(url)
        return result

    def _load_cached_queries(self) -> None:
        """Load previously generated queries from disk for resume support."""
        import json

        for query_file in self._queries_dir.glob("query_*.json"):
            try:
                data = json.loads(query_file.read_text())
                task_id = data.get("task_id", "")
                query = data.get("query", "")
                if task_id and query:
                    self._query_cache[task_id] = query
            except (json.JSONDecodeError, OSError):
                continue

    def _save_query(self, task_id: str, argument: str, query: str) -> None:
        """Save a generated query to disk for resume support."""
        import json

        data = {
            "task_id": task_id,
            "argument": argument,
            "query": query,
            "ts": time.time(),
        }
        query_path = self._queries_dir / f"query_{task_id}.json"
        query_path.write_text(json.dumps(data, indent=2))
        self._query_cache[task_id] = query

        # Update recent queries for UI display
        query_display = f"{query[:50]}..." if len(query) > 50 else query
        self.state.recent_queries.append(query_display)
        # Keep only last 10 queries
        if len(self.state.recent_queries) > 10:
            self.state.recent_queries = self.state.recent_queries[-10:]

    def _get_cached_query(self, task_id: str) -> str | None:
        """Get a cached query for a task if it exists."""
        return self._query_cache.get(task_id)

    @property
    def name(self) -> str:
        return "search"

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create Anthropic client."""
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    async def check_dependencies(self) -> tuple[bool, str]:
        """Check if StrategyAgent has created any tasks."""
        tasks_dir = self.session.staging_dir / "strategy" / "tasks"

        if not tasks_dir.exists():
            return (
                False,
                "No tasks directory found. Run StrategyAgent first to create research tasks.",
            )

        task_files = list(tasks_dir.glob("*.json"))
        if not task_files:
            return (
                False,
                "No research tasks found. Run StrategyAgent first to generate tasks.",
            )

        return (True, "")

    async def check_for_work(self) -> list[Any]:
        """Check for pending research tasks and pre-generate queries in batches."""
        tasks = self.session.get_pending_tasks()

        # Mark new tasks as queued in kanban (but don't overwrite existing states)
        for task in tasks:
            task_id = task.get("id", "")
            if task_id and task_id not in self.state.task_stages:
                # Only set to queued if this is a genuinely new task
                # Don't overwrite existing error/done states
                self.state.task_stages[task_id] = "queued"

        # Pre-generate queries for all tasks that don't have cached queries
        # This uses streaming batch generation for high throughput
        if tasks:
            await self._batch_generate_queries(tasks, batch_size=20)

        return tasks

    async def process_item(self, task: dict[str, Any]) -> None:
        """Process a research task: generate query, search, fetch, stage."""
        task_id = task["id"]
        task_path = str(self.session.staging_dir / "strategy" / "tasks" / f"task_{task_id}.json")

        self.state.current_task_id = task_id
        self.state.current_task_progress = "starting"
        argument = task.get("argument", "")
        self.state.current_argument = argument  # Track argument for UI
        self.log("processing_task", {"task_id": task_id, "argument": argument[:40]})
        self.state.update(f"Running: {argument[:50]}", "working")

        # Initialize retry tracking if needed
        if task_id not in self.state.task_retries:
            self.state.task_retries[task_id] = 0
        if task_id not in self.state.task_urls_tried:
            self.state.task_urls_tried[task_id] = []

        # Clear from error column if retrying
        if task_id in self.state.task_errors:
            del self.state.task_errors[task_id]

        # Move to query stage
        self.state.task_stages[task_id] = "query"

        # Generate search query (modify if retrying)
        # Note: With batch generation, this should hit cache immediately for most tasks
        self.state.current_task_progress = "generating_query"
        try:
            retry_count = self.state.task_retries.get(task_id, 0)
            query = await self._generate_query(task, retry_attempt=retry_count)
            if not query:
                await self._handle_error(task_id, "Query generation failed", task)
                return
        except Exception as e:
            await self._handle_error(task_id, f"Query error: {str(e)[:40]}", task)
            return

        self.log(
            "query_generated",
            {
                "task_id": task_id,
                "argument": task.get("argument", "")[:50],
                "search_intent": task.get("search_intent", "")[:50],
                "query": query,
            },
        )
        self.state.current_query = query
        self.state.current_task_progress = "query_ok"
        self.state.update(f"Query: {query[:60]}", "working")

        # Rate limiting for Brave API calls
        # Only wait if we need to make a search API call
        time_since_last = time.time() - self._last_search_time
        if time_since_last < self._search_delay:
            wait_time = self._search_delay - time_since_last
            self.state.update(f"rate_limit_wait_{wait_time:.1f}s", "waiting")
            await asyncio.sleep(wait_time)

        # Execute search (check for fixture mode)
        from tests.fixtures import is_fixture_mode, mock_brave_search

        self.state.current_task_progress = "searching"
        # Move to search stage
        self.state.task_stages[task_id] = "search"
        self._last_search_time = time.time()

        try:
            if is_fixture_mode():
                # Run in thread to avoid blocking event loop (allows UI updates)
                search_results: str | None = await asyncio.to_thread(
                    mock_brave_search, query, num_results=20, quiet=True
                )
            else:
                # Run in thread to avoid blocking event loop (allows UI updates)
                search_results = await asyncio.to_thread(_brave_search, query, num_results=20, quiet=True)

            if not search_results:
                await self._handle_error(task_id, "Search returned no results", task)
                return
        except Exception as e:
            await self._handle_error(task_id, f"Search error: {str(e)[:40]}", task)
            return

        # Extract URLs and fetch articles
        urls = _extract_urls_from_search_results(search_results)
        brave_api_key = os.environ.get("BRAVE_API_KEY")

        self.log(
            "search_success",
            {
                "query": query,
                "urls_found": len(urls),
                "urls_to_fetch": len(urls),
            },
        )
        self.state.update(f"Searched: {len(urls)} results found", "working")

        # Filter out already-tried URLs
        urls_tried = self.state.task_urls_tried.get(task_id, [])
        urls = [u for u in urls if u not in urls_tried]

        if not urls:
            # All URLs from this search already tried - need new search
            await self._handle_error(task_id, "All URLs already tried", task)
            return

        # Dedupe by domain and limit to parallel fetch limit
        urls = self._dedupe_urls_by_domain(urls)
        urls_to_fetch = urls[: self._parallel_fetch_limit]

        from tests.fixtures import is_fixture_mode, mock_fetch_source

        # Move to fetch stage
        self.state.task_stages[task_id] = "fetch"
        num_to_fetch = len(urls_to_fetch)
        self.state.current_task_progress = f"fetch 0/{num_to_fetch}"
        self.state.update(f"Fetching {num_to_fetch} URLs in parallel...", "working")

        # Mark URLs as tried
        if task_id not in self.state.task_urls_tried:
            self.state.task_urls_tried[task_id] = []
        self.state.task_urls_tried[task_id].extend(urls_to_fetch)

        # Parallel fetch with semaphore for rate limiting
        async def fetch_one(url: str) -> tuple[str, FetchedArticle | None, str]:
            """Fetch a single URL and return (url, article, error_msg)."""
            try:
                if is_fixture_mode():
                    article = await asyncio.to_thread(mock_fetch_source, url)
                else:
                    article = await asyncio.to_thread(
                        fetch_source, url, retry_on_paywall=True, brave_api_key=brave_api_key, quiet=True
                    )
                if article:
                    return (url, article, "")
                return (url, None, "Paywall or failed to extract content")
            except Exception as e:
                return (url, None, str(e)[:80])

        # Fetch all in parallel
        self.log("parallel_fetch_start", {"urls": len(urls_to_fetch)})
        results = await asyncio.gather(*[fetch_one(url) for url in urls_to_fetch], return_exceptions=True)

        # Process results
        fetched_sources: list[dict[str, Any]] = []
        successful_fetches = 0

        for i, fetch_result in enumerate(results, 1):
            self.state.current_task_progress = f"fetch {i}/{num_to_fetch}"

            if isinstance(fetch_result, BaseException):
                failed_url = urls_to_fetch[i - 1]
                self.state.sources_failed += 1
                self.log("fetch_failed", {"url": failed_url, "reason": str(fetch_result)[:80]})
                fetched_sources.append(
                    {
                        "url": failed_url,
                        "title": None,
                        "full_text": None,
                        "fetch_status": "failed",
                        "error": str(fetch_result)[:80],
                    }
                )
                continue

            # Type is now narrowed to tuple[str, FetchedArticle | None, str]
            url, article, error_msg = fetch_result

            if article:
                successful_fetches += 1
                self.state.sources_fetched += 1
                title = article.title[:60] if article.title else "No title"
                self.log(
                    "fetch_success",
                    {
                        "url": article.url,
                        "title": title,
                        "word_count": article.word_count,
                    },
                )
                self.state.update(f"✓ {title} ({article.word_count:,} words)", "working")
                fetched_sources.append(
                    {
                        "url": article.url,
                        "title": article.title,
                        "full_text": article.full_text,
                        "word_count": article.word_count,
                        "fetch_status": "success",
                    }
                )
            else:
                self.state.sources_failed += 1
                self.log("fetch_failed", {"url": url, "reason": error_msg})
                fetched_sources.append(
                    {
                        "url": url,
                        "title": None,
                        "full_text": None,
                        "fetch_status": "failed",
                        "error": error_msg,
                    }
                )

        # Check if we got at least one successful fetch
        if successful_fetches == 0:
            await self._handle_error(task_id, "All fetches failed", task)
            return

        # Stage results
        self.state.current_task_progress = "staging"
        staged_result = {
            "task_id": task_id,
            "query": query,
            "argument": task.get("argument", ""),
            "search_intent": task.get("search_intent", ""),
            "evidence_type": task.get("evidence_type", "support"),
            "sources": fetched_sources,
        }

        self.session.write_search_result(staged_result)
        self.state.items_created += 1

        successful_sources = len([s for s in fetched_sources if s["fetch_status"] == "success"])
        failed_sources = len([s for s in fetched_sources if s["fetch_status"] == "failed"])
        self.log(
            "staged_result",
            {
                "task_id": task_id,
                "query": query,
                "sources_fetched": successful_sources,
                "sources_failed": failed_sources,
            },
        )

        # Mark as processed only after successful completion (idempotency)
        self.session.mark_processed("search", task_path)

        # Log completion with summary
        summary = f"✓ Complete: {argument[:40]} ({successful_sources} articles"
        if failed_sources > 0:
            summary += f", {failed_sources} failed"
        summary += ")"
        self.state.update(summary, "working")

        # Move to done stage
        self.state.task_stages[task_id] = "done"

        # Clear current task state
        self.state.current_task_id = ""
        self.state.current_task_progress = ""
        self.state.current_argument = ""
        self.state.current_query = ""
        self.state.current_source = ""

    async def _stream_queries(self, tasks: list[dict[str, Any]], batch_size: int = 20):
        """Stream queries from API call for multiple tasks at once.

        Uses streaming API to generate queries for a batch of tasks, yielding
        each (task_id, query) pair as it's parsed from the stream.

        Args:
            tasks: List of tasks to generate queries for
            batch_size: Number of tasks to include in one API call

        Yields:
            Tuples of (task_id, query) as they're parsed from the stream
        """
        if not tasks:
            return

        config = Config()
        model = config.get_agent_model("prep_search")

        # Build batch prompt
        task_lines = []
        for i, task in enumerate(tasks[:batch_size], 1):
            task_id = task.get("id", "")
            argument = task.get("argument", "")
            evidence_type = task.get("evidence_type", "support")
            task_lines.append(f"{i}. [{task_id}] {argument} (evidence: {evidence_type})")

        template = _load_prompt("search_query_batch")
        prompt = template.format(task_lines=chr(10).join(task_lines))

        buffer = ""
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _feed_queue():
            """Run sync stream in thread and feed chunks to queue."""

            def _sync_stream_to_queue():
                """Run streaming API call synchronously and feed queue."""
                with self._get_client().messages.stream(
                    model=model,
                    max_tokens=1024,  # Enough for ~20 queries
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    # Iterate in thread, feed chunks via thread-safe call
                    for chunk in stream.text_stream:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)

            loop = asyncio.get_running_loop()
            try:
                await asyncio.to_thread(_sync_stream_to_queue)
            finally:
                await queue.put(None)  # Signal end of stream

        # Start the queue feeder task
        feeder_task = asyncio.create_task(_feed_queue())

        try:
            current_task_idx = None
            # Process chunks as they arrive
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break  # End of stream

                buffer += chunk

                # Try to extract complete lines (queries) from buffer
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    parsed = self._parse_query_line(line, tasks, current_task_idx)
                    if parsed:
                        task_id, query, new_idx = parsed
                        if new_idx is not None:
                            current_task_idx = new_idx
                        if task_id and query:
                            yield (task_id, query)

            # Process any remaining buffer after stream ends
            if buffer.strip():
                parsed = self._parse_query_line(buffer, tasks, current_task_idx)
                if parsed:
                    task_id, query, new_idx = parsed
                    if task_id and query:
                        yield (task_id, query)
        except Exception as e:
            self.log("stream_queries_error", {"error": str(e)[:100], "tasks": len(tasks)})
            raise
        finally:
            await feeder_task

    def _parse_query_line(
        self, line: str, tasks: list[dict[str, Any]], current_task_idx: int | None = None
    ) -> tuple[str, str, int | None] | None:
        """Parse a query line from streaming output.

        Expects format:
        - "Task N:" to identify which task we're parsing
        - "- query text" for queries belonging to the current task

        Args:
            line: Line from stream
            tasks: List of tasks for matching
            current_task_idx: Current task index (0-based), or None

        Returns:
            (task_id, query, new_task_idx) tuple or None if invalid
            new_task_idx is updated if line is a "Task N:" header
        """
        line = line.strip()
        if not line:
            return None

        import re

        # Try to match "Task N:" format (with optional markdown # and text after colon)
        match = re.match(r"^#*\s*Task\s+(\d+):", line)
        if match:
            idx = int(match.group(1)) - 1  # Convert to 0-indexed
            if 0 <= idx < len(tasks):
                return ("", "", idx)  # Signal task switch
            return None

        # Try to match "- query text" format (bullet point)
        if line.startswith("-") and current_task_idx is not None:
            query = line[1:].strip()  # Remove leading "-"
            # Strip strategy label if present (e.g., "[Source Check]" at end)
            query = re.sub(r"\s*\[.*?\]\s*$", "", query)
            if 0 <= current_task_idx < len(tasks):
                task_id = tasks[current_task_idx].get("id", "")
                if task_id and query:
                    query = query.strip('"').strip("'").strip()
                    return (task_id, query, current_task_idx)

        return None

    async def _batch_generate_queries(self, tasks: list[dict[str, Any]], batch_size: int = 20) -> None:
        """Generate queries for multiple tasks in batches using streaming API.

        Generates queries for all tasks in batches, caching them for fast retrieval.
        Only generates queries for tasks that don't have cached queries yet.

        Args:
            tasks: List of tasks to generate queries for
            batch_size: Number of tasks per API call
        """
        # Filter out tasks that already have cached queries
        tasks_needing_queries = [t for t in tasks if not self._get_cached_query(t.get("id", ""))]

        if not tasks_needing_queries:
            return

        # Check if using fixtures - use single-query approach
        from tests.fixtures import is_fixture_mode

        if is_fixture_mode():
            # In fixture mode, generate queries one at a time using mock
            for task in tasks_needing_queries:
                try:
                    query = await self._generate_query(task, retry_attempt=0)
                    if query:
                        # Query already cached by _generate_query
                        pass
                except Exception as e:
                    self.log("fixture_query_error", {"task_id": task.get("id", ""), "error": str(e)[:100]})
            return

        self.log("batch_query_generation_start", {"total_tasks": len(tasks_needing_queries), "batch_size": batch_size})

        # Process in batches
        for i in range(0, len(tasks_needing_queries), batch_size):
            batch = tasks_needing_queries[i : i + batch_size]

            self.state.update(f"Generating queries for batch {i // batch_size + 1} ({len(batch)} tasks)...", "working")

            try:
                queries_generated = 0
                task_query_counts = {}  # Track how many queries per task

                async for task_id, query in self._stream_queries(batch, batch_size):
                    # Find the task to get its argument
                    task = next((t for t in batch if t.get("id") == task_id), None)
                    if task:
                        argument = task.get("argument", "")
                        query_num = task_query_counts.get(task_id, 0) + 1
                        task_query_counts[task_id] = query_num

                        if query_num == 1:
                            # First query: save to original task
                            self._save_query(task_id, argument, query)
                        else:
                            # Additional queries: create variant tasks with unique argument
                            # Append query number to make it unique for deduplication
                            variant_task = {
                                "argument": f"{argument} [Q{query_num}]",
                                "base_argument": argument,  # Keep original for grouping
                                "evidence_type": task.get("evidence_type", "support"),
                                "arg_type": task.get("arg_type", "stock"),
                                "is_query_variant": True,
                                "query_number": query_num,
                            }
                            variant_id = self.session.write_task(variant_task)
                            if variant_id:
                                # Save with base argument (not the modified one)
                                self._save_query(variant_id, argument, query)
                                self.state.task_stages[variant_id] = "queued"

                        queries_generated += 1
                        self.state.update(f"✓ Query {queries_generated}: {query[:50]}...", "working")

                self.log("batch_queries_generated", {"batch": i // batch_size + 1, "queries": queries_generated})

                # Warn if no queries were generated
                if queries_generated == 0:
                    self.log(
                        "batch_query_warning",
                        {"message": "0 queries generated", "batch": i // batch_size + 1, "tasks": len(batch)},
                    )

            except Exception as e:
                self.log("batch_query_error", {"error": str(e)[:100], "batch": i // batch_size + 1})
                # Continue with next batch even if this one fails

    async def _generate_query(self, task: dict[str, Any], retry_attempt: int = 0) -> str | None:
        """Generate a targeted search query for the task.

        Checks cache first for resume support. Saves new queries to disk.

        Args:
            task: The research task
            retry_attempt: Number of previous attempts (0 = first try, 1+ = retry)
        """
        task_id = task.get("id", "")
        argument = task.get("argument", "")

        # Check cache first (only for first attempt - retries need new queries)
        if retry_attempt == 0:
            cached = self._get_cached_query(task_id)
            if cached:
                self.log("query_from_cache", {"task_id": task_id, "query": cached[:50]})
                return cached

        # Check if using fixtures
        from tests.fixtures import is_fixture_mode, mock_generate_query

        if is_fixture_mode():
            fixture_query = mock_generate_query(task)
            if fixture_query and task_id:
                self._save_query(task_id, argument, fixture_query)
            return fixture_query

        config = Config()
        model = config.get_agent_model("prep_search")

        # Modify prompt based on retry attempt
        retry_instructions = ""
        if retry_attempt == 1:
            retry_instructions = "\nIMPORTANT: Previous search failed. Try broader terms or alternative phrasing."
        elif retry_attempt >= 2:
            retry_instructions = "\nIMPORTANT: Multiple attempts failed. Use very different keywords or approach the topic from a different angle."

        template = _load_prompt("search_query_single")
        prompt = template.format(
            argument=argument,
            evidence_type=task.get("evidence_type", "support"),
            retry_instructions=retry_instructions,
        )

        try:
            # Run sync API call in thread pool to avoid blocking event loop
            response = await asyncio.to_thread(
                self._get_client().messages.create,
                model=model,
                max_tokens=50,  # Very short - just the query
                messages=[{"role": "user", "content": prompt}],
            )

            query: str | None = None
            if response.content:
                first_block = response.content[0]
                if hasattr(first_block, "text"):
                    query = first_block.text.strip()

            # Clean up query
            if query:
                query = query.strip('"').strip("'").strip()

            # Save to cache/disk (only for first attempt)
            if query and task_id and retry_attempt == 0:
                self._save_query(task_id, argument, query)

            return query

        except Exception as e:
            self.log("query_error", {"error": str(e)[:100]})
            return None

    async def _handle_error(self, task_id: str, error_reason: str, task: dict[str, Any]) -> None:
        """Handle task error and implement retry logic.

        Strategy:
        - Try next URL from search results (already handled in process_item)
        - If all URLs exhausted, increment retry and requeue
        - Max 3 attempts total
        """
        # Increment retry count
        self.state.task_retries[task_id] = self.state.task_retries.get(task_id, 0) + 1
        retry_count = self.state.task_retries[task_id]

        # Move to error stage
        self.state.task_stages[task_id] = "error"
        self.state.task_errors[task_id] = error_reason

        self.log(
            "task_error",
            {
                "task_id": task_id,
                "error": error_reason,
                "retry_count": retry_count,
                "max_retries": 3,
            },
        )

        # Check if we should retry
        if retry_count < 3:
            # Requeue for retry
            self.log("retry_queued", {"task_id": task_id, "attempt": retry_count + 1})
            self.state.update(f"Retry queued ({retry_count + 1}/3): {error_reason}", "working")

            # Clear current task
            self.state.current_task_id = ""
            self.state.current_task_progress = ""
            self.state.current_argument = ""
            self.state.current_query = ""
            self.state.current_source = ""

            # Add small delay before retry
            await asyncio.sleep(2)

            # Requeue by moving back to queued stage
            self.state.task_stages[task_id] = "queued"
        else:
            # Max retries reached - mark as PERMANENTLY failed
            # This persists to disk so task won't be retried even after agent restart
            self.session.mark_task_failed(task_id, error_reason)

            self.log("max_retries_reached", {"task_id": task_id})
            self.state.update(f"Max retries reached: {error_reason}", "working")
            self.state.current_task_id = ""
            self.state.current_task_progress = ""
            self.state.current_argument = ""
            self.state.current_query = ""
            self.state.current_source = ""
