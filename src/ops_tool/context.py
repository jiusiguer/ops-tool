from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .log import OpsLogger


@dataclass(slots=True)
class RuntimeContext:
    root: Path
    dry_run: bool
    assume_yes: bool
    verbose: bool
    logger: OpsLogger

    @property
    def backup_dir(self) -> Path:
        return self.root / "backups"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"
