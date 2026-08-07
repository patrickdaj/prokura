# Design — Expand Threat Model

## Context

`docs/threat-model.md` today is a scoped working draft: TCB definition, TTL-honesty table, and a few M2 residual risks, with an explicit note that the full model (assets, actors, STRIDE per flow, mitigations) is an M6 deliverable. This change is that deliverable. It is **adversary-centric**: given the now-fixed architecture, what can each attacker class do to each flow, and what stops them? It runs on `apply` after M6 and — ideally — after the sibling `security-review` change, whose findings register feeds the attack trees.

## Goals / Non-Goals

**Goals**
- A complete threat model meeting the `threat-model` spec's acceptance criteria: assets, attacker model, trust boundaries, STRIDE per flow (A/B/C/D + MCP), attack trees for high-value targets, threat→mitigation mapping, residual-risk register.
- Every threat evaluated against a *defined* adversary and dispositioned (mitigated-by-control or accepted-residual).
- Preserve the M2 draft's TCB statement and TTL table; retire its deferral header.

**Non-Goals**
- No control verification — that is `security-review` (this change consumes its findings, doesn't reproduce them).
- No ADR authoring — that is `adr-reconciliation`.
- No production hardening or new runtime behavior; accepted residuals stay accepted.

## Method

**Framework: STRIDE-per-interaction + attack trees.** STRIDE gives systematic breadth (six categories × five surfaces = a grid with no silent gaps); attack trees give depth on the few targets whose compromise is catastrophic. The two compose: STRIDE surfaces the threats, attack trees elaborate the worst ones.

**Attacker model first.** Define adversary classes and their capabilities before enumerating threats, so every STRIDE cell is judged against a concrete attacker rather than a vague "hacker":
- **Compromised/malicious agent** — holds a valid delegated token for its user; tries to exceed granted scope, reach other users' grants, or replay approvals.
- **Malicious MCP client (DCR)** — can self-register; has no consent tuple; tries to ride DCR into grant access.
- **On-network attacker** — sits on the compose network (no mTLS); can observe/inject between services.
- **Malicious grant-linking user** — legitimately links a provider account; tries to authorize agents they don't operate or corrupt tuples.
- **Curious insider** — can read logs/stores; tries to extract secrets or user data.

**Coverage grid.** `{flow × STRIDE}` for A/B/C/D + MCP is filled exhaustively — each cell is a concrete threat+mitigation or a reasoned N/A. High-value targets get attack trees: broker compromise, tuple forgery/cross-user write, approval spoof/replay, RAG confused-deputy.

**Disposition discipline.** Each threat links to a `security-baseline` requirement or spec scenario that mitigates it (e.g. spoofed-notification-inert ← human-approval; over-broad-scope-refused ← token-brokering; end-user-evaluated authz ← rag-authorization) or lands in the residual-risk register with a rationale. This mapping is what makes the model actionable rather than a list of fears.

## Seed threats from prior work

The SPEC-REVIEW findings already frame several threats — the model formalizes and extends them rather than starting blank:
- **F5** free-text `binding_message` → tampering/spoofing on approval; mitigated by structured payload + reference-ID binding + trusted rendering.
- **F7** ntfy topics as open capabilities → spoofed-notification threat; mitigated by notify-only + decisions-only-in-authenticated-UI.
- **F8** single-use action token → replay threat; mitigated by hash-verify + consumed-ID rejection.
- **F1 / Q3** `can_use` tuple integrity → elevation via tuple forgery; mitigated by broker-sole-writer + operator==owner (a trusted-code assumption the broker-compromise tree must account for).
- **§11** RAG confused-deputy → information disclosure; the acknowledged trade-off gets an explicit tree and residual note.

## Key decisions

- **`threat-model` is a capability with acceptance criteria, not just a doc.** Because "the docs ARE the product", making completeness *checkable* (no empty STRIDE cell, every threat dispositioned, every high-value target has a tree) turns the threat model into something verifiable at archive time instead of a subjective essay.
- **Consume, don't reproduce, the security-review findings.** Running after `security-review` lets confirmed control weaknesses become concrete attack-tree leaves, avoiding two changes analyzing the same controls from scratch.
- **Adversary-defined threats only.** Forbidding threats that assume an undefined attacker keeps the model grounded and prevents scope creep into implausible production-only attacks the compose reference doesn't claim to resist.

## Risks / Trade-offs

- **Overlap risk with `security-review`.** Mitigated by the lens split (control- vs adversary-centric) and by sequencing this change after the review so it references findings rather than re-deriving them.
- **Completeness is judgment-laden.** The acceptance criteria (grid fully filled, trees present, dispositions complete) make it as objective as practical, but "did we find every threat" is inherently open — the residual-risk register and the `security-review` test-gaps are the honesty valve.

## Rollout

None runtime. On archive, `threat-model` joins `openspec/specs/`; `docs/threat-model.md` becomes the complete model and its findings feed `adr-reconciliation` (decisions behind mitigations) and any follow-up spec-gap deltas.
