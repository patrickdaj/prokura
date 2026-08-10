## 1. Build the shared module

- [x] 1.1 Create `docs/site-nav.js` with the three data arrays — `SECTIONS`
      (Walkthrough, Blog, Architecture, GitHub), `MILESTONES` (M0–M9), `FLOWS`
      (the walkthrough flow/surface pages with optional origin-blog) — per
      design.md D2
- [x] 1.2 Implement path/section resolution from `location.pathname` (the
      `prefix` for root vs `blog/` vs `walkthroughs/`, current-section and
      current-item detection) and the rail-injection into a container the
      script owns; defensive if the container is absent (D3, D5)
- [x] 1.3 Render Tier 1 (global rail, current section marked) on all pages and
      Tier 2 (full milestone stepper on blog, flow strip + origin-blog
      cross-link on walkthroughs) from the shared lists (D4)
- [x] 1.4 Add any needed styling hooks to `docs/walkthroughs/walkthrough.css`,
      reusing existing `.rail`/`.nav`/`.steps`/`.cur`/`.done` styles (D6)

## 2. Adopt the shared rail on every page

- [x] 2.1 Replace the hand-embedded `.rail` in `docs/index.html` with the
      shared include + a `<noscript>` fallback (home + GitHub)
- [x] 2.2 Replace the `.rail` (stepper) in `blog/index.html` and `blog/m1`–`m9`
      with the shared include + `<noscript>` fallback; delete the truncated
      hand-embedded steppers
- [x] 2.3 Replace the `.rail` in `walkthroughs/index.html` and every flow/surface
      page (delegation, brokering, approval, rag, mcp, authority, revocation,
      claude-code, postmortem) with the shared include + `<noscript>` fallback

## 3. Verify and ship

- [x] 3.1 Confirm the global rail is byte-identical across landing, a blog page,
      and a walkthrough page, and that exactly one section is marked current
      (spec: Global rail identical on every page)
- [x] 3.2 Confirm every blog post (including `m1`–`m4`) shows the complete M0–M9
      stepper and each walkthrough keeps its origin-blog cross-link (spec:
      Section strip generated from shared lists)
- [x] 3.3 Render each page type in a browser and screenshot the rail in light
      and dark themes; verify relative links resolve from root, `blog/`, and
      `walkthroughs/` (verification discipline: look, don't assume)
- [x] 3.4 Verify the no-JavaScript fallback keeps home + GitHub reachable
      (spec: Usable without JavaScript)
- [x] 3.5 Commit to main and push
