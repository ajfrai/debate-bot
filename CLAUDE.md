# Debate Training CLI

## Project Overview

A CLI tool for practicing Public Forum debate against an AI opponent with AI judging.

## Running the Project

### Generate a Case (Basic)

```bash
# Generate a case with fabricated evidence
uv run debate generate "Resolved: The US should ban TikTok" --side pro
```

### Research Evidence Cards

```bash
# Research evidence for a specific argument
uv run debate research "Resolved: The US should ban TikTok" --side pro --topic "economic impacts" --num-cards 3

# Research for multiple topics
uv run debate research "Resolved: The US should ban TikTok" --side pro --topic "national security" --num-cards 2
```

### Generate a Case with Real Evidence

```bash
# Generate a case using researched evidence cards
uv run debate generate "Resolved: The US should ban TikTok" --side pro --with-evidence
```

### View Evidence Buckets

```bash
# List all evidence
uv run debate evidence

# List evidence for a specific resolution
uv run debate evidence --resolution "Resolved: The US should ban TikTok"
```

## Architecture

- `debate/models.py` - Pydantic models for Case, Contention, Speech, Card, EvidenceBucket, Round state
- `debate/cli.py` - Entry point with subcommands (generate, research, evidence)
- `debate/case_generator.py` - Generates cases using Anthropic API (with or without evidence)
- `debate/research_agent.py` - Research agent for cutting evidence cards (uses Haiku for cost efficiency)
- `debate/evidence_storage.py` - Save/load evidence buckets as JSON files
- `debate/prompts/` - Prompt templates (Markdown files)
- `evidence/` - Local directory storing evidence buckets (JSON files organized by resolution)

## Evidence Card System

The debate bot now supports research and cutting of evidence cards, similar to policy debate evidence buckets:

### Card Structure

Each evidence card includes:
- **Tag**: Brief argument label (e.g., "Trade increases GDP")
- **Author**: Full name with credentials (e.g., "Jane Smith, Professor of Economics at MIT")
- **Year**: Publication year
- **Source**: Publication name (e.g., "Journal of Economic Perspectives")
- **URL**: Link to source for verification
- **Text**: Direct quote with **bolded sections** marking what should be read aloud

### Workflow

1. **Research evidence**: Use `debate research` to cut cards for specific arguments
   - Research agent uses Claude Haiku (cost-effective) to find and format cards
   - Searches web sources and extracts quotes with proper citations
   - Bolds the key warrants (20-40% of text)

2. **Store in buckets**: Evidence is saved as JSON files in `evidence/` directory
   - Organized by resolution, side, and topic
   - Each bucket has a table of contents

3. **Generate with evidence**: Use `debate generate --with-evidence` to create cases
   - Case generator loads relevant evidence buckets
   - Debate agent cites real evidence with credentials and direct quotes
   - Only reads bolded portions in speeches (like real debate cards)

### Cost Optimization

- Research agent uses **Claude Haiku** (cheapest model) for card cutting
- Limited to 5 cards max per research session
- Evidence is cached locally, no need to re-research
- Case generation can use stored evidence without additional research costs

## Key Design Decisions

1. **Separation of concerns**: The debater module should NOT know about CLI concerns
2. **Prompt templates external**: Keep prompts in `/prompts` folder for easy iteration
3. **Round as state machine**: `round.py` manages speech order and turn state
4. **Models are flexible**: Contentions are prose, not structured card lists
5. **Evidence cards are real**: Research agent finds actual sources with verifiable citations, not fabricated evidence
6. **Cost-effective research**: Uses Haiku model and local caching to minimize token usage

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
