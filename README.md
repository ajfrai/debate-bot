# Debate Training CLI

Practice Public Forum debate against an AI opponent with AI judging.

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
# Install dependencies
uv sync

# Set your Anthropic API key
export ANTHROPIC_API_KEY=your-key-here
```

## Usage

### Generate a Case

```bash
# Generate a Pro case
uv run debate "Resolved: The US should ban TikTok" --side pro

# Generate a Con case
uv run debate "Resolved: The US should ban TikTok" --side con
```

## Project Structure

```
debate/
├── cli.py              # Entry point, argument parsing
├── case_generator.py   # Generates cases with contentions
├── models.py           # Pydantic models: Case, Contention, Speech, Round
└── prompts/            # Prompt templates
    └── case_generation.md
```

## Development

```bash
# Run directly
uv run python -m debate.cli "test resolution" --side pro
```
