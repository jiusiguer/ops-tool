from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import tomllib
from pathlib import Path

from ..context import RuntimeContext
from ..detect import collect_system_info
from ..files import (
    backup_directory,
    backup_file,
    ensure_private_file,
    mask_json_value,
    redact_text,
)
from ..shell import CommandResult, require_command, run_command
from ..ui import confirm, print_error, print_kv, print_step, print_title, print_warning

CODEX_NPM_PACKAGE = "@openai/codex"
SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9_*.-]+")


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def config_path() -> Path:
    return codex_home() / "config.toml"


def auth_path() -> Path:
    return codex_home() / "auth.json"


def _codex_bin() -> str | None:
    return shutil.which("codex")


def _npm_bin() -> str | None:
    return shutil.which("npm")


def _first_line(result: CommandResult) -> str:
    return (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else ""


def query_latest_version(ctx: RuntimeContext) -> str:
    npm = _npm_bin()
    if not npm:
        return "无法查询：未找到 npm"
    result = run_command(
        ctx,
        [npm, "view", CODEX_NPM_PACKAGE, "version"],
        timeout=30,
        capture=True,
        dry_run_execute=True,
    )
    if result.ok:
        return result.stdout.strip() or "unknown"
    return "查询失败：" + (result.stderr.strip() or result.stdout.strip() or f"rc={result.returncode}")


def current_version(ctx: RuntimeContext) -> str:
    codex = _codex_bin()
    if not codex:
        return "未安装或不在 PATH 中"
    result = run_command(ctx, [codex, "--version"], timeout=10, capture=True, dry_run_execute=True)
    if result.ok:
        return _first_line(result) or "unknown"
    return "检测失败：" + (result.stderr.strip() or result.stdout.strip())


def login_status(ctx: RuntimeContext) -> str:
    codex = _codex_bin()
    if not codex:
        return "无法检测：未找到 codex"
    result = run_command(ctx, [codex, "login", "status"], timeout=15, capture=True, dry_run_execute=True)
    text = (result.stdout or result.stderr).strip()
    if result.ok:
        return redact_login_status(text) or "已登录状态未知：命令无输出"
    return redact_login_status(text) or f"检测失败：rc={result.returncode}"


def redact_login_status(text: str) -> str:
    return OPENAI_KEY_RE.sub("[已隐藏的 OpenAI API Key]", text)


def print_status(ctx: RuntimeContext, *, check_latest: bool = True) -> int:
    print_title("Codex 状态")
    info = collect_system_info()
    print_kv("系统", info.os_name)
    print_kv("架构", info.arch)
    print_kv("包管理器", info.package_manager)
    print_kv("Codex 命令", _codex_bin() or "未找到")
    print_kv("Codex 版本", current_version(ctx))
    if check_latest:
        print_kv("npm latest", query_latest_version(ctx))
    print_kv("npm 命令", _npm_bin() or "未找到")
    print_kv("Codex 目录", codex_home())
    print_kv("配置文件", _file_summary(config_path()))
    print_kv("认证文件", _file_summary(auth_path()))
    print_kv("登录状态", login_status(ctx))
    print_kv("本次日志", ctx.logger.path)
    return 0


def _file_summary(path: Path) -> str:
    if not path.exists():
        return f"{path} 不存在"
    mode = stat.S_IMODE(path.stat().st_mode)
    summary = f"{path} 存在，大小 {path.stat().st_size} 字节，权限 {mode:04o}"
    if path.name == "auth.json" and mode != 0o600:
        summary += "（建议修正为 0600）"
    return summary


def install(ctx: RuntimeContext) -> int:
    npm = require_command("npm")
    print_title("安装 Codex CLI 最新版")
    print_kv("安装包", f"{CODEX_NPM_PACKAGE}@latest")
    print_kv("npm", npm)
    print_kv("当前版本", current_version(ctx))
    print_kv("latest", query_latest_version(ctx))

    if not confirm(ctx, "确认安装或覆盖安装 Codex CLI 最新版？"):
        print_step("已取消。")
        return 1

    run_command(ctx, [npm, "install", "-g", f"{CODEX_NPM_PACKAGE}@latest"], check=True, timeout=600, capture=False)
    if not ctx.dry_run:
        print_kv("安装后版本", current_version(ctx))
    return 0


def update(ctx: RuntimeContext, *, method: str = "auto") -> int:
    print_title("更新 Codex CLI")
    print_kv("当前版本", current_version(ctx))
    print_kv("latest", query_latest_version(ctx))

    if not confirm(ctx, "确认更新 Codex CLI 到最新版本？"):
        print_step("已取消。")
        return 1

    codex = _codex_bin()
    npm = _npm_bin()
    if method == "codex" or (method == "auto" and codex):
        run_command(ctx, [codex or "codex", "update"], check=True, timeout=600, capture=False)
    elif method in {"npm", "auto"}:
        if not npm:
            raise RuntimeError("未找到 npm，无法通过 npm 更新 Codex。")
        run_command(ctx, [npm, "install", "-g", f"{CODEX_NPM_PACKAGE}@latest"], check=True, timeout=600, capture=False)
    else:
        raise RuntimeError(f"未知更新方式：{method}")

    if not ctx.dry_run:
        print_kv("更新后版本", current_version(ctx))
    return 0


def uninstall(ctx: RuntimeContext, *, purge_config: bool = False) -> int:
    npm = require_command("npm")
    print_title("卸载 Codex CLI")
    print_warning("默认只卸载 npm 包，不删除 ~/.codex 下的配置、认证、历史和日志。")
    print_kv("当前版本", current_version(ctx))

    if not confirm(ctx, "确认卸载 Codex CLI？"):
        print_step("已取消。")
        return 1

    run_command(ctx, [npm, "uninstall", "-g", CODEX_NPM_PACKAGE], check=True, timeout=600, capture=False)

    if purge_config:
        print_warning("将备份并删除 config.toml 和 auth.json，不会删除会话数据库、日志和记忆文件。")
        if not confirm(ctx, "确认删除 Codex 配置文件和认证文件？", require_text="DELETE CODEX CONFIG"):
            print_step("已跳过配置和认证清理。")
            return 0
        backup_all(ctx)
        for path in (config_path(), auth_path()):
            if path.exists():
                print_step(f"删除 {path}")
                ctx.logger.info(f"remove {path}")
                if not ctx.dry_run:
                    path.unlink()

    return 0


def login(ctx: RuntimeContext, *, device_auth: bool = False) -> int:
    codex = require_command("codex")
    command = [codex, "login"]
    if device_auth:
        command.append("--device-auth")
    print_title("Codex 登录")
    print_warning("请按 Codex 的交互提示完成登录；本工具不会读取或打印认证密钥。")
    run_command(ctx, command, check=True, timeout=None, capture=False)
    return 0


def logout(ctx: RuntimeContext) -> int:
    codex = require_command("codex")
    print_title("Codex 登出")
    if not confirm(ctx, "确认移除本机保存的 Codex 登录凭据？"):
        print_step("已取消。")
        return 1
    backup_auth(ctx)
    run_command(ctx, [codex, "logout"], check=True, timeout=120, capture=False)
    return 0


def show_config(ctx: RuntimeContext, *, raw: bool = False) -> int:
    path = config_path()
    print_title("Codex 配置文件")
    print_kv("路径", path)
    if not path.exists():
        print_warning("配置文件不存在。")
        return 1

    text = path.read_text(encoding="utf-8", errors="replace")
    if not raw:
        text = redact_text(text)
    print(text)
    return 0


def edit_config(ctx: RuntimeContext) -> int:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Codex CLI 配置文件\n", encoding="utf-8")
        ensure_private_file(path)

    backup_config(ctx)
    editor = os.environ.get("EDITOR") or shutil.which("nano") or shutil.which("vim") or shutil.which("vi")
    if not editor:
        raise RuntimeError("未找到编辑器。请设置 EDITOR 环境变量，例如 EDITOR=vim。")
    print_step(f"使用编辑器打开：{path}")
    run_command(ctx, [*shlex.split(editor), str(path)], check=True, capture=False)
    ensure_private_file(path)
    validate_config_file(path)
    return 0


def set_config_value(ctx: RuntimeContext, key: str, value: str, *, value_type: str = "raw") -> int:
    if not SAFE_KEY_RE.match(key):
        raise RuntimeError("配置键只能包含字母、数字、下划线、点和短横线。")

    encoded_value = encode_toml_value(value, value_type=value_type)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_config(ctx)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        lines = ["# Codex CLI 配置文件"]

    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*).*$")
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if pattern.match(line):
            new_lines.append(f"{key} = {encoded_value}")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key} = {encoded_value}")

    new_text = "\n".join(new_lines) + "\n"
    validate_toml_text(new_text)
    print_step(f"写入配置：{key} = {encoded_value}")
    if not ctx.dry_run:
        path.write_text(new_text, encoding="utf-8")
        ensure_private_file(path)
    return 0


