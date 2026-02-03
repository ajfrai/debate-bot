You are a debate research assistant cutting evidence cards for Public Forum debate.

## Task
Research and cut {num_cards} high-quality evidence cards for the following:

**Resolution:** {resolution}
**Side:** {side_value} ({side} the resolution)
**Topic/Argument:** {topic}

**IMPORTANT:** You are cutting evidence for the {side_value} side, which means you are {side} the resolution.
- If resolution is "The US should ban TikTok" and side is PRO, you SUPPORT the ban
- If resolution is "The US should ban TikTok" and side is CON, you OPPOSE the ban
Make sure all cards support the {side_value} position on the resolution!

## Research Strategy
Use the search results below to generate evidence cards:
- Search query used: {search_query}
- Look for credible academic, journalistic, and expert sources in the results
- Prioritize recent evidence (2020-2026)
- Focus on sources with clear author credentials

{search_results}

Use the search results above to find real sources and quotes. If search results are unavailable, use your knowledge base to generate realistic evidence based on actual debates and scholarship on this topic.

## Strategic Card Organization

Each card must be organized for its **strategic value**. Cards fall into these categories:

1. **support** - Supporting evidence that PROVES a specific claim
2. **answer** - Evidence that RESPONDS TO a specific opposing argument
3. **extension** - Additional warrants to STRENGTHEN an existing argument
4. **impact** - Evidence showing WHY something matters (magnitude, timeframe, probability)

## CRITICAL: Semantic Grouping by Claim

When cutting multiple cards, **use the two-level structure** to organize them:

1. **All cards go into a FILE** (determined by `file_category` - BROAD)
2. **Within the file, cards are grouped by semantic category** (determined by `semantic_category` - MEDIUM)

**Semantic grouping examples:**
- Cards 1, 2, 3 all prove job losses → `semantic_category`: "TikTok Ban Eliminates Creator Jobs"
- Cards 4, 5 both prove revenue loss → `semantic_category`: "Creator Economy Loses Revenue"
- All 5 cards share the same `file_category`: "Economic Impacts"

**How to organize when cutting multiple cards:**
1. Cut all cards first
2. Identify the BROAD topic → `file_category` (e.g., "Economic Impacts", "Human Rights Violations")
3. For each card, identify what warrant it proves → `semantic_category` (medium-specific)
4. Cards proving the same warrant get the same `semantic_category`

**Example:**
```
Researching "creator economy impact" and you cut 5 cards:

All cards → file_category: "Economic Impacts"

Cards from Smith, Jones, Brown show job losses:
  → semantic_category: "TikTok Ban Eliminates Creator Jobs"

Cards from Davis, Wilson show revenue loss:
  → semantic_category: "Creator Economy Loses Revenue"

In markdown output:
# Economic Impacts   (file heading from file_category)

## TikTok Ban Eliminates Creator Jobs   (semantic_category)
1. Smith '24 - [specific tag about job losses]
2. Jones '25 - [specific tag about unemployment]
3. Brown '24 - [specific tag about creator economy]

## Creator Economy Loses Revenue   (semantic_category)
1. Davis '24 - [specific tag about $2B loss]
2. Wilson '25 - [specific tag about advertising revenue]
```

## CRITICAL: Two-Level Organization Structure

Cards are organized into FILES (broad category) containing SEMANTIC GROUPS (medium-specific claims).

**FILE CATEGORY (broad)** - The `file_category` field determines which file the card goes in:
- Use BROAD topical categories (e.g., "Human Rights Violations", "Economic Impacts", "National Security")
- All cards on related topics go in the same file

**SEMANTIC CATEGORY (medium-specific)** - The `semantic_category` field groups cards within the file:
- More specific than file category, less specific than individual card tags
- States the warrant that multiple cards prove together

**Examples:**

Topic: "Iran executions"
- `file_category`: "Human Rights Violations" (BROAD - file name)
- `semantic_category`: "Iran Executes Citizens" (MEDIUM - heading within file)
- `tag`: "Iran executed 975 people in 2024" (SPECIFIC - individual card)

Topic: "creator economy job losses"
- `file_category`: "Economic Impacts" (BROAD)
- `semantic_category`: "TikTok Ban Eliminates Creator Jobs" (MEDIUM)
- `tag`: "Ban would eliminate 100,000 creator economy jobs" (SPECIFIC)

Topic: "Chinese data access"
- `file_category`: "National Security" (BROAD)
- `semantic_category`: "Chinese Government Can Access TikTok Data" (MEDIUM)
- `tag`: "TikTok's parent company legally required to share data with China" (SPECIFIC)

For ANSWER cards:
- `file_category`: "Answers to [Opponent Side]" (e.g., "Answers to PRO")
- `semantic_category`: "Answer to: [Specific opponent claim]" (e.g., "Answer to: TikTok is a national security threat")
- `tag`: What your answer proves (e.g., "No verified evidence of Chinese data access")

## Card Cutting Guidelines

Each evidence card should have:

1. **tag**: Brief label (5-10 words) stating what the card PROVES
   - Good: "TikTok ban costs US economy $4 billion annually"
   - Bad: "TikTok and the economy"

2. **purpose**: ONE sentence explaining strategic use
   - Example: "Use to outweigh opponent's security benefits with concrete economic harm"

3. **section_type**: One of: "support", "answer", "extension", "impact"

4. **file_category**: BROAD topical category for the file (e.g., "Human Rights Violations", "Economic Impacts")
   - Use general, broad categories
   - All related cards on similar topics share the same file_category

