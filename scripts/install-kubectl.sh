#!/usr/bin/env bash
set -Eeuo pipefail

# ---------- Config (override via env) ----------
BIN_DIR="${BIN_DIR:-/usr/local/bin}"   # where kubectl will be installed
VERSION="${VERSION:-stable}"           # "stable" or "v1.x.y"
USE_BREW="${USE_BREW:-auto}"           # auto|true|false (macOS only)
USE_APT="${USE_APT:-false}"            # Debian/Ubuntu optional (defaults to binary method)

# ---------- Helpers ----------
log()  { printf "\033[1;32m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

detect_os_arch() {
  OS_UNAME="$(uname -s)"
  case "$OS_UNAME" in
    Linux)  OS="linux" ;;
    Darwin) OS="darwin" ;;
    *) err "Unsupported OS: $OS_UNAME"; exit 1 ;;
  esac

  ARCH_UNAME="$(uname -m)"
  case "$ARCH_UNAME" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) err "Unsupported arch: $ARCH_UNAME"; exit 1 ;;
  esac

  log "Detected OS=$OS, ARCH=$ARCH"
}

resolve_version() {
  if [[ "$VERSION" == "stable" ]]; then
    VERSION="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
  fi
  if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    err "Invalid VERSION '$VERSION' (expected 'stable' or 'vX.Y.Z')"; exit 1
  fi
  log "Resolved kubectl version: $VERSION"
}

install_with_brew() {
  log "Installing kubectl via Homebrew"
  brew update
  brew install kubectl || brew upgrade kubectl || true
  command -v kubectl >/dev/null || { warn "Brew install failed, falling back to binary."; return 1; }
  return 0
}

install_with_apt() {
  # Minimal: use distro kubectl if available. (Official apt repo setup is more involved; binary method is simpler.)
  if ! have sudo || ! have apt-get; then return 1; fi
  log "Attempting apt-based install of kubectl (may not be latest)"
  sudo apt-get update -y || true
  # Try common packages; if not present, this will fail and we’ll fall back
  sudo apt-get install -y kubectl && return 0 || return 1
}

install_from_binary() {
  local url tmp
  url="https://dl.k8s.io/release/${VERSION}/bin/${OS}/${ARCH}/kubectl"
  tmp="$(mktemp -t kubectl.XXXXXX)"

  log "Downloading ${url}"
  curl -fsSL -o "${tmp}" "${url}"

  chmod +x "${tmp}"
  if have sudo; then
    sudo install "${tmp}" "${BIN_DIR}/kubectl"
  else
    install "${tmp}" "${BIN_DIR}/kubectl"
  fi
  rm -f "${tmp}"
}

verify_install() {
  if ! command -v kubectl >/dev/null 2>&1; then
    err "kubectl not found on PATH after installation"; exit 1
  fi
  log "kubectl installed at: $(command -v kubectl)"
  kubectl version --client --output=yaml || kubectl version --client || true
}

main() {
  detect_os_arch
  resolve_version

  if [[ "$OS" == "darwin" ]]; then
    case "$USE_BREW" in
      auto) if have brew; then install_with_brew || install_from_binary; else install_from_binary; fi ;;
      true) install_with_brew || install_from_binary ;;
      *)    install_from_binary ;;
    esac
  else
    # Linux
    if [[ "$USE_APT" == "true" ]]; then
      install_with_apt || install_from_binary
    else
      install_from_binary
    fi
  fi

  verify_install
  log "Done. Tip: enable shell completion with 'kubectl completion bash|zsh'."
}

main "$@"