def encode_toml_value(value: str, *, value_type: str) -> str:
    if value_type == "string":
        return json.dumps(value, ensure_ascii=False)
    if value_type == "int":
        int(value)
        return value
    if value_type == "bool":
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "y", "是"}:
            return "true"
        if lowered in {"false", "0", "no", "n", "否"}:
            return "false"
        raise RuntimeError("布尔值请使用 true/false。")
    if value_type == "raw":
        validate_toml_text(f"x = {value}\n")
        return value
    raise RuntimeError(f"未知值类型：{value_type}")


def validate_toml_text(text: str) -> None:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"TOML 格式无效：{exc}") from exc


def validate_config_file(path: Path) -> None:
    if path.exists():
        validate_toml_text(path.read_text(encoding="utf-8", errors="replace"))


def backup_config(ctx: RuntimeContext) -> int:
    path = config_path()
    print_title("备份 Codex 配置")
    if not path.exists():
        print_warning(f"配置文件不存在：{path}")
        return 1
    if ctx.dry_run:
        print_step(f"[dry-run] 备份 {path} 到 {ctx.backup_dir / 'codex-config'}")
        return 0
    dest = backup_file(path, ctx.backup_dir, "codex-config")
    print_kv("备份文件", dest)
    return 0


def restore_config(ctx: RuntimeContext, source: Path) -> int:
    print_title("恢复 Codex 配置")
    source = source.expanduser().resolve()
    if not source.exists():
        raise RuntimeError(f"备份文件不存在：{source}")
    validate_config_file(source)
    if config_path().exists():
        backup_config(ctx)
    if not confirm(ctx, f"确认用 {source} 覆盖 {config_path()}？"):
        print_step("已取消。")
        return 1
    if not ctx.dry_run:
        config_path().parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, config_path())
        ensure_private_file(config_path())
    print_step("配置已恢复。")
    return 0


