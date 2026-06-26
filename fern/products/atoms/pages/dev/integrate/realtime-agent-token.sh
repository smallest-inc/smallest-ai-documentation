#!/usr/bin/env bash
# Fetch a short-lived access token for the Realtime Agent WebSocket.
#
# Usage:
#   export ATOMS_API_KEY="sk_..."
#   export ATOMS_AGENT_ID="..."
#   ./realtime-agent-token.sh                  # prints the wct_ token
#   ./realtime-agent-token.sh --json           # prints the full response
#   ./realtime-agent-token.sh --mode chat      # request chat (text-only) mode
#
# Token is single-use and expires in 30 seconds. Open the WebSocket
# immediately after this returns.

set -euo pipefail

: "${ATOMS_API_KEY:?ATOMS_API_KEY must be set}"
: "${ATOMS_AGENT_ID:?ATOMS_AGENT_ID must be set}"

mode="webcall"
json_out=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) mode="$2"; shift 2 ;;
    --json) json_out=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

resp=$(curl -fsS -X POST \
  https://api.smallest.ai/atoms/v1/conversation/register-call \
  -H "Authorization: Bearer ${ATOMS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"${ATOMS_AGENT_ID}\",\"mode\":\"${mode}\"}")

if [[ $json_out -eq 1 ]]; then
  echo "$resp"
else
  echo "$resp" | python3 -c 'import sys, json; print(json.load(sys.stdin)["data"]["access_token"])'
fi
