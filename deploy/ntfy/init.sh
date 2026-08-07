#!/bin/sh
# Provision the approval service's ntfy publisher on the deny-all server (F7):
# a single user allowed to read+write only the per-user approval topics.
# Idempotent enough for dev (tolerates an already-provisioned user).
set -e

export NTFY_PASSWORD="${NTFY_APPROVAL_PASSWORD:-prokura-approval-dev}"
ntfy user add prokura-approval 2>/dev/null || echo "ntfy user prokura-approval already exists"
ntfy access prokura-approval 'prokura-approvals-*' rw
echo "ntfy: prokura-approval provisioned with rw on prokura-approvals-*"
