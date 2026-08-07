# Design: add-observability

## Context

Every stack component already speaks telemetry natively — Keycloak 26 (OTel tracing + metrics), OpenFGA (OTLP export), OpenBao (telemetry stanza + audit device), FastAPI (OTel auto-instrumentation) — but nothing receives it. This change wires a receiver in before M1/M2 so the broker and approval service are born instrumented, and it upgrades the audit story from "persisted table" to "watchable live." The delegation-chain-as-a-trace is also a headline demo visual for a project whose product is explanation.

## Goals / Non-Goals

**Goals:**
- One-container LGTM receiver in compose; Grafana usable with zero manual setup.
- Native telemetry flags on Keycloak/OpenFGA/OpenBao; realm events on.
- Correlation convention (traceparent + domain IDs as span attributes) fixed now, inherited by M2/M3 services as definition-of-done.
- Smoke tests proving trace, log, and dashboard paths.

**Non-Goals:**
- No production observability posture (retention, sampling policy, alerting, HA) — dev-mode only, consistent with Q1.
- No custom instrumentation inside Keycloak/OpenFGA/OpenBao beyond their native switches.
- No log shipping for *host*-side test processes; only compose services are in scope.

## Decisions

1. **Single `grafana/otel-lgtm` container, pinned, not a hand-rolled Grafana+Tempo+Loki+Prometheus quartet.** It exposes one OTLP endpoint (gRPC 4317/HTTP 4318) and bundles pre-wired datasources; four separate services would quadruple compose surface for zero reference value. Trade-off: it's explicitly a dev image — which matches the stack's explicit non-production stance.
2. **Fire-and-forget telemetry.** No service gets a `depends_on` toward the receiver, and exporters are configured to drop on failure. The observability spec makes receiver-down non-fatal a scenario; the smoke suite keeps passing with the receiver stopped (except the telemetry tests themselves, which are the one place allowed to require it).
3. **Correlation convention:** W3C `traceparent` is the join key; domain IDs (audit correlation ID, approval reference ID) ride as span attributes (`prokura.correlation_id`, `prokura.approval_ref`) and appear as fields in structured log lines. Rationale: never invent a bespoke correlation scheme when trace context exists; domain IDs stay searchable by humans who have a ticket number, not a trace ID.
4. **Keycloak:** enable via env (tracing + metrics + OTLP endpoint pointed at the receiver) and set `eventsEnabled`/`adminEventsEnabled` in the realm export so identity events land in the event log. Exact flag names for 26.7 are an implementation-time verification item (Keycloak has churned these across 26.x minors) — task 1.1 pins them against the pinned image, not from memory.
5. **OpenFGA:** OTLP trace export + Prometheus metrics via env/flags (natively supported). FGA check spans are the per-check visibility; no per-check log line is added.
6. **OpenBao:** enable the **file audit device** in `init.sh` (satisfies "Bao access is audited"). Shipping that file into Loki requires a tailer; rather than adding an Alloy/Promtail sidecar in this change, the audit *file* is authoritative and Loki carries service stdout (docker logs) — the LGTM image ingests OTLP, and compose-level log shipping is listed as an open question with a cheap fallback (a ~10-line tailer sidecar) if the realtime-audit smoke test can't be satisfied from stdout alone.
7. **Dashboard as code:** `deploy/lgtm/` holds provisioning YAML + dashboard JSON, mounted into the container. The "delegation chain" dashboard v1 is honest about what exists pre-M2: login trace explorer, FGA check rate, Bao audit activity, realm events — and grows with M1/M2 traces.
8. **Test strategy:** telemetry assertions poll Tempo/Loki/Grafana APIs with a deadline (ingestion is async); they generate their own traffic (drive a login) rather than depending on residue from other tests.

## Risks / Trade-offs

