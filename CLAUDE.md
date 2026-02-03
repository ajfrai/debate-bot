# Debate Training CLI

## Project Overview

A CLI tool for practicing Public Forum debate against an AI opponent with AI judging.

### Latest Features (2025)

**Evidence Validation System:**
- All speeches automatically validated for unbacked citations
- Interactive validation with warnings and errors
- Standalone `debate validate` command
- Catches citations not backed by evidence files during rounds

## Running the Project

### Run a Complete Debate Round

```bash
# Run a full debate round against the AI
uv run debate run "Resolved: The US should ban TikTok" --side pro
```

This will:
1. Generate the AI opponent's opening case
2. Walk you through all speeches (you deliver your constructive, rebuttal, summary, final focus)
3. The AI delivers its speeches in response
4. Conduct crossfire Q&A after constructives, rebuttals, and summaries
5. Have an AI judge evaluate the round and declare a winner with feedback

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

### View Evidence

```bash
# List all debate files (numbered for easy selection)
uv run debate evidence

# View by number
uv run debate evidence 1

# View by keyword (partial match)
uv run debate evidence tiktok
```

## Architecture

- `debate/models.py` - Pydantic models for Case, Contention, Speech, Card, DebateFile, ArgumentSection, Round state
- `debate/cli.py` - Entry point with subcommands (run, generate, research, evidence)
- `debate/debate_agent.py` - AI debate agent that generates speeches, handles crossfire, and orchestrates debate activities
- `debate/case_generator.py` - Generates cases using Anthropic API (with or without evidence)
- `debate/judge_agent.py` - AI judge that evaluates rounds and provides decisions with feedback
- `debate/round_controller.py` - Manages debate flow, speech order, and user interaction
- `debate/research_agent.py` - Research agent for cutting evidence cards (uses Haiku for cost efficiency)
- `debate/evidence_storage.py` - Save/load debate files as directories per resolution
- `debate/prompts/` - Prompt templates (Markdown files)
- `lessons/` - Accumulated lessons for agent improvement (research, strategy, organization)
- `evidence/` - Local directory storing debate files (one directory per resolution, git-ignored)

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

Cards are organized into **debate files** (one per resolution) with a flat argument-based structure:

```
evidence/
  resolved_the_us_should_ban_tiktok/
    INDEX.md                              # Master table of contents
    pro/
      economic_harm.md                    # Argument file
      national_security.md                # Argument file
      at_privacy_concerns.md              # Answer file (AT: = "answer to")
    con/
      privacy_protection.md               # Argument file
      at_economic_harm.md                 # Answer file
```

**Each file contains an argument with multiple claims and numbered cards:**

```markdown
# TikTok ban eliminates creator jobs
Evidence that the TikTok ban would destroy the creator economy.

## Supporting claim: Ban eliminates 100k jobs
### 1. Smith '24 - Journal of Economics
**Purpose:** Quantify job losses

The TikTok ban would **eliminate over 100,000 jobs** in the creator economy...

### 2. Jones '25 - Tech Policy Report
...

## Supporting claim: Creator economy contributes $4B annually
### 1. Brown '24 - Economic Analysis
...
```

**Quick search during rounds:**
```bash
ls pro/                           # See all PRO arguments
cat pro/economic_harm.md          # View all evidence for economic harm
grep -r "billion" pro/            # Find cards mentioning "billion"
grep -r "security" con/           # Find opponent's security evidence
```

**Benefits:**
- All evidence for an argument in one file
- Easy to navigate and read entire argument
- Fast searching with grep
- Answer files clearly marked with `AT:` prefix

### Specific Argument Headers

Headers must be SPECIFIC CLAIMS, not vague topics:

**BAD (too vague):**
- "Answer to economic impacts"
- "Supporting evidence for national security"

**GOOD (specific):**
- "Answer to: Opponent claim that TikTok ban hurts creator jobs"
- "Supporting evidence for: Chinese government can access user data"
- "Impact evidence for: Data breaches lead to identity theft"

### Workflow

1. **Autonomous prep**: Use `debate prep` to run agent-driven research
   - Agent uses **Edit-style workflow** (no text regeneration)
   - Searches Brave API, fetches articles, marks warrants programmatically
   - Saves cards to argument-based files
   - **Streams tokens in real-time** so you can see progress

2. **Store in debate files**: Evidence is saved to resolution directories in `evidence/`
   - One directory per resolution containing all PRO and CON evidence
   - Each argument in its own file with numbered cards
   - Markdown INDEX.md provides navigable table of contents

