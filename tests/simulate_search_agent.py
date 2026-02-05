#!/usr/bin/env python3
"""
Simulation script to reproduce search agent issues.

This script runs the search agent with fixtures and simulates various
error conditions to document the observed bugs.
"""

import asyncio
import json
import os
import sys
import time
import random
from pathlib import Path
from dataclasses import dataclass
from typing import Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from debate.prep.session import PrepSession
from debate.prep.search_agent import SearchAgent
from debate.models import Side


# Simulation configuration
@dataclass
class SimulationConfig:
    """Configuration for the simulation."""
    duration_seconds: float = 30.0
    simulate_fetch_delays: bool = True
    simulate_fetch_errors: bool = True
    fetch_error_rate: float = 0.3  # 30% of fetches fail
    fetch_delay_range: tuple[float, float] = (0.5, 2.0)
    search_delay_range: tuple[float, float] = (0.2, 1.0)
    log_ui_updates: bool = True


# Tracking for analysis
class SimulationTracker:
    """Track simulation events for analysis."""

    def __init__(self):
        self.events: list[dict] = []
        self.ui_updates: list[dict] = []
        self.start_time: float = 0.0

    def log_event(self, event_type: str, details: dict):
        elapsed = time.time() - self.start_time
        event = {
            "elapsed": round(elapsed, 2),
            "type": event_type,
            **details
        }
        self.events.append(event)

    def log_ui_update(self, agent_state: dict):
        elapsed = time.time() - self.start_time
        self.ui_updates.append({
            "elapsed": round(elapsed, 2),
            **agent_state
        })


# Enhanced fixtures with delays and errors
_tracker: SimulationTracker | None = None
_config: SimulationConfig | None = None


def mock_generate_query_with_delay(task: dict[str, Any]) -> str:
    """Mock query generation with simulated delay."""
    from tests.fixtures import SAMPLE_QUERIES

    global _query_counter
    if not hasattr(mock_generate_query_with_delay, '_counter'):
        mock_generate_query_with_delay._counter = 0

    query = SAMPLE_QUERIES[mock_generate_query_with_delay._counter % len(SAMPLE_QUERIES)]
    mock_generate_query_with_delay._counter += 1

    if _tracker:
        _tracker.log_event("query_generated", {"query": query[:50]})

    return query


def mock_brave_search_with_delay(query: str, num_results: int = 5, quiet: bool = True) -> str:
    """Mock Brave search that returns CORRECTLY FORMATTED results."""
    from tests.fixtures import SAMPLE_RESULTS

    if _config and _config.simulate_fetch_delays:
        delay = random.uniform(*_config.search_delay_range)
        time.sleep(delay)

    # Find matching results or use random
    matching_results = None
    for result in SAMPLE_RESULTS:
        if result["query"].lower() in query.lower() or query.lower() in result["query"].lower():
            matching_results = result
            break

    if not matching_results:
        if not hasattr(mock_brave_search_with_delay, '_counter'):
            mock_brave_search_with_delay._counter = 0
        matching_results = SAMPLE_RESULTS[mock_brave_search_with_delay._counter % len(SAMPLE_RESULTS)]
        mock_brave_search_with_delay._counter += 1

    urls = matching_results["urls"][:num_results]

    # Format EXACTLY like _brave_search does (markdown format, not JSON!)
    formatted = ["## Search Results\n"]
    for i, url in enumerate(urls, 1):
        formatted.append(f"{i}. **Result for {query[:30]}**")
        formatted.append(f"   URL: {url}")
        formatted.append(f"   Description: Search result from {url}")
        formatted.append("")

    if _tracker:
        _tracker.log_event("search_completed", {"query": query[:40], "urls_found": len(urls)})

    return "\n".join(formatted)


def mock_fetch_source_with_delay(url: str, **kwargs) -> Any:
    """Mock article fetching with delays and simulated errors."""
    from tests.fixtures import SAMPLE_ARTICLES

    # Simulate fetch delay
    if _config and _config.simulate_fetch_delays:
        delay = random.uniform(*_config.fetch_delay_range)
        time.sleep(delay)

    # Simulate fetch errors
    if _config and _config.simulate_fetch_errors:
        if random.random() < _config.fetch_error_rate:
            error_types = [
                "Paywall detected",
                "Connection timeout",
                "HTTP 403 Forbidden",
                "HTTP 404 Not Found",
                "SSL certificate error",
            ]
            error = random.choice(error_types)
            if _tracker:
                _tracker.log_event("fetch_error", {"url": url[:50], "error": error})
            return None

    # Find matching article or use random
    article = None
    for a in SAMPLE_ARTICLES:
        if a["url"] == url:
            article = a
            break

    if not article:
        article = random.choice(SAMPLE_ARTICLES)

    class MockArticle:
        def __init__(self, url: str, title: str, content: str):
            self.url = url
            self.title = title
            self.full_text = content
            self.word_count = len(content.split())

    if _tracker:
        _tracker.log_event("fetch_success", {"url": url[:50], "words": article["content"].split().__len__()})

    return MockArticle(url=article["url"], title=article["title"], content=article["content"])


