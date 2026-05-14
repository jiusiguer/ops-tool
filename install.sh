#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${OPS_TOOL_REPO:-jiusiguer/ops-tool}"
REF="${OPS_TOOL_REF:-main}"
INSTALL_DIR="${OPS_TOOL_INSTALL_DIR:-$HOME/.local/share/ops-tool}"
BIN_DIR="${OPS_TOOL_BIN_DIR:-$HOME/.local/bin}"
RUN_AFTER_INSTALL="${OPS_TOOL_RUN_AFTER_INSTALL:-1}"

TMP_DIR=""

info() {
  printf 'info: %s\n' "$*"
}

warn() {
  printf 'warn: %s\n' "$*" >&2
}

err() {
  printf 'error: %s\n' "$*" >&2
}

cleanup() {
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Required command not found: $1"
    exit 1
  fi
}

run_as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    err "Root permission is required to install missing dependencies, and sudo was not found."
    exit 1
  fi
}

python3_is_compatible() {
  command -v python3 >/dev/null 2>&1 || return 1
  python3 - "$@" <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

install_python3() {
  warn "python3 was not found. Trying to install Python 3 automatically."
  if command -v apt-get >/dev/null 2>&1; then
    run_as_root apt-get update
    run_as_root apt-get install -y python3
  elif command -v dnf >/dev/null 2>&1; then
    run_as_root dnf install -y python3
  elif command -v yum >/dev/null 2>&1; then
    run_as_root yum install -y python3
  elif command -v apk >/dev/null 2>&1; then
    run_as_root apk add --no-cache python3
  elif command -v zypper >/dev/null 2>&1; then
    run_as_root zypper --non-interactive install python3
  elif command -v pacman >/dev/null 2>&1; then
    run_as_root pacman -Sy --noconfirm python
  else
    err "python3 was not found and no supported package manager was detected."
    exit 1
  fi
}

ensure_python3() {
  if ! command -v python3 >/dev/null 2>&1; then
    install_python3
  fi

  if ! python3_is_compatible; then
    err "Python 3.10 or newer is required. Current python3 is: $(python3 --version 2>&1 || true)"
    exit 1
  fi
}

download_archive() {
  local url="$1"
  local dest="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 -o "${dest}" "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${dest}" "${url}"
  else
    err "Neither curl nor wget found. Please install one and retry."
    exit 1
  fi
}

ensure_path_hint() {
  case ":${PATH}:" in
    *":${BIN_DIR}:"*)
      return 0
      ;;
  esac

  warn "${BIN_DIR} is not in PATH."
  printf '\nAdd this to your shell profile, for example ~/.bashrc:\n\n'
  printf '  export PATH="%s:$PATH"\n\n' "${BIN_DIR}"
  printf 'Then run:\n\n'
  printf '  source ~/.bashrc\n\n'
}

run_menu() {
  if [[ "${RUN_AFTER_INSTALL}" != "1" ]]; then
    return 0
  fi

  if [[ -r /dev/tty ]]; then
    info "Starting ops-tool..."
    "${INSTALL_DIR}/run.sh" </dev/tty >/dev/tty 2>/dev/tty
  else
    info "Installed. Run: ${BIN_DIR}/ops-tool"
  fi
}

main() {
  trap cleanup EXIT

  need_cmd bash
  need_cmd tar
  ensure_python3

  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ops-tool-install.XXXXXX")"
  local archive="${TMP_DIR}/ops-tool.tar.gz"
  local url="https://codeload.github.com/${REPO}/tar.gz/${REF}"

  info "Downloading ${REPO}@${REF}"
  download_archive "${url}" "${archive}"

  info "Extracting archive"
  tar -xzf "${archive}" -C "${TMP_DIR}"

  local src_dir
  src_dir="$(find "${TMP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [[ -z "${src_dir}" || ! -f "${src_dir}/run.sh" ]]; then
    err "Downloaded archive does not look like ops-tool."
    exit 1
  fi

  if [[ -d "${INSTALL_DIR}" ]]; then
    local backup="${INSTALL_DIR}.bak.$(date +%Y%m%d-%H%M%S)"
    info "Backing up existing install to ${backup}"
    mv "${INSTALL_DIR}" "${backup}"
  fi

  info "Installing to ${INSTALL_DIR}"
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  cp -a "${src_dir}" "${INSTALL_DIR}"
  chmod +x "${INSTALL_DIR}/run.sh"

  info "Creating command: ${BIN_DIR}/ops-tool"
  mkdir -p "${BIN_DIR}"
  ln -sfn "${INSTALL_DIR}/run.sh" "${BIN_DIR}/ops-tool"

  ensure_path_hint

  printf '\nInstalled successfully.\n\n'
  printf 'Run with:\n\n'
  printf '  %s/ops-tool\n\n' "${BIN_DIR}"
  printf 'Or directly:\n\n'
  printf '  %s/run.sh\n\n' "${INSTALL_DIR}"

  run_menu
}

main "$@"