def auth_status(ctx: RuntimeContext) -> int:
    path = auth_path()
    print_title("Codex 认证文件")
    print_kv("路径", path)
    if not path.exists():
        print_warning("认证文件不存在。")
        return 1

    stat_result = path.stat()
    mode = stat.S_IMODE(stat_result.st_mode)
    print_kv("大小", f"{stat_result.st_size} 字节")
    print_kv("权限", f"{mode:04o}")
    if mode != 0o600:
        print_warning("认证文件权限不是 0600，建议运行 ./run.sh codex auth fix-perms。")
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        print_warning("认证文件不是有效 JSON，未显示内容结构。")
        return 1

    print_kv("结构", json.dumps(mask_json_value(data), ensure_ascii=False, indent=2))
    print_kv("登录状态", login_status(ctx))
    return 0


def backup_auth(ctx: RuntimeContext) -> int:
    path = auth_path()
    print_title("备份 Codex 认证文件")
    if not path.exists():
        print_warning(f"认证文件不存在：{path}")
        return 1
    if ctx.dry_run:
        print_step(f"[dry-run] 备份 {path} 到 {ctx.backup_dir / 'codex-auth'}")
        return 0
    dest = backup_file(path, ctx.backup_dir, "codex-auth")
    print_kv("备份文件", dest)
    return 0


def import_auth(ctx: RuntimeContext, source: Path) -> int:
    print_title("导入 Codex 认证文件")
    source = source.expanduser().resolve()
    if not source.exists():
        raise RuntimeError(f"认证文件不存在：{source}")

    try:
        json.loads(source.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"导入文件不是有效 JSON：{exc}") from exc

    if auth_path().exists():
        backup_auth(ctx)
    if not confirm(ctx, f"确认用 {source} 覆盖 {auth_path()}？"):
        print_step("已取消。")
        return 1
    if not ctx.dry_run:
        auth_path().parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, auth_path())
        ensure_private_file(auth_path())
    print_step("认证文件已导入。")
    return 0


def fix_auth_permissions(ctx: RuntimeContext) -> int:
    path = auth_path()
    print_title("修正 Codex 认证文件权限")
    if not path.exists():
        print_warning(f"认证文件不存在：{path}")
        return 1
    if ctx.dry_run:
        print_step(f"[dry-run] chmod 600 {path}")
    else:
        print_step(f"设置权限：chmod 600 {path}")
        ensure_private_file(path)
    return 0


def backup_all(ctx: RuntimeContext) -> int:
    print_title("备份 Codex 目录")
    home = codex_home()
    if not home.exists():
        print_warning(f"Codex 目录不存在：{home}")
        return 1
    if ctx.dry_run:
        print_step(f"[dry-run] 备份 {home} 到 {ctx.backup_dir / 'codex-home'}")
        return 0
    dest = backup_directory(home, ctx.backup_dir, "codex-home")
    print_kv("备份文件", dest)
    return 0
