# ADR-0006: Keycloak's built-in CIBA HTTP channel — no custom Java SPI

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F6; `spike/ciba-http-channel/`; `docker-compose.yml` (keycloak CIBA flag)

## Context

M3 (the riskiest milestone) budgeted a custom Keycloak `AuthenticationChannelProvider` SPI in Java — a Java toolchain + SPI-churn burden on a mostly-Python project.

## Decision

Use Keycloak's **built-in HTTP authentication channel** (`--spi-ciba-auth-channel--ciba-http-auth-channel--http-authentication-channel-uri`) pointed at the FastAPI approval service; the decision returns on Keycloak's standard CIBA callback. Spiked in M0 to de-risk before M3. The Java SPI is deleted from the plan.

## Alternatives considered

- B — keep the Java SPI: full control, upstream-contribution potential, real maintenance drag.
- C — skip Keycloak CIBA, approve in the broker: abandons the CIBA standards story that justifies Keycloak.

## Consequences

M3 shrank to Python + configuration. Fallback was B if the built-in channel proved unusable (it didn't).

