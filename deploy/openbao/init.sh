#!/bin/sh
# OpenBao dev-mode init — NON-PRODUCTION.
# Ensures KV v2 at secret/, a least-privilege broker policy, and a scoped
# broker token. The root token is used only here; services use the broker token.
set -eu

export BAO_ADDR="${BAO_ADDR:-http://openbao:8200}"
export BAO_TOKEN="${BAO_TOKEN:-prokura-dev-root}"

echo "openbao-init: waiting for ${BAO_ADDR}"
i=0
until bao status >/dev/null 2>&1 || [ $i -ge 30 ]; do
  i=$((i + 1)); sleep 1
done

# Dev mode mounts kv-v2 at secret/ already; enable only if missing.
if ! bao secrets list -format=table | grep -q '^secret/'; then
  bao secrets enable -path=secret kv-v2
fi

# Broker may manage grant credentials only.
bao policy write broker - <<'EOF'
path "secret/data/grants/*" {
  capabilities = ["create", "read", "update", "delete"]
}
path "secret/metadata/grants/*" {
  capabilities = ["list", "read", "delete"]
}
EOF

# Deterministic dev token for the broker (documented non-production).
bao token create -id="prokura-broker-dev-token" -policy=broker -orphan -ttl=768h >/dev/null 2>&1 || \
  echo "openbao-init: broker token already exists"

echo "openbao-init: done"
