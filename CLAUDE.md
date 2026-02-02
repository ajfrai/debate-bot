# Debate Training CLI

## Project Overview

A CLI tool for practicing Public Forum debate against an AI opponent with AI judging.

## Running the Project

```bash
# Generate a case
uv run python -m debate.cli "Resolved: The US should ban TikTok" --side pro

# Or using the installed command
uv run debate "Resolved: The US should ban TikTok" --side con
```

## Architecture

- `debate/models.py` - Pydantic models for Case, Contention, Speech, Round state
- `debate/cli.py` - Entry point, argument parsing
- `debate/case_generator.py` - Generates cases using Anthropic API
- `debate/prompts/` - Prompt templates (Markdown files)

## Key Design Decisions

1. **Separation of concerns**: The debater module should NOT know about CLI concerns
2. **Prompt templates external**: Keep prompts in `/prompts` folder for easy iteration
3. **Round as state machine**: `round.py` manages speech order and turn state
4. **Models are flexible**: Contentions are prose, not structured card lists

## PF Speech Order

| Order | Speaker | Speech | Time |
|-------|---------|--------|------|
| 1 | Team A - First Speaker | Constructive | 4 min |
| 2 | Team B - First Speaker | Constructive | 4 min |
| 3 | Team A - Second Speaker | Rebuttal | 4 min |
| 4 | Team B - Second Speaker | Rebuttal | 4 min |
| 5 | Team A - First Speaker | Summary | 3 min |
| 6 | Team B - First Speaker | Summary | 3 min |
| 7 | Team A - Second Speaker | Final Focus | 2 min |
| 8 | Team B - Second Speaker | Final Focus | 2 min |

Crossfires after speeches 1-2, 3-4, and 5-6.

## Environment

Requires `ANTHROPIC_API_KEY` environment variable.