- [LGTM container is heavy (~1 GB+ RAM)] → acceptable on a dev laptop; document it; profile-gating it (`--profile obs`) is the fallback if default-on proves annoying — decide at implementation based on measured startup cost.
- [Keycloak tracing flag names vary across 26.x] → pin against 26.7.1 during task 1.1; record the exact flags in this design when verified.
- [Async ingestion makes tests flaky] → bounded polling (same pattern as the Mailpit test), generous deadlines, tests generate their own traffic.
- [Bao audit file vs Loki gap] → audit device satisfies the audit scenario regardless; realtime-queryability scenario may need the tailer sidecar — scoped fallback, not unknown territory.
- [Dashboard rot as milestones add services] → dashboard JSON lives in-repo; each milestone change that adds a service updates it (noted in tasks as a convention, enforced by review).

## Migration Plan

Additive only; no rollback concerns. Sequence: receiver + flags → realm events → Bao audit → dashboard provisioning → smoke tests → README observability section. M1+ services adopt the correlation convention from birth.

## Open Questions

(None — all resolved; see below.)

## Resolved at implementation time

- **Realtime audit → Loki: OTLP logs, no tailer needed (open question 2).** Keycloak's `--telemetry-logs-enabled` (gated behind `--features=...,opentelemetry-logs`) pushes its log stream to Loki via OTLP, and `--spi-events-listener--jboss-logging--success-level=info` surfaces realm events (type, realm, client, userId, IP) in that stream — verified live: a LOGIN event was Loki-queryable seconds after the login. OpenBao's audit file remains its authoritative record; its realtime visibility arrives with M2's instrumented broker (caller-side spans + broker-emitted audit events).
- **Keycloak preview-feature pattern:** every `--telemetry-*` capability family is gated behind its own preview feature (`opentelemetry-metrics`, `opentelemetry-logs`); the flag alone makes the container refuse to start with "Disabled option." Hit twice; assume the same for future telemetry families.
- **Per-event metrics:** `--event-metrics-user-enabled=true` yields `keycloak_user_events_total{event, realm}` — the dashboard's logins/token-grants panels read this.
- **OpenBao has no trace export** (verified against OpenBao 2.6 docs: metrics sinks + audit device only) — spec's component-export requirement amended accordingly; Bao becomes trace-visible via caller-side spans in M2.
- **Receiver-outage semantics verified:** with `lgtm` stopped, the 8 core smoke tests pass and the 4 telemetry tests skip cleanly.
- **Dashboard provisioning:** provider yaml mounted at `provisioning/dashboards/prokura.yaml` pointing at `/otel-lgtm/prokura-dashboards` (bind-mounted `deploy/lgtm/dashboards/`); Grafana's file provider hot-loads JSON changes within ~10 s — dashboard iteration needs no container restart.

- **Keycloak 26.7 flags (verified against the image):** traces via `--tracing-enabled=true --tracing-endpoint=<otlp> --tracing-sampler-type=always_on`; OTLP metrics are a *separate* `--telemetry-metrics-*` family gated behind the preview feature `--features=opentelemetry-metrics` (Keycloak refuses to start without it — discovered live). `--metrics-enabled=true` additionally serves Prometheus metrics on the management port.
- **OpenFGA flags (verified via `run --help`):** `--trace-enabled --trace-otlp-endpoint=lgtm:4317 --trace-sampler=always_on --trace-sample-ratio=1`; Prometheus metrics on by default. Note: compose healthchecks generate a gRPC health-check trace every 3s with always_on sampling — dashboard/TraceQL queries must filter `name!~"grpc.health.*"`.
- **OpenBao audit is declarative in 2.6:** runtime `bao audit enable` returns 400 ("use declarative, config-based audit device management"); implemented as `deploy/openbao/audit.hcl` mounted with `-config=` appended to the dev-mode command — verified working (audit lines include full request path and token accessor). `init.sh` only verifies the device exists.
- **Receiver cost (measured):** Grafana ready in 47 s from container start; ~638 MiB RSS steady-state (Keycloak itself: ~704 MiB). **Decision: default-on**, no `obs` profile — the cost is a fraction of the stack and realtime visibility is a headline feature.
