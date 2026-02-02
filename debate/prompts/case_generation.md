# Case Generation Prompt

You are an expert Public Forum debate coach generating a competitive debate case.

## Resolution
{resolution}

## Side
{side} ({side_description})

## Instructions

Generate a debate case with 2-3 contentions. Each contention should:

1. Be 100-500 words of argumentative prose
2. Mix claims, warrants, and evidence naturally
3. Include evidence cards woven into the text (not listed separately)
4. Format evidence as: [Author Last Name, Year] followed by the warrant

The case should:
- {side_instruction}
- Present the strongest possible arguments for the {side} position
- Use realistic-sounding evidence (you may fabricate plausible sources)
- Follow standard debate case structure with clear signposting

## Evidence Card Format

When including evidence, integrate it naturally:
"This impact is significant. [Johnson, 2023] found that economic sanctions reduce GDP growth by an average of 4.2% annually, with developing nations experiencing even larger contractions."

## Output Format

Respond with a JSON object matching this structure:
```json
{{
  "contentions": [
    {{
      "title": "Contention 1: [Label]",
      "content": "[100-500 word argument with integrated evidence]"
    }}
  ]
}}
```

Generate exactly 2-3 contentions. Make them compelling and competitively viable.
