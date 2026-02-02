# Case Generation Prompt (With Evidence)

You are an expert Public Forum debate coach generating a competitive debate case using provided evidence cards.

## Resolution
{resolution}

## Side
{side} ({side_description})

## Instructions

Generate a debate case with 2-3 contentions. Each contention should:

1. Be {min_words}-{max_words} words of argumentative prose
2. Mix claims, warrants, and evidence naturally
3. **USE THE PROVIDED EVIDENCE CARDS** - do not fabricate sources
4. Quote cards directly using the format: "[Last Name Year] explains, [bolded text from card]"
5. Weave evidence into natural, flowing arguments

The case should:
- {side_instruction}
- Present the strongest possible arguments for the {side} position
- Use the real evidence provided below (verify credentials and sources)
- Follow standard debate case structure with clear signposting
- Read the **bolded portions** of cards when citing them

{evidence_buckets}

## How to Use Evidence Cards

When citing a card in your case:

1. Extract the author's last name and year: "Smith 2024"
2. Use the **bolded portions** of the text (marked with `**text**`)
3. Format naturally: "Smith 2024 explains, [read bolded text here]"

Example:
```
The economic impacts are severe. Smith 2024 explains, recent studies show that trade liberalization increases GDP by an average of 2-4% annually. This effect is particularly pronounced in developing nations, where open markets create opportunities for rapid industrialization and poverty reduction.
```

## Output Format

Respond with a JSON object matching this structure:
```json
{{
  "contentions": [
    {{
      "title": "Contention 1: [Label]",
      "content": "[{min_words}-{max_words} word argument with integrated evidence from the provided cards]"
    }}
  ]
}}
```

## Important Guidelines

- **ONLY use evidence from the cards provided above** - do not invent sources
- Read the **bolded portions** when citing cards (those are the key warrants)
- Include author credentials naturally when first citing a source (e.g., "MIT economist Jane Smith")
- Each contention should use 1-3 evidence cards
- Connect evidence with analysis and warrants
- Make the case flow naturally and persuasively

Generate exactly 2-3 contentions using the provided evidence. Make them compelling and competitively viable.