3. **Generate with evidence**: Use `debate generate --with-evidence` to create cases
   - Case generator loads the debate file for the resolution
   - Debate agent cites real evidence with credentials and direct quotes
   - Only reads bolded portions in speeches (like real debate cards)
   - **Streams tokens in real-time** for immediate feedback

### Edit-Style Card Cutting (Token Efficient)

**The agent uses an Edit-style workflow during autonomous prep** - similar to how Claude edits code:

**Workflow:**
1. `search(query)` → Brave API returns URLs and descriptions
2. `fetch_source(url)` → Downloads article, extracts text (up to 3000 chars)
3. `mark_warrants(text, phrases)` → Agent identifies exact phrases to bold, tool adds `**markers**` programmatically
4. `cut_card(metadata, marked_text)` → Saves card to argument file

**Key principle: The agent NEVER regenerates text**
- Agent reads raw article text
- Agent identifies which exact phrases should be bolded
- Tool adds `**markers**` around those phrases automatically
- Like using Edit tool: find exact matches, add markers programmatically

**Benefits:**
- **No text regeneration**: Agent never rewrites content (saves tokens, prevents hallucination)
- **Token efficient**: Only identifies phrases, doesn't rewrite full text
- **Accurate**: Uses exact text from source
- **Edit-like**: Same pattern as code editing

**Example:**
```
Raw text from fetch_source:
"The ban would eliminate jobs and hurt the economy significantly."

Agent calls mark_warrants with:
warrant_phrases: ["eliminate jobs", "hurt the economy significantly"]

Tool returns:
"The ban would **eliminate jobs** and **hurt the economy significantly**."
```

### Cost Optimization

- Autonomous prep uses **Sonnet** for reasoning, but Edit-style workflow minimizes token costs
- **Edit-style card cutting**: Agent never regenerates text, only identifies phrases to bold
- **Brave Search API** finds real sources (free tier: 15k queries/month)
- **Trafilatura** extracts article text efficiently (open source, no API costs)
- Evidence is cached locally in argument files, no need to re-research
- Case generation can use stored evidence without additional research costs
- **Token streaming** provides immediate feedback without waiting

## Key Design Decisions

1. **Separation of concerns**: The debater module should NOT know about CLI concerns
2. **Prompt templates external**: Keep prompts in `/prompts` folder for easy iteration
3. **Round as state machine**: `round.py` manages speech order and turn state
4. **Models are flexible**: Contentions are prose, not structured card lists
5. **Evidence cards are real**: Research agent finds actual sources with verifiable citations, not fabricated evidence
6. **Edit-style card cutting**: Agent never regenerates text - only identifies phrases to bold, tool adds markers programmatically
7. **Argument-based organization**: Each argument is a file with multiple claims and numbered cards (not scattered across folders)
8. **Token efficiency**: No text regeneration, local caching, minimal API usage
9. **Tool-based workflow**: Agent uses tools (search, fetch_source, mark_warrants, cut_card) instead of generating full JSON structures

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

## Configuration

Agent behavior and model selection is controlled by `config.yaml` in the project root. This file manages settings that can grow beyond model selection to include other agent parameters and future capabilities.

### Current Configuration

```yaml
# Agent model configuration
agents:
  # Case generation agent - used for creating debate cases
  case_generator:
    model: claude-sonnet-4-5  # High-quality output for competitive cases

  # Research agent - used for cutting evidence cards
  research:
    model: claude-haiku-4-5  # Cost-effective for iterative research

# API configuration
api:
  max_tokens: 4096  # Maximum tokens per response
```

### Customizing Agent Models

You can override the default models by editing `config.yaml`:

- **case_generator**: Set the model for generating debate cases. Use high-capacity models (Opus, Sonnet) for better quality contentions.
- **research**: Set the model for cutting evidence cards. Haiku is recommended for cost efficiency since many cards are researched per session.

Supported models (as of 2026):
- `claude-opus-4-5` - Most capable, best for complex reasoning
- `claude-sonnet-4-5` - Balanced quality and speed
- `claude-haiku-4-5` - Most cost-effective, fast responses

### Configuration File Growth

This `config.yaml` file is designed to grow beyond model settings to include:
- Agent-specific parameters and behavior tuning
- API rate limiting and timeout settings
- Feature flags for research modes or debate formats
- Output formatting preferences
- Caching and storage settings

## Environment

Required environment variables:
- `ANTHROPIC_API_KEY` - Your Anthropic API key for Claude
- `BRAVE_API_KEY` - (Optional) Your Brave Search API key for evidence research
  - Default is embedded, but you can override with your own key
  - Get a free key at https://brave.com/search/api/ (15k queries/month free tier)
