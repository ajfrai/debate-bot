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
        self._search_delay: float = 3.0  # Seconds between searches

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
        # Mark new tasks as queued in kanban
        for task in tasks:
            task_id = task.get("id", "")
            if task_id and task_id not in self.state.task_stages:
                self.state.task_stages[task_id] = "queued"
        return tasks

    async def process_item(self, task: dict[str, Any]) -> None:
        """Process a research task: generate query, search, fetch, stage."""
        task_id = task["id"]
        task_path = str(self.session.staging_dir / "strategy" / "tasks" / f"task_{task_id}.json")

        self.state.current_task_id = task_id
        self.state.current_task_progress = "starting"
        argument = task.get("argument", "")
        self.log("processing_task", {"task_id": task_id, "argument": argument[:40]})
        self.state.update(f"Running: {argument[:50]}", "working")
        # Move to query stage
        self.state.task_stages[task_id] = "query"

        # Rate limiting
        time_since_last = time.time() - self._last_search_time
        if time_since_last < self._search_delay:
            wait_time = self._search_delay - time_since_last
            self.state.update(f"rate_limit_wait_{wait_time:.1f}s", "waiting")
            await asyncio.sleep(wait_time)

        # Generate search query
        self.state.current_task_progress = "generating_query"
        query = await self._generate_query(task)
        if not query:
            self.log("query_failed", {"task_id": task_id})
            self.state.current_task_id = ""
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
        if is_fixture_mode():
            search_results: str | None = mock_brave_search(query, num_results=5, quiet=True)
        else:
            search_results = _brave_search(query, num_results=5, quiet=True)

        if not search_results:
            self.log("search_failed", {"task_id": task_id, "query": query})
            self.state.current_task_id = ""
            return

        # Extract URLs and fetch articles
        urls = _extract_urls_from_search_results(search_results)
        brave_api_key = os.environ.get("BRAVE_API_KEY")

        self.log(
            "search_success",
            {
                "query": query,
                "urls_found": len(urls),
                "urls_to_fetch": min(2, len(urls)),
            },
        )
        self.state.update(f"Searched: {len(urls)} results found", "working")

        fetched_sources = []
        from tests.fixtures import is_fixture_mode, mock_fetch_source

        # Move to fetch stage
        self.state.task_stages[task_id] = "fetch"

        num_to_fetch = min(2, len(urls))
        for idx, url in enumerate(urls[:2], 1):  # Fetch top 2
            self.state.current_source = url
            self.state.current_task_progress = f"fetch {idx}/{num_to_fetch}"
            self.log("fetching_start", {"url": url})
            self.state.update(f"Fetching ({idx}/{num_to_fetch}): {url[:50]}", "working")

            article = None
            error_msg = "Unknown error"

            try:
                if is_fixture_mode():
                    article = mock_fetch_source(url)
                else:
                    article = fetch_source(url, retry_on_paywall=True, brave_api_key=brave_api_key, quiet=True)

                if not article:
                    error_msg = "Paywall or failed to extract content"
            except Exception as e:
                error_msg = str(e)[:80]

            if article:
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

            await asyncio.sleep(2)  # Rate limit between fetches

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

        self.state.current_task_id = ""
        self.state.current_task_progress = ""

    async def _generate_query(self, task: dict[str, Any]) -> str | None:
        """Generate a targeted search query for the task."""
        # Check if using fixtures
        from tests.fixtures import is_fixture_mode, mock_generate_query

        if is_fixture_mode():
            return mock_generate_query(task)

        config = Config()
        model = config.get_agent_model("prep_search")

        prompt = f"""Generate ONE search query to find evidence for this debate argument.

Argument: {task.get("argument", "")}
Search intent: {task.get("search_intent", "")}
Evidence type needed: {task.get("evidence_type", "support")}

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
