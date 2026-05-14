#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  SOURCE_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  if [[ "$SOURCE" != /* ]]; then
    SOURCE="$SOURCE_DIR/$SOURCE"
  fi
done

ROOT="$(cd -P "$(dirname "$SOURCE")" && pwd)"

run_as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "错误：未找到 python3，且当前用户无法通过 sudo 自动安装。" >&2
    exit 1
  fi
}

install_python3() {
  echo "警告：未找到 python3，正在尝试自动安装 Python 3。" >&2
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
    echo "错误：未找到 python3，也没有检测到支持的包管理器。" >&2
    exit 1
  fi
}

python_is_compatible() {
  "$1" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

if [[ -x "$ROOT/.venv/bin/python" ]] && python_is_compatible "$ROOT/.venv/bin/python"; then
  PYTHON="$ROOT/.venv/bin/python"
else
  if ! command -v python3 >/dev/null 2>&1; then
    install_python3
  fi
  PYTHON="python3"
fi

if ! python_is_compatible "$PYTHON"; then
  echo "错误：ops-tool 需要 Python 3.10 或更新版本，当前版本是：$($PYTHON --version 2>&1 || true)" >&2
  exit 1
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m ops_tool.cli "$@"
