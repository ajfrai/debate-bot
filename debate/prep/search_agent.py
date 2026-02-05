"""SearchAgent: Writes search queries and stages results."""

import asyncio
import os
import time
from typing import Any

import anthropic

from debate.article_fetcher import fetch_source
from debate.config import Config
from debate.prep.base_agent import BaseAgent
from debate.prep.session import PrepSession
from debate.research_agent import _brave_search, _extract_urls_from_search_results


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

    def __init__(self, session: PrepSession) -> None:
        super().__init__(session, poll_interval=2.0)
        self._client: anthropic.Anthropic | None = None
        self._last_search_time: float = 0.0
        self._search_delay: float = 1.0  # Brave Free: 1 req/sec (was 3.0s - too conservative!)
        self._fetch_delay: float = 0.5  # Delay between article fetches (not Brave API calls)

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
        """Check for pending research tasks."""
        tasks = self.session.get_pending_tasks()
        # Mark new tasks as queued in kanban (but don't overwrite existing states)
        for task in tasks:
            task_id = task.get("id", "")
            if task_id and task_id not in self.state.task_stages:
                # Only set to queued if this is a genuinely new task
                # Don't overwrite existing error/done states
                self.state.task_stages[task_id] = "queued"
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

        # Rate limiting
        time_since_last = time.time() - self._last_search_time
        if time_since_last < self._search_delay:
            wait_time = self._search_delay - time_since_last
            self.state.update(f"rate_limit_wait_{wait_time:.1f}s", "waiting")
            await asyncio.sleep(wait_time)

        # Generate search query (modify if retrying)
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

        fetched_sources = []
        from tests.fixtures import is_fixture_mode, mock_fetch_source

        # Move to fetch stage
        self.state.task_stages[task_id] = "fetch"

        # Fetch all available URLs (all from Brave search results)
        num_to_fetch = len(urls)
        successful_fetches = 0

        for idx, url in enumerate(urls[:num_to_fetch], 1):
            self.state.current_source = url
            self.state.current_task_progress = f"fetch {idx}/{num_to_fetch}"
            self.log("fetching_start", {"url": url})
            self.state.update(f"Fetching ({idx}/{num_to_fetch}): {url[:50]}", "working")

            # Mark URL as tried
            if task_id not in self.state.task_urls_tried:
                self.state.task_urls_tried[task_id] = []
            self.state.task_urls_tried[task_id].append(url)

            article = None
            error_msg = "Unknown error"

            try:
                if is_fixture_mode():
                    # Run in thread to avoid blocking event loop (allows UI updates)
                    article = await asyncio.to_thread(mock_fetch_source, url)
                else:
                    # Run in thread to avoid blocking event loop (allows UI updates)
                    article = await asyncio.to_thread(
                        fetch_source, url, retry_on_paywall=True, brave_api_key=brave_api_key, quiet=True
                    )

                if not article:
                    error_msg = "Paywall or failed to extract content"
            except Exception as e:
                error_msg = str(e)[:80]

            if article:
                successful_fetches += 1
                content_preview = article.full_text[:100] if article.full_text else ""
                self.state.current_snippet = content_preview
                word_count = article.word_count
                title = article.title[:60] if article.title else "No title"
                self.log(
                    "fetch_success",
                    {
                        "url": article.url,
                        "title": title,
                        "word_count": word_count,
                        "content_preview": content_preview,
                    },
                )
                self.state.update(f"✓ {title} ({word_count:,} words)", "working")
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
                self.log(
                    "fetch_failed",
                    {
                        "url": url,
                        "reason": error_msg,
                    },
                )
                # Truncate URL and error for display
                url_short = url[:35] if len(url) > 35 else url
                self.state.update(f"✗ Failed: {url_short} ({error_msg[:40]})", "working")
                fetched_sources.append(
                    {
                        "url": url,
                        "title": None,
                        "full_text": None,
                        "fetch_status": "failed",
                        "error": error_msg,
                    }
                )

            await asyncio.sleep(self._fetch_delay)  # Delay between article fetches

        # Check if we got at least one successful fetch
        if successful_fetches == 0:
            # All fetches failed - trigger retry
            await self._handle_error(task_id, "All fetches failed", task)
            return

        # Stage results
        self.state.current_task_progress = "staging"
        result = {
            "task_id": task_id,
            "query": query,
            "argument": task.get("argument", ""),
            "search_intent": task.get("search_intent", ""),
            "evidence_type": task.get("evidence_type", "support"),
            "sources": fetched_sources,
        }

        self.session.write_search_result(result)
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

    async def _generate_query(self, task: dict[str, Any], retry_attempt: int = 0) -> str | None:
        """Generate a targeted search query for the task.

        Args:
            task: The research task
            retry_attempt: Number of previous attempts (0 = first try, 1+ = retry)
        """
        # Check if using fixtures
        from tests.fixtures import is_fixture_mode, mock_generate_query

        if is_fixture_mode():
            return mock_generate_query(task)

        config = Config()
        model = config.get_agent_model("prep_search")

        # Modify prompt based on retry attempt
        retry_instructions = ""
        if retry_attempt == 1:
            retry_instructions = "\nIMPORTANT: Previous search failed. Try broader terms or alternative phrasing."
        elif retry_attempt >= 2:
            retry_instructions = "\nIMPORTANT: Multiple attempts failed. Use very different keywords or approach the topic from a different angle."

        prompt = f"""Generate ONE search query to find evidence for this debate argument.

Debate tag: {task.get("argument", "")}
Evidence type: {task.get("evidence_type", "support")}{retry_instructions}

Requirements:
- Be specific (include key terms, years like 2024/2025)
- Target credible sources (studies, experts, think tanks)
- Use quotes for exact phrases when helpful

Output ONLY the search query, nothing else. Max 15 words."""

        try:
            # Run sync API call in thread pool to avoid blocking event loop
            response = await asyncio.to_thread(
                self._get_client().messages.create,
                model=model,
                max_tokens=50,  # Very short - just the query
                messages=[{"role": "user", "content": prompt}],
            )

            query = None
            if response.content:
                first_block = response.content[0]
                if hasattr(first_block, "text"):
                    query = first_block.text.strip()

            # Clean up query
            if query:
                query = query.strip('"').strip("'").strip()

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
