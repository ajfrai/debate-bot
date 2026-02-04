"""Specialized prep agents for debate research.

This module provides a multi-agent system for debate prep:
- StrategyAgent: Maintains argument queue, decides what to research
- SearchAgent: Writes search queries, stages results
- CutterAgent: Marks/cuts text from staged search results
- OrganizerAgent: Places cut cards into strategic briefs
"""

from debate.prep.runner import run_prep
from debate.prep.session import PrepSession

__all__ = ["PrepSession", "run_prep"]
