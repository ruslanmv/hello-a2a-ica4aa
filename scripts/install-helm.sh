#!/usr/bin/env bash
# install-helm.sh — Installs/updates Helm v3 on Ubuntu/WSL
# Usage: bash install-helm.sh

set -euo pipefail

NEED_MAJOR=3

log()    { printf "\033[1;34m[INFO]\033[0m %s\n" "$*"; }
ok()     { printf "\033[1;32m[SUCCESS]\033[0m %s\n" "$*"; }
warn()   { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()    { printf "\033[1;31m[ERROR]\033[0m %s\n" "$*" >&2; }
divider(){ printf "%s\n" "----------------------------------------"; }

SUDO=""
if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  SUDO="sudo"
fi

helm_ok() {
  if ! command -v helm >/dev/null 2>&1; then
    return 1
  fi
  local ver major
  ver=$(helm version --short 2>/dev/null | sed -E 's/^v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/')
  major="${ver%%.*}"
  if [ -z "$major" ]; then
    return 1
  fi
  if [ "$major" -ge "$NEED_MAJOR" ]; then
    return 0
  fi
  return 1
}

install_via_apt() {
  log "Attempting install via APT (official Helm repo)..."
  $SUDO apt-get update -y
  $SUDO apt-get install -y --no-install-recommends apt-transport-https ca-certificates curl gnupg
  # Use keyring (apt-key is deprecated)
  if [ ! -f /usr/share/keyrings/helm.gpg ]; then
    curl -fsSL https://baltocdn.com/helm/signing.asc | gpg --dearmor | $SUDO tee /usr/share/keyrings/helm.gpg >/dev/null
  fi
  echo "deb [signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" \
    | $SUDO tee /etc/apt/sources.list.d/helm-stable-debian.list >/dev/null

  $SUDO apt-get update -y
  $SUDO apt-get install -y helm
}

install_via_snap() {
  if ! command -v snap >/dev/null 2>&1; then
    warn "snap not available; skipping snap method."
    return 1
  fi
  # On WSL, snap often isn't available unless systemd is enabled.
  if grep -qi microsoft /proc/version 2>/dev/null; then
    warn "Detected WSL; snap may not work unless systemd is enabled. Trying anyway..."
  fi
  log "Attempting install via snap..."
  $SUDO snap install helm --classic
}

install_via_get_script() {
  log "Attempting install via official get-helm-3 script..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 -o "$tmp/get_helm.sh"
  chmod 700 "$tmp/get_helm.sh"
  # Encourage script to use sudo when needed
  USE_SUDO=1 bash "$tmp/get_helm.sh"
}

print_helm() {
  divider
  command -v helm >/dev/null 2>&1 && log "helm binary: $(command -v helm)"
  helm version || true
  divider
}

main() {
  log "Installing Helm (v${NEED_MAJOR}+ required)..."
  if helm_ok; then
    ok "Helm already installed and up-to-date."
    print_helm
    exit 0
  fi

  # Try APT
  if install_via_apt && helm_ok; then
    ok "Helm installed via APT."
    print_helm
    exit 0
  fi
  warn "APT method failed or produced an invalid Helm."

  # Try snap
  if install_via_snap && helm_ok; then
    ok "Helm installed via snap."
    print_helm
    exit 0
  fi
  warn "snap method failed or produced an invalid Helm."

  # Try upstream script
  if install_via_get_script && helm_ok; then
    ok "Helm installed via official script."
    print_helm
    exit 0
  fi

  err "All install methods failed. Please check network/proxy and try again."
  exit 1
}

main "$@"
