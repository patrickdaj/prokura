"""Per-agent consent (per-agent-consent spec). The broker is the SOLE writer of
``can_use`` tuples and refuses any write where the agent's ``operator`` is not the
grant's ``owner``. The grant owner is definitionally the user in the grant object
id ``grant:{user}/{provider}``; the invariant lives here in code, per F1-A/Q3-B."""

import fga


class ConsentRefused(Exception):
    """operator != owner — a cross-user write attempt. 403 + logged."""


def grant_consent(agent: str, user: str, provider: str) -> None:
    """Authorize ``agent`` to use ``user``'s ``provider`` grant. Refuses unless the
    agent is operated by the grant owner."""
    operator = fga.agent_operator(agent)
    if operator != user:
        raise ConsentRefused(
            f"agent {agent!r} operated by {operator!r} != grant owner {user!r}"
        )
    fga.write_can_use(agent, user, provider)


def revoke_consent(agent: str, user: str, provider: str) -> None:
    fga.delete_can_use(agent, user, provider)


def is_allowed(agent: str, user: str, provider: str) -> bool:
    return fga.can_use(agent, user, provider)
