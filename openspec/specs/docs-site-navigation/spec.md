# docs-site-navigation

## Purpose

The docs site (landing page, blog posts, and walkthrough flow pages) shares a
single navigation system: a global rail that is identical on every page and a
section strip generated from shared data. Navigation data — the global section
list, the milestone list, and the walkthrough flow list — lives in one shared
JavaScript module (`docs/site-nav.js`), so adding or renaming a milestone or
flow means editing one file, not per-page markup. Every page degrades to a
usable, script-free baseline.

## Requirements

### Requirement: Single source of truth for navigation
The docs site SHALL define its navigation data (the global section list, the
milestone list, and the walkthrough flow list) in one shared JavaScript module
(`docs/site-nav.js`) that every page includes. Adding or renaming a milestone or
flow SHALL require editing only that module, not per-page markup.

#### Scenario: Add a new milestone
- **WHEN** a maintainer adds a new milestone (e.g. M10) by appending one entry
  to the milestone list in `site-nav.js`
- **THEN** the milestone appears in the stepper on every blog page with no edits
  to any HTML page

#### Scenario: No per-page milestone markup
- **WHEN** any blog page's HTML source is inspected
- **THEN** it does not contain a hand-embedded milestone list; the stepper is
  produced from the shared module

### Requirement: Global rail identical on every page
Every docs page SHALL present the same global rail: the `PROKURA` wordmark
linking home on the left, and the same ordered set of destinations on the right
(Walkthrough, Blog, Architecture, GitHub), with identical labels and slot
meanings across pages.

#### Scenario: Rail parity across page types
- **WHEN** the global rail is compared between the landing page, a blog page,
  and a walkthrough page
- **THEN** the wordmark and the right-side destination set (labels and order)
  are identical on all three

#### Scenario: Current section is marked
- **WHEN** a page within a section (blog, or walkthrough) renders its global
  rail
- **THEN** that section's entry is visually marked as current, and the marking
  is applied to at most one entry

### Requirement: Section strip generated from shared lists
Within a section, the page SHALL render a section strip from the shared lists:
blog pages SHALL show the complete milestone stepper (M0 through the latest
milestone) and walkthrough pages SHALL show the flow list. The current item in
the strip SHALL be marked and non-navigating.

#### Scenario: Blog stepper is complete on every post
- **WHEN** any blog post (including the earliest, `m1`–`m4`) renders
- **THEN** its stepper lists every milestone from M0 through the latest, not a
  prefix truncated at the milestone that existed when the post was written

#### Scenario: Walkthrough cross-link preserved
- **WHEN** a walkthrough flow page that originates from a milestone renders
- **THEN** its section area still offers a link to that milestone's blog post

### Requirement: Usable without JavaScript
Each docs page SHALL remain navigable without JavaScript: at minimum the
wordmark SHALL link home and a link to the GitHub repository SHALL be reachable
without script execution.

#### Scenario: Script disabled
- **WHEN** a page is loaded with JavaScript disabled
- **THEN** the reader can still reach the site home and the GitHub repository
