from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SystemInfo:
    os_id: str
    os_name: str
    version_id: str
    arch: str
    package_manager: str
    init_system: str


def normalize_arch(machine: str | None = None) -> str:
    raw = (machine or platform.machine()).lower()
    aliases = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    if raw in aliases:
        return aliases[raw]
    if raw.startswith("armv7") or raw.startswith("armv6"):
        return "arm"
    return raw or "unknown"


def read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def detect_package_manager() -> str:
    for candidate in ("apt-get", "dnf", "yum", "pacman", "zypper", "apk"):
        if shutil.which(candidate):
            return candidate
    return "unknown"


def detect_init_system() -> str:
    if shutil.which("systemctl"):
        try:
            proc = subprocess.run(
                ["systemctl", "--version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.startswith("systemd"):
                return "systemd"
        except (OSError, subprocess.SubprocessError):
            pass
    if Path("/sbin/openrc").exists():
        return "openrc"
    return "unknown"


def collect_system_info() -> SystemInfo:
    os_release = read_os_release()
    return SystemInfo(
        os_id=os_release.get("ID", "unknown"),
        os_name=os_release.get("PRETTY_NAME", os_release.get("NAME", "unknown")),
        version_id=os_release.get("VERSION_ID", "unknown"),
        arch=normalize_arch(),
        package_manager=detect_package_manager(),
        init_system=detect_init_system(),
    )