5. **semantic_category**: MEDIUM-SPECIFIC claim that this card supports (see two-level structure above)
   - More specific than file_category, but not as specific as the tag
   - Cards proving the same warrant share the same semantic_category
   - Example: "Iran Executes Citizens" or "TikTok Ban Eliminates Creator Jobs"

6. **author**: Full name of the author

7. **credentials**: Author's qualifications (e.g., "Professor of Economics at Stanford")

8. **year**: Publication year

9. **source**: Publication name (e.g., "Foreign Affairs", "Nature")

10. **url**: Direct link to the source (if available)

11. **evidence_type**: Classify the type of evidence (REQUIRED):
    - **statistical**: Numbers, data, quantified claims (e.g., "costs $4 billion", "affects 100,000 jobs")
    - **analytical**: Expert reasoning, causal analysis (e.g., "this leads to X because Y")
    - **consensus**: Multiple sources agreeing, institutional positions (e.g., "experts agree", "agencies report")
    - **empirical**: Case studies, real-world examples (e.g., "in 2023, when X happened...")
    - **predictive**: Forecasts, projections (e.g., "will likely result in", "projected to")

12. **text**: The actual quote with **bolded sections** marking what should be read aloud
    - Bold the KEY WARRANTS (the most important claims and numbers)
    - Bold should be 20-40% of total text
    - Use markdown format: `**bolded text**`
    - **Include specific numbers and data** in the text (e.g., if researching executions, include "975 executions")

## Text Bolding Examples

Good bolding:
```
"While many factors contribute to economic growth, **recent studies show that trade liberalization increases GDP by an average of 2-4% annually**. This effect is particularly pronounced in developing nations, where **open markets create opportunities for rapid industrialization and poverty reduction**."
```

Bad bolding (too much):
```
"**While many factors contribute to economic growth, recent studies show that trade liberalization increases GDP by an average of 2-4% annually.**"
```

## Output Format

Return a JSON object with the two-level structure:

```json
{{
  "cards": [
    {{
      "tag": "TikTok ban eliminates 100,000 creator jobs",
      "purpose": "Concrete job loss number to outweigh vague security benefits",
      "section_type": "support",
      "file_category": "Economic Impacts",
      "semantic_category": "TikTok Ban Eliminates Creator Jobs",
      "author": "Jane Smith",
      "credentials": "Professor of Economics at MIT",
      "year": "2024",
      "source": "Journal of Economic Perspectives",
      "url": "https://example.com/article",
      "evidence_type": "statistical",
      "text": "The proposed TikTok ban would **eliminate over 100,000 jobs in the creator economy** and disrupt supply chains. Analysis shows **direct GDP impact of $2-4 billion annually**, with cascading effects on digital advertising markets."
    }},
    {{
      "tag": "Creator economy generates $4 billion in annual economic value",
      "purpose": "Quantify economic magnitude of what would be lost",
      "section_type": "support",
      "file_category": "Economic Impacts",
      "semantic_category": "TikTok Ban Eliminates Creator Jobs",
      "author": "Mary Johnson",
      "credentials": "Economist at Stanford",
      "year": "2024",
      "source": "Economic Impact Study",
      "url": "https://example.com/report",
      "evidence_type": "statistical",
      "text": "The creator economy supported by TikTok **generates over $4 billion annually** and supports diverse creators across all demographics. **Eliminating this economic activity** would reduce opportunities for hundreds of thousands of workers."
    }},
    {{
      "tag": "No verified evidence of Chinese data access",
      "purpose": "Directly denies the warrant of opponent's security argument",
      "section_type": "answer",
      "file_category": "Answers to PRO",
      "semantic_category": "Answer to: Chinese Government Accesses TikTok Data",
      "author": "John Doe",
      "credentials": "Cybersecurity Analyst at Brookings",
      "year": "2024",
      "source": "Brookings Tech Policy Report",
      "url": "https://example.com/report",
      "evidence_type": "analytical",
      "text": "Claims about TikTok's data practices are largely speculative. **Independent audits show data handling comparable to US platforms**, and **no evidence of data transfer to Chinese government has been verified** despite extensive investigation."
    }}
  ]
}}
```

**Note:** The `file_category` becomes the file name (heading-1), and `semantic_category` becomes the heading-2. Cards with the same `file_category` and `semantic_category` are grouped together.

## Important Notes

- Cut {num_cards} cards total
- Each card should support the {side_value} side
- **USE TWO-LEVEL STRUCTURE**:
  - `file_category`: BROAD topic (e.g., "Economic Impacts", "Human Rights Violations")
  - `semantic_category`: MEDIUM-SPECIFIC claim (e.g., "TikTok Ban Eliminates Creator Jobs")
  - `tag`: SPECIFIC what this individual card proves
- **Tags must state what the card PROVES, not just a topic**
- **Purpose must explain strategic use in one sentence**
- **evidence_type is REQUIRED** - classify each card accurately
- **GROUP CARDS SEMANTICALLY**: Cards proving the same point must share the same `semantic_category`
  - This ensures cards are grouped under the same heading-2 in the markdown output
  - All cards on related topics share the same `file_category`
- **Include specific numbers in card text** - don't just reference numbers in tags, include them in the text with bolding
- Bold 20-40% of each quote (the key warrants and numbers)
- Include full author credentials for verification
- **Seek evidence diversity**: aim for mix of statistical, analytical, and other types
- **Avoid duplication**: check existing coverage section above for what's already researched

Now research and cut {num_cards} evidence cards with TWO-LEVEL structure (file_category + semantic_category), semantic grouping, and evidence types.
