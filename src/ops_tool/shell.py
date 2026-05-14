from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .context import RuntimeContext
from .ui import print_step


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"未找到命令：{name}")
    return path


def run_command(
    ctx: RuntimeContext,
    command: list[str],
    *,
    check: bool = False,
    sudo: bool = False,
    timeout: int | None = None,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    capture: bool = True,
    dry_run_execute: bool = False,
    input_text: str | None = None,
) -> CommandResult:
    final_command = ["sudo", *command] if sudo else command
    ctx.logger.command(final_command)

    if ctx.dry_run and not dry_run_execute:
        print_step("[dry-run] " + " ".join(final_command))
        return CommandResult(final_command, 0, "", "")

    sys.stdout.flush()
    sys.stderr.flush()

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    stdout_pipe = subprocess.PIPE if capture else None
    stderr_pipe = subprocess.PIPE if capture else None
    proc = subprocess.run(
        final_command,
        text=True,
        input=input_text,
        stdout=stdout_pipe,
        stderr=stderr_pipe,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        check=False,
    )
    result = CommandResult(
        command=final_command,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
    ctx.logger.command(final_command, proc.returncode)
    if result.stdout and ctx.verbose:
        ctx.logger.info("stdout:\n" + result.stdout.rstrip())
    if result.stderr:
        ctx.logger.warning("stderr:\n" + result.stderr.rstrip())

    if check and proc.returncode != 0:
        raise RuntimeError(
            "命令执行失败："
            + " ".join(final_command)
            + f"\n返回码：{proc.returncode}\n"
            + (result.stderr.strip() or result.stdout.strip())
        )

    return result
