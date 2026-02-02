# Bidirectional Evidence-Argument Synthesis

## Overview

The debate bot now supports **bidirectional flow** between evidence and arguments, mirroring real debate preparation:

1. **Argument → Evidence**: Start with arguments, find supporting evidence
2. **Evidence → Arguments**: Start with evidence, synthesize arguments from it
3. **Iterative**: Go back and forth, refining both

## Key Features

### 1. Evidence Validation

All speeches are automatically validated to ensure citations are backed by evidence files.

**Validation Rules:**
- ✓ **Acceptable**: Arguments using logic/reasoning OR quoted evidence with backing
- ⚠ **Borderline**: Paraphrased evidence with backing (warning)
- ✗ **Unacceptable**: Citations not backed in evidence files (error)

**Validation happens automatically during:**
- Debate rounds (both user and AI speeches)
- Manual validation with `debate validate`

### 2. Evidence Analysis & Synthesis

The synthesis agent can analyze evidence and build arguments directly from it.

**What it does:**
- Identifies themes/topics in evidence
- Assesses evidence strength
- Synthesizes contentions from evidence
- Shows what arguments the evidence supports

### 3. Three Case Generation Modes

**Mode: `scratch`** (No evidence)
- Generates arguments without evidence
- Uses fabricated evidence citations
- Good for initial brainstorming

**Mode: `evidence_first`** (Evidence → Arguments)
- Requires debate file with evidence
- Analyzes evidence first
- Builds arguments around what evidence proves
- All claims backed by actual evidence

**Mode: `balanced`** (Auto)
- Default mode
- Uses evidence-first if available
- Falls back gracefully if insufficient evidence
- Best for most use cases

## Usage Examples

### Workflow 1: Evidence-First (Start with Research)

```bash
# Step 1: Research evidence on specific topics
uv run debate research "Resolved: Ban TikTok" --side con --topic "economic impacts" --num-cards 5
uv run debate research "Resolved: Ban TikTok" --side con --topic "privacy concerns" --num-cards 4

# Step 2: Analyze what arguments the evidence supports
uv run debate synthesize "Resolved: Ban TikTok" --side con

# This will:
# - Identify themes in your evidence
# - Show what claims each theme could prove
# - Synthesize 2-3 contentions directly from evidence
# - Display complete arguments with citations

# Step 3: Generate case from evidence
uv run debate generate "Resolved: Ban TikTok" --side con --mode evidence_first

# This creates a case built entirely from your evidence
```

### Workflow 2: Argument-First (Traditional)

```bash
# Step 1: Generate draft case (no evidence required)
uv run debate generate "Resolved: Ban TikTok" --side con --mode scratch

# Step 2: Identify what evidence you need
# (manually review the case and note claims that need support)

# Step 3: Research evidence for specific claims
uv run debate research "Resolved: Ban TikTok" --side con --topic "Ban costs 100k jobs" --num-cards 3

# Step 4: Regenerate case with evidence
uv run debate generate "Resolved: Ban TikTok" --side con --mode balanced
```

### Workflow 3: Balanced (Recommended)

```bash
# Step 1: Do some initial research
uv run debate research "Resolved: Ban TikTok" --side pro --topic "national security" --num-cards 4

# Step 2: Generate case (auto-detects evidence)
uv run debate generate "Resolved: Ban TikTok" --side pro

# The system will:
# - Detect your evidence file
# - Try evidence-first approach
# - Fall back to balanced mode if needed
# - Create strongest possible case with available evidence

# Step 3: Identify gaps (what evidence is missing)
uv run debate synthesize "Resolved: Ban TikTok" --side pro --action gaps

# Step 4: Research gaps
uv run debate research "Resolved: Ban TikTok" --side pro --topic "data breach impacts" --num-cards 3

# Step 5: Regenerate with complete evidence
uv run debate generate "Resolved: Ban TikTok" --side pro
```

### Validation During Debates

```bash
# Run a debate round
uv run debate run "Resolved: Ban TikTok" --side pro

# During the round:
# - AI speeches are automatically validated
# - Errors/warnings shown if citations are unbacked
# - User speeches are validated too
# - You can choose to revise if validation fails
```

### Manual Validation

