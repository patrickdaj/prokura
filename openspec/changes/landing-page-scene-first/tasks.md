## 1. Hero rewrite

- [ ] 1.1 Replace the H1 and lede in `docs/index.html` with the verbatim copy
      from design.md D1 (eyebrow, chips, and `<title>` unchanged)
- [ ] 1.2 Add the fail-closed terminal panel after the chips row using the
      existing `screen`/`bar`/`body term` classes and walkthrough span
      conventions, with the one-line "Fail closed, not fail open" caption
      (design.md D2)

## 2. "Why this exists" Q-cards

- [ ] 2.1 Replace each `.qcard`'s `.a` answer with the today→ / prokura→
      pair and mono mechanism tag per the design.md D3 table
- [ ] 2.2 Add the supporting classes (muted today line, ink prokura line,
      `.qcard .mech` tag) to the page's inline `<style>` block only; trim
      the section's `p.lead` so it doesn't restate the new lede (D4, D5)

## 3. Verify and ship

- [ ] 3.1 Confirm the diff touches only `docs/index.html` and nothing below
      the "Why this exists" section changed (spec: Depth sections unchanged)
- [ ] 3.2 Render the page in a browser and screenshot the hero + Q-cards in
      light and dark themes; check the panel stays ~7 lines and the hero
      fits the first screenful (verification discipline: look, don't assume)
- [ ] 3.3 Commit to main and push
