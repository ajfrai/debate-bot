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

Cards are organized into **debate files** (one per resolution) as a searchable directory tree:

```
evidence/
  resolved_the_us_should_ban_tiktok/
    INDEX.md                              # Master table of contents
    pro/
      support/
        tiktok_ban_eliminates_100k_jobs.md
        creator_economy_loses_4_billion.md
      answer/
        no_verified_chinese_data_access.md
      extension/
      impact/
        economic_recession_triggers.md
    con/
      support/
      answer/
      extension/
      impact/
```

**Quick search during rounds:**
```bash
ls pro/answer/                    # See all your answers
grep -r "billion" pro/            # Find cards mentioning "billion"
grep -r "security" con/support/   # Find opponent's security evidence
```

Cards are organized by **strategic value** into sections:

- **support/** - Evidence that PROVES your specific claims
- **answer/** - Evidence that RESPONDS TO opponent's specific arguments
- **extension/** - Additional warrants to STRENGTHEN existing arguments
- **impact/** - Evidence showing WHY something matters (magnitude, timeframe, probability)

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

### Token-Efficient Card Cutting Workflow (NEW)

**Problem**: Having LLM regenerate full card text is expensive and wasteful.

**New Workflow**:

1. **Capture raw source** (Bash)
   ```bash
   cat > evidence/temp/raw_source_001.txt <<'EOF'
   [paste full text from Brave search result]
   EOF
   ```

2. **Mark up the card** (Edit tool or text editor)
   - Bold key warrants: `**like this**`
   - Add metadata at top:
     ```
     TAG: India TikTok ban removed 100M users effectively
     CITE: Kumar & Thussu '23, Media scholars at Amsterdam/Westminster
     AUTHOR: Anilesh Kumar and Daya Thussu
     YEAR: 2023
     SECTION: answer,support
     ARGUMENT: TikTok bans are effective at removing platform access
     URL: https://journals.sagepub.com/...
     ```
   - Mark extract region:
     ```
     >>> START
     India's 2020 ban on **TikTok** and 58 other Chinese apps **successfully removed the platform from access for over 100 million active users within weeks**. The ban **demonstrated effective enforcement through ISP-level blocking and app store removal**, setting a precedent for how democratic nations can successfully execute platform bans.
     <<< END
     ```

3. **Import card** (CLI command)
   ```bash
   uv run debate card-import evidence/temp/raw_source_001.txt "Resolved: The US should ban TikTok" --side pro
   ```
   - Script reads metadata from marked-up file
   - Extracts text between `>>> START` and `<<< END` markers
   - Generates proper card markdown format
   - Places in correct evidence directory based on SECTION/ARGUMENT metadata

**Multiple Destinations:**

Cards can be placed in multiple sections by:
- **Comma-separated SECTION field**: `SECTION: answer,support,extension`
- **--copy-to flag**: `--copy-to impact,extension`

This allows cards to serve multiple purposes (e.g., rebuts opponent AND supports your claim).

**Benefits**:
- LLM doesn't regenerate text (saves tokens)
- Edit tool is precise (no hallucination risk)
- Bash commands are cheap
- Script handles file organization (no LLM JSON generation)
- Can reuse same source for multiple cards by editing different sections

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