def patch_fixtures():
    """Patch the fixture functions with our enhanced versions."""
    import tests.fixtures as fixtures

    # Store originals
    fixtures._original_mock_generate_query = fixtures.mock_generate_query
    fixtures._original_mock_brave_search = fixtures.mock_brave_search
    fixtures._original_mock_fetch_source = fixtures.mock_fetch_source

    # Patch with our versions
    fixtures.mock_generate_query = mock_generate_query_with_delay
    fixtures.mock_brave_search = mock_brave_search_with_delay
    fixtures.mock_fetch_source = mock_fetch_source_with_delay


def unpatch_fixtures():
    """Restore original fixture functions."""
    import tests.fixtures as fixtures

    if hasattr(fixtures, '_original_mock_generate_query'):
        fixtures.mock_generate_query = fixtures._original_mock_generate_query
        fixtures.mock_brave_search = fixtures._original_mock_brave_search
        fixtures.mock_fetch_source = fixtures._original_mock_fetch_source


async def monitor_ui_state(agent: SearchAgent, deadline: float, interval: float = 0.5):
    """Monitor and log UI state changes."""
    global _tracker

    last_state = None
    while time.time() < deadline:
        state = agent.state
        current_state = {
            "status": state.status,
            "current_argument": state.current_argument[:40] if state.current_argument else "",
            "current_query": state.current_query[:40] if state.current_query else "",
            "current_source": state.current_source[:40] if state.current_source else "",
            "items_processed": state.items_processed,
            "items_created": state.items_created,
            "task_stages": dict(state.task_stages),
        }

        # Only log if state changed
        if current_state != last_state:
            if _tracker:
                _tracker.log_ui_update(current_state)
            last_state = current_state.copy()

        await asyncio.sleep(interval)


async def run_simulation(config: SimulationConfig) -> dict:
    """Run the simulation and return results."""
    global _tracker, _config

    _config = config
    _tracker = SimulationTracker()
    _tracker.start_time = time.time()

    # Enable fixtures and patch
    os.environ["DEBATE_FIXTURES"] = "1"
    patch_fixtures()

    try:
        # Create session with test tasks
        session = PrepSession(
            resolution="Resolved: The US should pursue military action against Iran",
            side=Side.CON,
        )

        # Create diverse test tasks
        test_tasks = [
            {
                "id": "task_001",
                "argument": "Iran nuclear advancement threatens regional stability",
                "search_intent": "Find evidence on Iran's nuclear capability growth",
                "evidence_type": "support",
            },
            {
                "id": "task_002",
                "argument": "Military intervention would destabilize the region",
                "search_intent": "Find evidence on military conflict costs and risks",
                "evidence_type": "support",
            },
            {
                "id": "task_003",
                "argument": "Diplomatic options remain viable",
                "search_intent": "Find evidence on diplomatic alternatives to military action",
                "evidence_type": "support",
            },
            {
                "id": "task_004",
                "argument": "Iran's missile program poses direct threat",
                "search_intent": "Find evidence on Iran missile capabilities",
                "evidence_type": "attack",
            },
        ]

        for task in test_tasks:
            session.write_task(task)

        _tracker.log_event("simulation_started", {
            "tasks": len(test_tasks),
            "duration": config.duration_seconds,
            "error_rate": config.fetch_error_rate,
        })

        # Create agent
        agent = SearchAgent(session)

        # Run agent with UI monitoring
        deadline = time.time() + config.duration_seconds

        # Run both concurrently
        await asyncio.gather(
            agent.run(deadline),
            monitor_ui_state(agent, deadline, interval=0.5),
        )

        # Collect results
        results_dir = session.staging_dir / "search" / "results"
        result_files = list(results_dir.glob("*.json")) if results_dir.exists() else []

        # Read event log
        event_log_path = session.staging_dir / "_event_log.jsonl"
        event_log_entries = []
        if event_log_path.exists():
            with open(event_log_path) as f:
                for line in f:
                    event_log_entries.append(json.loads(line))

        _tracker.log_event("simulation_completed", {
            "items_processed": agent.state.items_processed,
            "items_created": agent.state.items_created,
            "result_files": len(result_files),
            "final_task_stages": dict(agent.state.task_stages),
        })

        # Get permanently failed tasks from session
        permanently_failed = list(session._load_failed_tasks())

        return {
            "config": {
                "duration": config.duration_seconds,
                "fetch_error_rate": config.fetch_error_rate,
                "simulate_delays": config.simulate_fetch_delays,
            },
            "results": {
                "items_processed": agent.state.items_processed,
                "items_created": agent.state.items_created,
                "result_files": len(result_files),
                "final_task_stages": dict(agent.state.task_stages),
                "task_retries": dict(agent.state.task_retries),
                "task_errors": dict(agent.state.task_errors),
                "permanently_failed_tasks": permanently_failed,
            },
            "events": _tracker.events,
            "ui_updates": _tracker.ui_updates,
            "event_log": event_log_entries,
            "staging_dir": str(session.staging_dir),
        }

    finally:
        unpatch_fixtures()
        os.environ["DEBATE_FIXTURES"] = ""


