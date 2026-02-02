# Bidirectional Evidence-Argument Synthesis Design

## Overview

The debate bot should support flexible, bidirectional flow between evidence and arguments, mirroring how real debate preparation works.

## Three Core Flows

### 1. Argument-First (Current)
```
Idea → Argument → Find Evidence → Cite in Speech
```
- Debater has an argument idea
- Searches for evidence to support it
- Cites evidence in constructive/speeches

### 2. Evidence-First (New)
```
Evidence → Analyze → Synthesize Argument → Build Case
```
- Debater finds compelling evidence
- Identifies what it proves
- Builds arguments around the evidence

### 3. Iterative Refinement (New)
```
Draft Arguments ←→ Evidence Research ←→ Refine Arguments
```
- Start with either evidence or arguments
- Identify gaps (missing evidence or weak arguments)
- Iterate until complete

## Implementation Plan

### Phase 1: Evidence Analysis & Synthesis

**New Module: `debate/synthesis_agent.py`**

Key functions:
- `analyze_evidence(debate_file, side)` - Analyze what arguments the evidence supports
- `synthesize_arguments_from_evidence(debate_file, side)` - Generate argument ideas from evidence
- `identify_gaps(case, debate_file, side)` - Find arguments without evidence or evidence without arguments

**Returns:**
```python
@dataclass
class EvidenceAnalysis:
    """Analysis of available evidence"""
    themes: List[str]  # What topics/themes the evidence covers
    supported_claims: List[str]  # What specific claims the evidence proves
    gap_areas: List[str]  # What arguments need more evidence
    suggested_contentions: List[Contention]  # Contentions synthesized from evidence
```

### Phase 2: Enhanced Case Generation Modes

**Extend `debate/case_generator.py`**

Add new generation modes:
1. `generate_case_from_scratch()` - Current mode (fabricate evidence)
2. `generate_case_argument_first(topic)` - Generate arguments, then find evidence
3. `generate_case_evidence_first(debate_file)` - Start from evidence, build arguments
4. `generate_case_iterative(debate_file, draft_case)` - Refine case using evidence

**Mode Selection:**
```python
def generate_case(
    resolution: str,
    side: Side,
    mode: str = "balanced",  # scratch | argument_first | evidence_first | iterative
    debate_file: Optional[DebateFile] = None,
    draft_case: Optional[Case] = None,
    **kwargs
) -> Case:
    """Generate a case with flexible evidence-argument flow"""
```

### Phase 3: Research Agent Enhancement

**Extend `debate/research_agent.py`**

Add targeted research modes:
- `research_for_claim(claim, resolution, side)` - Find evidence for specific claim
- `research_from_evidence_gaps(case, debate_file)` - Fill in missing evidence
- `research_exploratory(resolution, side, num_cards)` - Broad research to discover arguments

**Example Usage:**
```python
# Current: specify topic upfront
research_evidence(resolution, side, topic="economic impacts")

# New: specify the claim you want to prove
research_for_claim(
    claim="TikTok ban would eliminate 100,000 US jobs",
    resolution=resolution,
    side=Side.CON
)

# New: find gaps and research automatically
gaps = identify_gaps(case, debate_file, side)
for gap in gaps.missing_evidence:
    research_for_claim(gap.claim, resolution, side)
```

### Phase 4: Iterative Workflow

**New CLI Command: `debate synthesize`**

```bash
# Evidence-first: build case from existing evidence
uv run debate synthesize "Resolved: ..." --side pro --from-evidence

# Argument-first: draft case, then research gaps
uv run debate synthesize "Resolved: ..." --side pro --draft-first

# Iterative: refine existing case with evidence
uv run debate synthesize "Resolved: ..." --side pro --refine --case-file case.json

# Interactive: agent suggests next steps
uv run debate synthesize "Resolved: ..." --side pro --interactive
```

**Interactive Mode:**
```
Step 1/5: Analyzing available evidence...
  Found 12 cards covering: economic impacts, privacy concerns, security risks

Step 2/5: Synthesizing argument ideas...
  Suggested Contention 1: Economic harm (backed by 5 cards)
  Suggested Contention 2: Privacy violations (backed by 4 cards)
  Suggested Contention 3: National security (backed by 3 cards)

Step 3/5: Identifying gaps...
  ⚠ Contention 1 needs impact evidence (jobs → recession link)
  ⚠ Contention 2 needs answers to "other apps do same thing"

What would you like to do?
  [1] Research missing evidence for gaps
  [2] Generate draft case from current evidence
  [3] Refine contentions to match evidence
  [4] Add new contention ideas
>
```

