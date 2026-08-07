#!/bin/sh
# Idempotently ensure the Prokura OpenFGA store exists and the authorization
# model is loaded. model.fga is the canonical (human) source; model.json is its
# HTTP-API form (the API takes JSON; keep both in sync).
set -eu

API="${FGA_API_URL:-http://openfga:8080}"
NAME="${FGA_STORE_NAME:-prokura}"

echo "openfga-init: waiting for ${API}"
i=0
until curl -sf "${API}/healthz" >/dev/null 2>&1 || [ $i -ge 30 ]; do
  i=$((i + 1)); sleep 1
done

# Find existing store by name
STORE_ID=$(curl -sf "${API}/stores" | sed -n 's/.*"id":"\([^"]*\)","name":"'"${NAME}"'".*/\1/p' | head -1)

if [ -z "${STORE_ID}" ]; then
  echo "openfga-init: creating store '${NAME}'"
  STORE_ID=$(curl -sf -X POST "${API}/stores" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"${NAME}\"}" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
else
  echo "openfga-init: store '${NAME}' exists (${STORE_ID})"
fi

echo "openfga-init: writing authorization model to store ${STORE_ID}"
curl -sf -X POST "${API}/stores/${STORE_ID}/authorization-models" \
  -H 'Content-Type: application/json' \
  --data-binary @/deploy/model.json >/dev/null

echo "openfga-init: done (store ${STORE_ID})"