def analyze_results(results: dict) -> dict:
    """Analyze simulation results for issues."""
    issues = []

    # Check for format mismatch bug
    events = results.get("event_log", [])
    zero_url_searches = [e for e in events if e.get("action") == "search_success" and e.get("urls_found") == 0]
    if zero_url_searches:
        issues.append({
            "severity": "CRITICAL",
            "type": "format_mismatch",
            "description": "Search returns 0 URLs - mock returns JSON but extractor expects markdown",
            "count": len(zero_url_searches),
        })

    # Check for infinite retry loop
    retry_counts = results.get("results", {}).get("task_retries", {})
    excessive_retries = {k: v for k, v in retry_counts.items() if v > 3}
    if excessive_retries:
        issues.append({
            "severity": "CRITICAL",
            "type": "infinite_retry",
            "description": "Tasks retry beyond max_retries (3) limit",
            "tasks": excessive_retries,
        })

    # Check if failed tasks are properly persisted
    permanently_failed = results.get("results", {}).get("permanently_failed_tasks", [])
    max_retries_events = [e for e in events if e.get("action") == "max_retries_reached"]
    error_task_ids = set(e.get("task_id") for e in max_retries_events)

    for task_id in error_task_ids:
        if task_id not in permanently_failed:
            issues.append({
                "severity": "HIGH",
                "type": "task_not_persisted_failed",
                "description": f"Task {task_id} hit max retries but not marked as permanently failed",
            })

    # Check UI update frequency
    ui_updates = results.get("ui_updates", [])
    if len(ui_updates) < 5:
        issues.append({
            "severity": "MEDIUM",
            "type": "slow_ui_updates",
            "description": f"Only {len(ui_updates)} UI updates in {results['config']['duration']}s",
        })

    # Check for successful results
    items_created = results.get("results", {}).get("items_created", 0)
    if items_created == 0:
        issues.append({
            "severity": "CRITICAL",
            "type": "no_results",
            "description": "No search results were created",
        })

    return {
        "issues": issues,
        "summary": {
            "critical": len([i for i in issues if i["severity"] == "CRITICAL"]),
            "high": len([i for i in issues if i["severity"] == "HIGH"]),
            "medium": len([i for i in issues if i["severity"] == "MEDIUM"]),
        }
    }


def print_report(results: dict, analysis: dict):
    """Print a formatted report."""
    print("\n" + "=" * 70)
    print("SEARCH AGENT SIMULATION REPORT")
    print("=" * 70)

    print("\n## Configuration")
    config = results["config"]
    print(f"  Duration: {config['duration']}s")
    print(f"  Fetch Error Rate: {config['fetch_error_rate']*100}%")
    print(f"  Simulate Delays: {config['simulate_delays']}")

    print("\n## Results")
    r = results["results"]
    print(f"  Items Processed: {r['items_processed']}")
    print(f"  Items Created: {r['items_created']}")
    print(f"  Result Files: {r['result_files']}")

    print("\n## Final Task States")
    for task_id, stage in r["final_task_stages"].items():
        retries = r["task_retries"].get(task_id, 0)
        error = r["task_errors"].get(task_id, "")
        print(f"  {task_id}: {stage} (retries: {retries}) {error}")

    print("\n## Issues Found")
    issues = analysis["issues"]
    if not issues:
        print("  No issues found!")
    else:
        for issue in issues:
            print(f"\n  [{issue['severity']}] {issue['type']}")
            print(f"    {issue['description']}")
            for k, v in issue.items():
                if k not in ["severity", "type", "description"]:
                    print(f"    {k}: {v}")

    print("\n## UI Update Timeline")
    for i, update in enumerate(results["ui_updates"][:10]):  # First 10
        print(f"  {update['elapsed']:5.1f}s: {update['status']} - {update.get('current_argument', '')[:30]}")
    if len(results["ui_updates"]) > 10:
        print(f"  ... and {len(results['ui_updates']) - 10} more updates")

    print("\n## Event Log Summary")
    event_types = {}
    for event in results["event_log"]:
        action = event.get("action", "unknown")
        event_types[action] = event_types.get(action, 0) + 1
    for action, count in sorted(event_types.items(), key=lambda x: -x[1]):
        print(f"  {action}: {count}")

    print("\n" + "=" * 70)
    summary = analysis["summary"]
    print(f"SUMMARY: {summary['critical']} critical, {summary['high']} high, {summary['medium']} medium issues")
    print("=" * 70 + "\n")


async def main():
    """Run the simulation."""
    print("\nStarting Search Agent Simulation...")
    print("This will simulate API calls with delays and errors.\n")

    config = SimulationConfig(
        duration_seconds=30.0,
        simulate_fetch_delays=True,
        simulate_fetch_errors=True,
        fetch_error_rate=0.3,  # 30% failure rate (realistic)
    )

    results = await run_simulation(config)
    analysis = analyze_results(results)
    print_report(results, analysis)

    # Save detailed results
    output_path = Path("/tmp/search_agent_simulation_report.json")
    with open(output_path, "w") as f:
        json.dump({
            "results": results,
            "analysis": analysis,
        }, f, indent=2, default=str)
    print(f"Detailed results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