### Phase 5: Speech Generation Integration

**Extend `debate/debate_agent.py`**

When generating speeches, agent should:
1. Check available evidence FIRST
2. Build arguments around what evidence proves
3. Only make unsupported claims if no relevant evidence exists
4. Suggest research needs during speech prep

**Speech Generation Modes:**
```python
def generate_speech(
    goal: str,
    round_state: RoundState,
    debate_file: Optional[DebateFile] = None,
    synthesis_mode: str = "balanced",  # evidence_first | argument_first | balanced
    **kwargs
) -> str:
    """
    Generate speech with flexible evidence-argument flow

    - evidence_first: Build speech around available evidence
    - argument_first: Make strategic arguments, cite evidence where available
    - balanced: Blend both approaches
    """
```

## Validation Integration

The validation system fits into this as a quality check:

```
Evidence ←→ Arguments ←→ Speeches
              ↓
          Validation
              ↓
        (errors/warnings)
              ↓
      Refine/Research
```

**Validation checks:**
- ✓ All citations backed by evidence files (implemented)
- ✓ Quoted text matches bolded portions (implemented)
- ⚠ Arguments without any evidence support (new)
- ⚠ Evidence not used in any arguments (new)
- ℹ Evidence usage statistics (new)

## Example Workflows

### Workflow 1: Start from Research
```bash
# Cut evidence cards
uv run debate research "Resolved: Ban TikTok" --side con --topic "economic impacts" --num-cards 5
uv run debate research "Resolved: Ban TikTok" --side con --topic "privacy concerns" --num-cards 4

# Synthesize case from evidence
uv run debate synthesize "Resolved: Ban TikTok" --side con --from-evidence

# Identify gaps
uv run debate validate case.json --identify-gaps

# Research gaps
uv run debate research "Resolved: Ban TikTok" --side con --fill-gaps case.json
```

### Workflow 2: Start from Arguments
```bash
# Generate draft case (no evidence)
uv run debate generate "Resolved: Ban TikTok" --side con --draft

# Analyze what evidence is needed
uv run debate synthesize "Resolved: Ban TikTok" --side con --analyze-needs case.json

# Research each need
uv run debate research "Resolved: Ban TikTok" --side con --for-claim "Ban costs 100k jobs"

# Refine case with evidence
uv run debate synthesize "Resolved: Ban TikTok" --side con --refine case.json
```

### Workflow 3: Interactive Iteration
```bash
# Start interactive synthesis
uv run debate synthesize "Resolved: Ban TikTok" --side con --interactive

# Agent guides through:
# 1. Research some initial evidence
# 2. Analyze evidence for argument ideas
# 3. Draft contentions
# 4. Identify gaps
# 5. Research gaps
# 6. Refine case
# 7. Validate
# 8. Repeat until satisfied
```

## Technical Architecture

```
┌─────────────────────────────────────────────────────┐
│                   CLI Layer                          │
│  (debate generate, research, synthesize, validate)   │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────┴───────────────────────────────────┐
│              Synthesis Orchestrator                  │
│         (synthesis_agent.py - NEW)                   │
│  • analyze_evidence()                                │
│  • synthesize_arguments()                            │
│  • identify_gaps()                                   │
│  • orchestrate_iteration()                           │
└─────┬──────────────────────────────────────┬────────┘
      │                                      │
┌─────┴─────────┐                  ┌─────────┴────────┐
│ Case Generator│                  │ Research Agent   │
│ (enhanced)    │                  │ (enhanced)       │
│               │                  │                  │
│ • from_scratch│                  │ • for_topic      │
│ • argument_1st│                  │ • for_claim      │
│ • evidence_1st│                  │ • fill_gaps      │
│ • iterative   │                  │ • exploratory    │
└───────┬───────┘                  └────────┬─────────┘
        │                                   │
        └─────────────┬─────────────────────┘
                      │
        ┌─────────────┴──────────────┐
        │     Evidence Storage        │
        │  (debate files + cards)     │
        └─────────────┬───────────────┘
                      │
        ┌─────────────┴───────────────┐
        │   Validation System (NEW)    │
        │ • validate_citations()       │
        │ • identify_gaps()            │
        │ • check_evidence_usage()     │
        └──────────────────────────────┘
```

## Next Steps

1. ✓ Implement validation system (done)
2. Create synthesis_agent.py with evidence analysis
3. Add evidence-first case generation mode
4. Enhance research agent with targeted research
5. Add CLI commands for synthesis workflows
6. Test bidirectional flows
7. Add interactive mode
