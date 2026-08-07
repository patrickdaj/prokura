## Why

`docs/threat-model.md` is an explicit working draft: it covers only what M2 made concrete (broker TCB, TTL honesty, a handful of M2 residual risks) and its own header defers the full model — assets, actors, STRIDE per flow, mitigations — to M6. With M1–M5 and the MCP milestone complete, the architecture is now fixed and can be modeled adversarially end to end. This change delivers M6's threat-model deliverable: expand the draft into a complete, adversary-centric threat model so the attack surface of every flow is understood, not assumed.

This is the second of three M6 ("Polish") follow-ups. Its lens is **adversary-centric** (what can an attacker do to each flow?), complementary to the sibling `security-review` change's **control-centric** lens (are the hard rules enforced?) and the `adr-reconciliation` change's **decision-centric** lens. The three cross-reference rather than duplicate.

## What Changes

- **New `threat-model` capability spec** stating what a complete Prokura threat model MUST contain, as verifiable acceptance criteria: named assets and actors, an explicit trust boundary / TCB diagram, a STRIDE analysis per flow (A delegation, B brokering, C approval, D RAG) plus the MCP authorization surface, attack trees for the highest-value targets (broker compromise, tuple forgery, approval spoofing/replay, RAG confused-deputy), each threat mapped to a mitigating control (or an accepted residual), and an honest residual-risk register for the non-production posture.
- **Expanded `docs/threat-model.md`** from the M2-only draft to the full model meeting those criteria — preserving the existing TCB statement and TTL-honesty table as inputs, not rewriting them.
- **Explicit attacker model**: capabilities and boundaries of each adversary class (malicious/compromised agent, malicious MCP client via DCR, network attacker on the compose network, malicious grant-linking user, curious insider), so every STRIDE entry is evaluated against a defined adversary.
- **Cross-references** into the `security-review` findings (control weaknesses become attack paths) and the SPEC-REVIEW decisions (F5/F7/F8 approval-and-notification threats, F1/Q3 tuple-writer trust, §11 confused-deputy trade-off).
- **No new runtime behavior and no production hardening**: threats the non-production posture accepts (no mTLS, dev secrets, single-node) are documented as accepted residuals, not fixed.

## Capabilities

### New Capabilities
- `threat-model`: The required contents and rigor of the Prokura threat model — assets, actors/attacker model, trust boundaries, STRIDE-per-flow coverage, attack trees for high-value targets, threat→mitigation mapping, and a residual-risk register. Acceptance criteria are stated so completeness is checkable, not subjective.

### Modified Capabilities
<!-- None. The threat model documents (does not change) the requirements owned by
     token-brokering, human-approval, per-agent-consent, identity-delegation,
     rag-authorization, and observability. If modeling exposes a genuine requirement
     gap, it is logged and handled as its own delta change, not pre-empted here. -->

## Impact

- **Docs**: rewrites/expands `docs/threat-model.md` from working draft to complete model.
- **Specs**: adds `openspec/specs/threat-model/` on archive.
- **Inputs consumed**: the `security-review` change's findings register (attack paths), the existing TTL table and TCB statement, SPEC.md §9 and §11, and SPEC-REVIEW.md F1–F9 / Q1–Q7.
- **No code changes.** Modeling only; any implied fix is a separate follow-up.
- **Sequencing**: authored now (planning); the modeling work (`apply`) runs after M6 and ideally after `security-review` so its findings feed the attack trees.
