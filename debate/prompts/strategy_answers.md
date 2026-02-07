You are a debate strategist preparing ANSWERS to opponent arguments.

Resolution: {resolution}
Your side: {side}
Opponent side: {opponent_side}

Already prepared answers: {existing_answers}

Generate 40-50 ANSWER TAGS (responding to likely opponent claims). Use a MIX of these 5 types (20% each):

1. STOCK - Conventional responses to predictable arguments
2. CREATIVE - Outside the box turns, counterintuitive defenses
3. NICHE - Academic frameworks to reframe opponent claims
4. OPPORTUNISTIC - Concede and turn opponent impact scenarios
5. SECOND_ORDER - Chain opponent's argument to show it leads to worse outcome for them
   - Format: "AT: [Their claim] leads to [bad consequence for them]"
   - Can chain on other answers (build deep refutation chains)

EXAMPLES by type:

STOCK:
- AT: Economic costs outweighed by national security benefits
- AT: Privacy already protected by existing regulations

CREATIVE:
- AT: Ban proves government overreach their impact claims warn against
- AT: Censorship attempt validates slippery slope to authoritarianism

NICHE:
- AT: Coase theorem suggests market solutions superior to ban
- AT: Securitization theory explains overblown threat perception

OPPORTUNISTIC (concede and turn):
- AT: Job losses real but creative destruction accelerates innovation
- AT: Privacy violations exist but ban sets worse precedent

SECOND_ORDER (chain their argument):
- AT: Their privacy concern leads to broader surveillance precedent
- AT: Economic harm claim leads to protectionist spiral

CRITICAL RULES:
- AVOID semantic duplicates - each answer must respond to a MEANINGFULLY DIFFERENT opponent claim
- Do NOT rephrase the same response in different words
- Mix all 5 types roughly equally (20% each)
- Skip any tag too similar to existing answers above
- Each tag starts with "AT:" and is 5-12 words

Output as numbered list. Generate the tag first, then classify it.
Format: N. AT: tag | TYPE (where TYPE is STOCK, CREATIVE, NICHE, OPPORTUNISTIC, or SECOND_ORDER)

1. AT: Economic costs outweighed by national security benefits | STOCK
2. AT: Ban proves government overreach their impact claims warn against | CREATIVE
3. AT: Coase theorem suggests market solutions superior to ban | NICHE
4. AT: Job losses real but creative destruction accelerates innovation | OPPORTUNISTIC
5. AT: Their privacy concern leads to broader surveillance precedent | SECOND_ORDER
...etc
