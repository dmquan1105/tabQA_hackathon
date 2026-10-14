from __future__ import annotations

import subprocess
import sys
from pathlib import Path


if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required to run the judge.")

repo_root = Path(__file__).resolve().parents[1]
config_dir = repo_root / "organizer-config"

command = [
    sys.executable,
    "-m",
    "judge",
    "run-all",
    "--judge-config",
    str(config_dir / "judge.toml"),
    "--runtime-config",
    str(config_dir / "run-config.local.toml"),
    *sys.argv[1:],
]

raise SystemExit(subprocess.call(command, cwd=repo_root))
