## ADDED Requirements

### Requirement: Defined ADR format

The ADR corpus SHALL use a single defined format captured in `docs/adr/0000-template.md`. Each ADR SHALL contain: a stable number and title, a status (`accepted` | `superseded` | `proposed`), the context/problem, the decision made, the alternatives considered, the consequences (including accepted downsides), and a source citation. Free-form decision notes without this structure SHALL NOT count as ADRs.

#### Scenario: Every ADR follows the template
- **WHEN** any file in `docs/adr/` (other than the template and README) is reviewed
- **THEN** it has a number, title, status, context, decision, alternatives, consequences, and a source citation

### Requirement: One ADR per material decision

Every material architectural decision SHALL be recorded as exactly one accepted ADR. The set of material decisions SHALL include, at minimum, SPEC-REVIEW findings F1–F9 and decisions Q1–Q7, plus locked choices not captured as a numbered finding (e.g. broker-brokered grants vs broker-run OAuth, broker's own token audience, TTL honesty/re-issuance interval, GitHub App vs OAuth app, sole-tuple-writer invariant, ntfy notify-only, Mailpit demo sink). A decision SHALL NOT be split across multiple ADRs or merged with an unrelated decision.

#### Scenario: Known decision set is fully covered
- **WHEN** the decision inventory is checked against the ADR corpus
- **THEN** each of F1–F9, Q1–Q7, and every listed locked choice maps to exactly one accepted ADR, or to an explicit, reasoned exclusion

#### Scenario: No decision is silently missing
- **WHEN** a material decision has no ADR and no recorded exclusion
- **THEN** the reconciliation is incomplete and the gap is listed as an open item

### Requirement: Each ADR is traceable to its source of truth

Because OpenSpec specs and design docs remain the working source of truth, each ADR SHALL cite where its decision actually lives — a SPEC-REVIEW finding/decision ID, a specific `openspec/specs/<cap>/spec.md`, or a change `design.md`/`proposal.md`. An ADR SHALL NOT introduce a decision that contradicts its cited source; if it would, the contradiction is flagged rather than silently resolved.

#### Scenario: Citation resolves
- **WHEN** an ADR's source citation is followed
- **THEN** it points to an existing SPEC-REVIEW ID or OpenSpec artifact that contains or made the decision

#### Scenario: Contradiction is surfaced, not hidden
- **WHEN** an ADR's stated decision conflicts with its cited source
- **THEN** the conflict is recorded as an open item for real resolution, not overwritten in the ADR

### Requirement: Navigable index

`docs/adr/README.md` SHALL list every ADR by number, title, and status, so the corpus is navigable and superseded decisions are visibly marked.

#### Scenario: Index matches the corpus
- **WHEN** the ADR index is compared to the files in `docs/adr/`
- **THEN** every ADR appears with its current status and no listed ADR is missing a file (and vice versa)

### Requirement: Reconciliation is documentation-only

The reconciliation SHALL NOT make or alter any architectural decision. If the inventory surfaces a decision that was never actually settled, it SHALL be flagged for resolution in its proper venue (a new change or spec), and its ADR SHALL NOT be marked `accepted` until it is genuinely decided.

#### Scenario: Unsettled decision is not fabricated as accepted
- **WHEN** the inventory finds an apparent decision with no real resolution in any source
- **THEN** it is flagged as open and no `accepted` ADR is created to paper over it
