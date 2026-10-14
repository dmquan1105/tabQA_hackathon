#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3.12 >/dev/null 2>&1; then
  python_bin="python3.12"
else
  python_bin="python3"
fi

exec "$python_bin" "$script_dir/run_all.py" "$@"
