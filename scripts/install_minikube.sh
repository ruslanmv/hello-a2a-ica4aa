#!/usr/bin/env bash
set -Eeuo pipefail

### Config (override via env vars if you like)
CPUS="${CPUS:-6}"
MEMORY_MB="${MEMORY_MB:-10240}"
DISK_SIZE="${DISK_SIZE:-60g}"
DRIVER="${DRIVER:-docker}"        # docker recommended on laptops/WSL
INSTALL_DOCKER_ON_LINUX="${INSTALL_DOCKER_ON_LINUX:-true}"

### Helpers
log()  { printf "\033[1;32m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

trap 'err "Something went wrong. Check the messages above."' ERR

detect_os_arch() {
  OS="$(uname -s)"
  ARCH_RAW="$(uname -m)"
  case "$ARCH_RAW" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) err "Unsupported CPU arch: $ARCH_RAW"; exit 1 ;;
  esac
  log "Detected OS=$OS, ARCH=$ARCH"
}

install_minikube_linux() {
  # Prefer .deb on Debian/Ubuntu; else fallback to static binary
  if have dpkg && have sudo; then
    log "Installing minikube (.deb) for $ARCH"
    URL="https://storage.googleapis.com/minikube/releases/latest/minikube_latest_${ARCH}.deb"
    curl -fsSL -o "/tmp/minikube_latest_${ARCH}.deb" "$URL"
    sudo dpkg -i "/tmp/minikube_latest_${ARCH}.deb" || {
      warn "dpkg reported missing deps — attempting apt fix"
      if have apt-get; then
        sudo apt-get -y -f install
      fi
    }
  else
    log "dpkg/apt not available — using static binary"
    URL="https://storage.googleapis.com/minikube/releases/latest/minikube-linux-${ARCH}"
    curl -fsSL -o "/tmp/minikube-linux-${ARCH}" "$URL"
    chmod +x "/tmp/minikube-linux-${ARCH}"
    sudo install "/tmp/minikube-linux-${ARCH}" /usr/local/bin/minikube
  fi

  if ! have minikube; then
    err "minikube did not install correctly on Linux."; exit 1
  fi
}

install_minikube_macos() {
  # Use Homebrew if available; otherwise install the official binary
  if have brew; then
    log "Installing minikube via Homebrew"
    brew update
    brew install minikube || brew upgrade minikube || true
  else
    log "Homebrew not found — installing minikube via official binary"
    URL="https://storage.googleapis.com/minikube/releases/latest/minikube-darwin-${ARCH}"
    curl -fsSL -o "/tmp/minikube-darwin-${ARCH}" "$URL"
    chmod +x "/tmp/minikube-darwin-${ARCH}"
    # Prefer /usr/local/bin (works on both Intel and Apple Silicon if writable)
    if [ -w /usr/local/bin ]; then
      sudo install "/tmp/minikube-darwin-${ARCH}" /usr/local/bin/minikube
    else
      # Fallback to /usr/local/bin with sudo or /opt/homebrew/bin if exists
      if have sudo; then
        sudo install "/tmp/minikube-darwin-${ARCH}" /usr/local/bin/minikube
      elif [ -d /opt/homebrew/bin ] && [ -w /opt/homebrew/bin ]; then
        install "/tmp/minikube-darwin-${ARCH}" /opt/homebrew/bin/minikube
      else
        err "No writable bin dir found (try installing Homebrew: https://brew.sh)"; exit 1
      fi
    fi
  fi

  if ! have minikube; then
    err "minikube did not install correctly on macOS."; exit 1
  fi
}

maybe_install_docker_linux() {
  if [ "${INSTALL_DOCKER_ON_LINUX}" != "true" ]; then
    warn "Skipping Docker install on Linux (INSTALL_DOCKER_ON_LINUX=false)"
    return 0
  fi

  if have docker; then
    log "Docker is already installed"
  else
    if have apt-get && have sudo; then
      log "Installing Docker (docker.io) from Ubuntu repos"
      sudo apt-get update -y
      sudo apt-get install -y docker.io
      sudo systemctl enable --now docker || true
    else
      warn "apt-get not available; please install Docker manually for best minikube experience."
    fi
  fi

  if have docker; then
    # add current user to docker group to avoid root-requiring driver
    if getent group docker >/dev/null 2>&1; then
      if id -nG "$USER" | grep -qw docker; then
        log "User '$USER' already in docker group"
      else
        if have sudo; then
          log "Adding '$USER' to docker group"
          sudo usermod -aG docker "$USER" || true
          warn "You may need to log out/in (or run 'newgrp docker') for group changes to take effect."
        else
          warn "Cannot add user to docker group without sudo."
        fi
      fi
    fi
  fi
}

repair_kubeconfig_and_cleanup() {
  log "Ensuring ~/.kube/config is a file (not a directory)"
  ts=$(date +%F-%H%M%S)
  if [ -d "$HOME/.kube/config" ]; then
    mv "$HOME/.kube/config" "$HOME/.kube/config.dir-backup-$ts"
  fi
  mkdir -p "$HOME/.kube"
  : > "$HOME/.kube/config"

  chmod 700 "$HOME/.kube"
  chmod 600 "$HOME/.kube/config"
  if have sudo; then
    sudo chown -R "$USER":"$USER" "$HOME/.kube" "$HOME/.minikube" 2>/dev/null || true
  fi

  # Clean any half-created cluster (safe if none exists)
  if have minikube; then
    log "Deleting any existing minikube profile to start fresh"
    minikube delete || true
  fi
}

start_minikube() {
  log "Starting minikube: --cpus=${CPUS} --memory=${MEMORY_MB} --disk-size=${DISK_SIZE} --driver=${DRIVER}"
  minikube start --cpus="${CPUS}" --memory="${MEMORY_MB}" --disk-size="${DISK_SIZE}" --driver="${DRIVER}"

  log "Verifying cluster"
  minikube status || true
  if ! have kubectl; then
    warn "kubectl not found. You can use: 'minikube kubectl -- get pods -A'"
  else
    kubectl get nodes || true
  fi
}

main() {
  detect_os_arch

  case "$OS" in
    Linux)
      install_minikube_linux
      maybe_install_docker_linux
      ;;
    Darwin)
      install_minikube_macos
      ;;
    *)
      err "Unsupported OS: $OS"; exit 1
      ;;
  esac

  repair_kubeconfig_and_cleanup
  start_minikube

  log "Done! kubectl (or 'minikube kubectl --') is now configured for the 'minikube' context."
}

main "$@"
