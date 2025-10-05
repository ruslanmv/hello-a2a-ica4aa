#!/usr/bin/env bash
set -Eeuo pipefail

# --- Simple ICA4AA/A2A server verifier ---------------------------------------
# Usage:
#   ./verify-a2a-ica4aa.sh <ip-or-base-url> [port]
# Examples:
#   ./verify-a2a-ica4aa.sh 13.48.133.166
#   ./verify-a2a-ica4aa.sh 13.48.133.166 8080
#   ./verify-a2a-ica4aa.sh http://13.48.133.166:8080
#
# Exits 0 if all mandatory checks pass, non-zero otherwise.

# --- Pretty output ------------------------------------------------------------
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[PASS]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

# --- Args -> BASE URL ---------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <ip-or-base-url> [port]" >&2
  exit 2
fi

INPUT="$1"
PORT="${2:-8080}"

if [[ "$INPUT" == http://* || "$INPUT" == https://* ]]; then
  BASE="${INPUT%/}"
else
  BASE="http://$INPUT:$PORT"
fi

# --- Ensure jq ----------------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  info "jq not found. Attempting to install (Ubuntu/Debian)..."
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y jq >/dev/null 2>&1 || {
      fail "Could not install jq. Please install jq and re-run."
      exit 3
    }
  else
    fail "jq is required. Install jq and re-run."
    exit 3
  fi
fi

# --- Curl helper --------------------------------------------------------------
CURL_OPTS=( -sS --fail --connect-timeout 5 --max-time 20 )
tmpdir="$(mktemp -d)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

http_get()  { curl "${CURL_OPTS[@]}" -w "%{http_code}" -o "$2" "$1"; }
http_post() { curl "${CURL_OPTS[@]}" -w "%{http_code}" -o "$3" -H 'content-type: application/json' -d "$2" "$1"; }

MANDATORY_FAILS=0
OPTIONAL_FAILS=0

# --- 1) Health & readiness ----------------------------------------------------
for path in /healthz /readyz; do
  out="$tmpdir${path//\//_}.json"
  code="$(http_get "$BASE$path" "$out" || true)"
  if [[ "$code" == "200" ]] && jq -e 'type=="object"' "$out" >/dev/null 2>&1; then
    ok "$path ok"
  else
    fail "$path returned $code"
    (( MANDATORY_FAILS++ )) || true
  fi
done

# --- 2) OpenAPI (sanity) ------------------------------------------------------
out="$tmpdir/openapi.json"
code="$(http_get "$BASE/openapi.json" "$out" || true)"
if [[ "$code" == "200" ]] && jq -e '.info and .paths' "$out" >/dev/null 2>&1; then
  ok "/openapi.json ok"
else
  warn "/openapi.json returned $code (not mandatory but useful)"
  (( OPTIONAL_FAILS++ )) || true
fi

# --- 3) Agent Card (optional) -------------------------------------------------
out="$tmpdir/agent_card.json"
code="$(http_get "$BASE/.well-known/agent-card.json" "$out" || true)"
if [[ "$code" == "200" ]]; then
  ok "/.well-known/agent-card.json ok"
else
  warn "agent-card not found ($code) – optional"
fi

# --- 4) Manifest (mandatory ICA4AA shape) ------------------------------------
out="$tmpdir/manifest.json"
code="$(http_get "$BASE/a2a/manifest" "$out" || true)"
if [[ "$code" == "200" ]] && jq -e '
  .apiVersion and .kind and .metadata and .spec and
  .spec.endpoints.invoke and .spec.inputSchema and .spec.outputSchema
' "$out" >/dev/null 2>&1; then
  ok "/a2a/manifest shape ok"
else
  fail "/a2a/manifest invalid or $code"
  (( MANDATORY_FAILS++ )) || true
fi

# Extract agent_id if possible
AGENT_ID="$(jq -r '.metadata.id // empty' "$out" 2>/dev/null || true)"
if [[ -z "${AGENT_ID:-}" ]]; then
  warn "Could not read agent id from manifest; will try directory endpoints."
fi

# --- 5) Directory (server list) ----------------------------------------------
out="$tmpdir/dir.json"
code="$(http_get "$BASE/a2a/agents" "$out" || true)"
if [[ "$code" == "200" ]] && jq -e '.agents|type=="array" and (length>=1)' "$out" >/dev/null 2>&1; then
  ok "/a2a/agents ok"
  if [[ -z "${AGENT_ID:-}" ]]; then
    AGENT_ID="$(jq -r '.agents[0].id // empty' "$out" 2>/dev/null || true)"
  fi
else
  fail "/a2a/agents invalid or $code"
  (( MANDATORY_FAILS++ )) || true
fi

# --- 6) Well-known directories (at least one should work) --------------------
have_well_known=0
for path in "/.well-known/ica4aa/agents" "/api/v1/agents"; do
  out="$tmpdir${path//\//_}.json"
  code="$(http_get "$BASE$path" "$out" || true)"
  if [[ "$code" == "200" ]] && jq -e '
      (type=="object") and (.agents|type=="array") and (length>=1)
    ' "$out" >/dev/null 2>&1; then
    ok "$path ok"
    have_well_known=1
    if [[ -z "${AGENT_ID:-}" ]]; then
      AGENT_ID="$(jq -r '.agents[0].id // empty' "$out" 2>/dev/null || true)"
    fi
  else
    warn "$path invalid or $code"
  fi
done
if [[ $have_well_known -eq 0 ]]; then
  fail "No well-known directory endpoint responded correctly"
  (( MANDATORY_FAILS++ )) || true
fi

# --- 7) Ensure we have an agent id -------------------------------------------
if [[ -z "${AGENT_ID:-}" ]]; then
  fail "Could not determine agent id from manifest or directory endpoints"
  (( MANDATORY_FAILS++ )) || true
else
  info "Using AGENT_ID=${AGENT_ID}"
fi

# --- 8) Invoke wrapper (mandatory) -------------------------------------------
if [[ -n "${AGENT_ID:-}" ]]; then
  out="$tmpdir/invoke.json"
  body='{"name":"ICA4AA Test"}'
  code="$(http_post "$BASE/api/v1/agents/$AGENT_ID/invoke" "$body" "$out" || true)"
  if [[ "$code" == "200" ]] && jq -e '.message | type=="string"' "$out" >/dev/null 2>&1; then
    ok "POST /api/v1/agents/$AGENT_ID/invoke ok"
  else
    fail "POST /api/v1/agents/$AGENT_ID/invoke failed ($code)"
    (( MANDATORY_FAILS++ )) || true
  fi
fi

# --- 9) Canonical A2A pipeline (mandatory) -----------------------------------
out="$tmpdir/a2a_send.json"
body='{
  "method":"message/send",
  "params":{"message":{"role":"user","messageId":"verify","parts":[{"type":"text","text":"Ping from verifier"}]}}
}'
code="$(http_post "$BASE/a2a" "$body" "$out" || true)"
if [[ "$code" == "200" ]] && jq -e '.result.message.parts[0].text | type=="string"' "$out" >/dev/null 2>&1; then
  ok "POST /a2a (message/send) ok"
else
  fail "POST /a2a (message/send) failed ($code)"
  (( MANDATORY_FAILS++ )) || true
fi

# --- 10) Optional demo action -------------------------------------------------
out="$tmpdir/say_hello.json"
body='{"name":"ICA4AA"}'
code="$(http_post "$BASE/a2a/actions/say_hello" "$body" "$out" || true)"
if [[ "$code" == "200" ]] && jq -e '.message | type=="string"' "$out" >/dev/null 2>&1; then
  ok "POST /a2a/actions/say_hello ok (optional)"
else
  warn "POST /a2a/actions/say_hello not available ($code) – optional"
fi

# --- Summary -----------------------------------------------------------------
echo
if [[ $MANDATORY_FAILS -eq 0 ]]; then
  ok  "All mandatory ICA4AA compatibility checks PASSED for $BASE"
  if [[ $OPTIONAL_FAILS -gt 0 ]]; then
    warn "$OPTIONAL_FAILS optional items did not pass (not blocking)."
  fi
  exit 0
else
  fail "$MANDATORY_FAILS mandatory checks FAILED for $BASE"
  echo "Troubleshooting tips:"
  echo "  • Ensure PUBLIC_URL (or reverse proxy) makes the service reachable externally."
  echo "  • /a2a/manifest must include spec.endpoints.invoke and inputSchema/outputSchema."
  echo "  • /a2a/agents and one well-known directory must return an agents[] array."
  echo "  • /api/v1/agents/{id}/invoke must return {\"message\":\"...\"}."
  echo "  • /a2a message/send must return result.message.parts[0].text."
  exit 1
fi
