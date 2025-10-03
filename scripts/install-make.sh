#!/usr/bin/env bash
# install-make.sh — Install GNU Make on Ubuntu/Debian
# Usage:
#   chmod +x install-make.sh
#   ./install-make.sh

set -euo pipefail

# If make already exists, exit early
if command -v make >/dev/null 2>&1; then
  echo "make is already installed: $(make --version | head -n1)"
  exit 0
fi

# Ensure we're on a Debian/Ubuntu-like system
if ! command -v apt-get >/dev/null 2>&1; then
  echo "This script requires apt-get (Ubuntu/Debian). Exiting." >&2
  exit 1
fi

# Use sudo when not running as root
SUDO=""
if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "Please run this script as root or install sudo first." >&2
    exit 1
  fi
fi

export DEBIAN_FRONTEND=noninteractive

# Update package index and install
$SUDO apt-get update
# Try the 'make' meta package first; fall back to 'make-guile' if needed
if ! $SUDO apt-get install -y make; then
  $SUDO apt-get install -y make-guile
fi

echo "✅ Installed: $(make --version | head -n1)"

# Quick sanity check + hint
if make -v >/dev/null 2>&1; then
  echo
  echo "You can now run: make help"
fi
