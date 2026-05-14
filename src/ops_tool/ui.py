from __future__ import annotations

import getpass
import sys

from .context import RuntimeContext


def print_title(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def print_kv(key: str, value: object) -> None:
    print(f"{key:<18} {value}", flush=True)


def print_step(message: str) -> None:
    print(f"-> {message}", flush=True)


def print_warning(message: str) -> None:
    print(f"警告：{message}", file=sys.stderr, flush=True)


def print_error(message: str) -> None:
    print(f"错误：{message}", file=sys.stderr, flush=True)


def confirm(
    ctx: RuntimeContext,
    prompt: str,
    *,
    default: bool = False,
    require_text: str | None = None,
) -> bool:
    if ctx.dry_run:
        marker = f" [dry-run 已模拟输入 {require_text!r}]" if require_text else " [dry-run 已模拟确认]"
        print_step(prompt + marker)
        return True

    if require_text:
        print_warning(f"危险操作，需要输入 {require_text!r} 才会继续。")
        answer = input(f"{prompt}\n请输入确认文本：").strip()
        return answer == require_text

    if ctx.assume_yes:
        print_step(f"{prompt} [已通过 --yes 自动确认]")
        return True

    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "是", "好", "确认"}


def prompt_hidden(prompt: str) -> str:
    return getpass.getpass(prompt)