```bash
# Validate a speech from a file
uv run debate validate "Resolved: Ban TikTok" --side pro --file my_speech.txt

# Validate from stdin
uv run debate validate "Resolved: Ban TikTok" --side con
# (then paste your speech and press Ctrl+D)

# Output shows:
# - ✓ Valid citations with matched evidence
# - ✗ Citations not backed by evidence (ERRORS)
# - ⚠ Paraphrased or missing quotes (WARNINGS)
# - Summary of all citations found
```

## CLI Commands Reference

### Generate Command

```bash
uv run debate generate <resolution> --side <pro|con> [options]

Options:
  --mode <scratch|evidence_first|balanced>  Generation mode (default: balanced)
  --with-evidence                           Use legacy evidence buckets (optional)
```

### Synthesize Command

```bash
uv run debate synthesize <resolution> --side <pro|con> [options]

Options:
  --action <analyze|from-evidence|gaps>     What to do (default: analyze)

Actions:
  analyze       Analyze evidence and synthesize arguments
  from-evidence Same as analyze
  gaps          Identify gaps in a case (future feature)
```

### Validate Command

```bash
uv run debate validate <resolution> --side <pro|con> [options]

Options:
  --file <path>    File with speech text (reads stdin if omitted)
```

### Research Command (Enhanced)

```bash
uv run debate research <resolution> --side <pro|con> --topic <topic> [options]

Options:
  --num-cards <n>   Number of cards to cut (default: 3, max: 5)
  --query <query>   Custom search query (auto-generated if omitted)
```

## How Validation Works

### Citation Pattern Detection

The validator detects citations in these formats:

- `[Author Year] explains/found/argues...`
- `Author Year explains/found/argues...` (without brackets)
- `According to Author Year,`
- `Author (Year)` format

### Matching Process

For each citation found:
1. Extracts author last name and year
2. Searches debate file for matching card
3. Verifies quoted text matches bolded portions
4. Reports status (valid, warning, error)

### Validation Results

**Errors (Must Fix):**
- Citation not found in evidence file
- Author/year doesn't match any card

**Warnings (Should Fix):**
- Citation found but no quoted text
- Quoted text doesn't match bolded portions
- May be paraphrased evidence

**Info (Good):**
- Citation matched with verified quote
- Evidence usage statistics

## Architecture

```
┌──────────────────────────────────────────┐
│         CLI Commands                     │
│  generate | research | synthesize        │
│  validate | evidence | run               │
└───────────┬──────────────────────────────┘
            │
┌───────────┴─────────────┬────────────────┐
│                         │                │
│  Synthesis Agent        │   Validator    │
│  • analyze_evidence     │   • validate   │
│  • synthesize_args      │   • match      │
│  • identify_gaps        │   • verify     │
│                         │                │
└───────────┬─────────────┴────────────────┘
            │
┌───────────┴──────────────────────────────┐
│      Case Generator (Enhanced)           │
│  • scratch mode                          │
│  • evidence_first mode                   │
│  • balanced mode                         │
└───────────┬──────────────────────────────┘
            │
┌───────────┴──────────────────────────────┐
│      Research Agent                      │
│  • Cut cards from searches               │
│  • Organize by strategic value           │
│  • Store in debate files                 │
└───────────┬──────────────────────────────┘
            │
┌───────────┴──────────────────────────────┐
│      Evidence Storage                    │
│  • DebateFile (debate files)             │
│  • Cards (evidence cards)                │
│  • Sections (strategic organization)     │
└──────────────────────────────────────────┘
```

## Benefits of Bidirectional Synthesis

### For Evidence-First Approach:
- Build arguments around strong evidence
- No unbacked claims
- Every argument has support
- Discover argument opportunities from research

### For Argument-First Approach:
- Start with strategic framing
- Research targeted evidence
- Fill specific gaps
- Traditional debate prep flow

### For Validation:
- Catch unbacked citations early
- Ensure evidence quality
- Practice proper evidence usage
- Build good debate habits

## Next Steps

1. Research evidence on key topics
2. Use `synthesize` to see what arguments you can make
3. Generate case with appropriate mode
4. Validate speeches to ensure quality
5. Iterate and refine

The system is designed to be flexible - use whichever workflow fits your preparation style!
