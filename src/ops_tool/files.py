from __future__ import annotations

import os
import re
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

SECRET_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|credential|authorization|auth)",
    re.IGNORECASE,
)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_private_file(path: Path) -> None:
    if path.exists():
        os.chmod(path, 0o600)


def backup_file(source: Path, backup_root: Path, label: str) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"文件不存在：{source}")
    dest_dir = backup_root / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{source.name}.{timestamp()}.bak"
    shutil.copy2(source, dest)
    os.chmod(dest, 0o600)
    return dest


def backup_directory(source: Path, backup_root: Path, label: str) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"目录不存在：{source}")
    dest_dir = backup_root / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{source.name}.{timestamp()}.tar.gz"
    with tarfile.open(dest, "w:gz") as archive:
        archive.add(source, arcname=source.name)
    os.chmod(dest, 0o600)
    return dest


def redact_text(text: str) -> str:
    redacted_lines: list[str] = []
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if SECRET_RE.search(key):
                redacted_lines.append(f"{key}= [已隐藏，原长度 {len(value.strip())}]")
                continue
        if SECRET_RE.search(line):
            redacted_lines.append("[该行疑似包含认证信息，已隐藏]")
            continue
        redacted_lines.append(line)
    return "\n".join(redacted_lines)


def mask_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): mask_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_json_value(item) for item in value]
    if isinstance(value, str):
        return f"[已隐藏字符串，长度 {len(value)}]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return f"[已隐藏 {type(value).__name__}]"
