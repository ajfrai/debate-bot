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

- `debate/models.py` - Pydantic models for Case, Contention, Speech, Card, DebateFile, ArgumentSection, Round state
- `debate/cli.py` - Entry point with subcommands (generate, research, evidence)
- `debate/case_generator.py` - Generates cases using Anthropic API (with or without evidence)
- `debate/research_agent.py` - Research agent for cutting evidence cards (uses Haiku for cost efficiency)
- `debate/evidence_storage.py` - Save/load debate files as directories per resolution
- `debate/prompts/` - Prompt templates (Markdown files)
- `evidence/` - Local directory storing debate files (one directory per resolution)

## Evidence Card System

The debate bot supports research and cutting of evidence cards, organized into **debate files** by strategic value.

### Card Structure

Each evidence card includes:
- **ID**: Unique identifier for cross-referencing across sections
- **Tag**: Brief argument label that states what the card PROVES (e.g., "TikTok ban costs US economy billions")
- **Purpose**: Strategic purpose explaining WHY this card matters
- **Author**: Full name with credentials (e.g., "Jane Smith, Professor of Economics at MIT")
- **Year**: Publication year
- **Source**: Publication name (e.g., "Journal of Economic Perspectives")
- **URL**: Link to source for verification
- **Text**: Direct quote with **bolded sections** marking what should be read aloud

### Debate File Organization

Cards are organized into **debate files** (one per resolution) structured like a directory:

```
evidence/
  resolved_the_us_should_ban_tiktok/
    debate_file.json    # All cards and section data
    INDEX.md            # Rendered markdown table of contents
```

Cards are organized by **strategic value** into sections:

- **Supporting evidence for <argument>** - Cards that prove your arguments
- **Answer to <argument>** - Cards that respond to opponent arguments
- **Extensions for <argument>** - Additional warrants to extend arguments
- **Impact evidence for <argument>** - Impact calculus (magnitude, timeframe, probability)

**Cards can appear in multiple sections** - the same card may be relevant as both support for your argument AND an answer to theirs.

### Workflow

1. **Research evidence**: Use `debate research` to cut cards for specific arguments
   - Research agent uses **Brave Search API** to find real sources
   - Uses Claude Haiku (cost-effective) to extract and format evidence cards
   - Extracts quotes with proper citations and author credentials
   - **Organizes cards by strategic value** (support, answer, extension, impact)
   - Bolds the key warrants (20-40% of text)
   - **Streams tokens in real-time** so you can see progress

2. **Store in debate files**: Evidence is saved to resolution directories in `evidence/`
   - One directory per resolution containing all PRO and CON evidence
   - Markdown INDEX.md provides navigable table of contents
   - Cards are cross-referenced by ID across sections

3. **Generate with evidence**: Use `debate generate --with-evidence` to create cases
   - Case generator loads the debate file for the resolution
   - Debate agent cites real evidence with credentials and direct quotes
   - Only reads bolded portions in speeches (like real debate cards)
   - **Streams tokens in real-time** for immediate feedback

### Cost Optimization

- Research agent uses **Claude Haiku** (cheapest model) for card cutting
- **Brave Search API** finds real sources (free tier: 15k queries/month)
- Limited to 5 cards max per research session
- Evidence is cached locally, no need to re-research
- Case generation can use stored evidence without additional research costs
- **Token streaming** provides immediate feedback without waiting

## Key Design Decisions

1. **Separation of concerns**: The debater module should NOT know about CLI concerns
2. **Prompt templates external**: Keep prompts in `/prompts` folder for easy iteration
3. **Round as state machine**: `round.py` manages speech order and turn state
4. **Models are flexible**: Contentions are prose, not structured card lists
5. **Evidence cards are real**: Research agent finds actual sources with verifiable citations, not fabricated evidence
6. **Cost-effective research**: Uses Haiku model and local caching to minimize token usage
7. **Debate files as directories**: Each resolution has its own directory, like a real debate file
8. **Strategic organization**: Cards organized by purpose (support, answer, extension, impact)
9. **Cross-referencing**: Cards have IDs and can appear in multiple sections where relevant

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

Required environment variables:
- `ANTHROPIC_API_KEY` - Your Anthropic API key for Claude
- `BRAVE_API_KEY` - (Optional) Your Brave Search API key for evidence research
  - Default is embedded, but you can override with your own key
  - Get a free key at https://brave.com/search/api/ (15k queries/month free tier)
