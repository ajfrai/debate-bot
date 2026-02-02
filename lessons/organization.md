# Evidence Organization Lessons

This file contains lessons about organizing evidence for quick retrieval during rounds.

## File Structure

### Directory Organization
```
evidence/{resolution}/
  pro/
    support/    # Cards that prove PRO claims
    answer/     # Cards that answer CON arguments
    extension/  # Additional warrants for PRO args
    impact/     # Impact calculus for PRO
  con/
    support/    # Cards that prove CON claims
    answer/     # Cards that answer PRO arguments
    extension/  # Additional warrants for CON args
    impact/     # Impact calculus for CON
```

### Filename = Tag
- File name should be the slugified card tag
- Makes `ls` and `grep` useful for finding cards
- Example: `tiktok_ban_eliminates_100k_jobs.md`

## Quick Search Tips

### Finding Cards Fast
```bash
ls pro/answer/              # See all your answers
grep -r "billion" pro/      # Find cards with "billion"
grep -r "security" con/     # Find opponent's security args
```

### INDEX.md Navigation
- Always check INDEX.md first for overview
- Organized by section type and argument
- Links directly to card files

## Cross-Referencing

### Cards Can Appear Multiple Places
- Same card might be "support" for one argument AND "answer" to another
- Don't duplicate the card - reference by ID
- Example: Economic harm card supports "ban hurts economy" AND answers "ban has no costs"

## During Rounds

### Prep Time Efficiency
- Know your file structure before the round
- Pre-mark key cards for each speech
- Have answers ready before you need them

### Flowing to Evidence
- Note which cards you've read
- Track opponent's arguments to find answers
- Don't re-read the same card twice

---

*Add new lessons below as they're learned:*
