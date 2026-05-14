from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Iterable


class OpsLogger:
    def __init__(self, log_dir: Path, *, verbose: bool = False) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.path = log_dir / f"{stamp}-{os.getpid()}.log"
        self.verbose = verbose
        self.path.touch(mode=0o600, exist_ok=False)

    def write(self, level: str, message: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now}] [{level.upper()}] {message}\n")

    def info(self, message: str) -> None:
        self.write("info", message)

    def warning(self, message: str) -> None:
        self.write("warning", message)

    def error(self, message: str) -> None:
        self.write("error", message)

    def command(self, command: Iterable[str], returncode: int | None = None) -> None:
        suffix = "" if returncode is None else f" -> rc={returncode}"
        self.write("command", " ".join(command) + suffix)
