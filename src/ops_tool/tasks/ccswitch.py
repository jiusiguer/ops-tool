from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..context import RuntimeContext
from ..shell import CommandResult, run_command
from ..ui import confirm, print_kv, print_step, print_title, print_warning

CC_SWITCH_REPO = "SaladDay/cc-switch-cli"
INSTALL_SCRIPT_URL = "https://github.com/SaladDay/cc-switch-cli/releases/latest/download/install.sh"
APP_NAME = "codex"


def install_dir() -> Path:
    return Path(os.environ.get("CC_SWITCH_INSTALL_DIR", "~/.local/bin")).expanduser()


def cc_switch_bin() -> str | None:
    preferred = install_dir() / "cc-switch"
    if preferred.exists() and os.access(preferred, os.X_OK):
        return str(preferred)
    return shutil.which("cc-switch")


def _first_line(result: CommandResult) -> str:
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0] if text else ""


def version(ctx: RuntimeContext) -> str:
    binary = cc_switch_bin()
    if not binary:
        return "未安装或不在 PATH 中"
    result = run_command(ctx, [binary, "--version"], timeout=10, capture=True, dry_run_execute=True)
    if result.ok:
        return _first_line(result) or "unknown"
    return "检测失败：" + (result.stderr.strip() or result.stdout.strip() or f"rc={result.returncode}")


def run_cc_switch(
    ctx: RuntimeContext,
    args: list[str],
    *,
    app: bool = True,
    check: bool = False,
    capture: bool = False,
    timeout: int | None = None,
    dry_run_execute: bool = False,
) -> CommandResult:
    binary = cc_switch_bin()
    if not binary:
        raise RuntimeError("未找到 cc-switch。请先运行 ./run.sh ccswitch install。")
    command = [binary]
    if app:
        command.extend(["--app", APP_NAME])
    command.extend(args)
    return run_command(
        ctx,
        command,
        check=check,
        capture=capture,
        timeout=timeout,
        dry_run_execute=dry_run_execute,
    )


def install(ctx: RuntimeContext) -> int:
    print_title("安装 cc-switch-cli")
    print_kv("项目", f"https://github.com/{CC_SWITCH_REPO}")
    print_kv("目标目录", install_dir())
    print_kv("当前版本", version(ctx))

    if not confirm(ctx, "确认安装或更新 cc-switch 到用户目录？"):
        print_step("已取消。")
        return 1

    env = {
        "CC_SWITCH_INSTALL_DIR": str(install_dir()),
        "CC_SWITCH_FORCE": "1",
    }
    run_command(
        ctx,
        ["bash", "-lc", f"curl -fsSL {INSTALL_SCRIPT_URL} | bash"],
        env=env,
        check=True,
        timeout=600,
        capture=False,
    )
    if not ctx.dry_run:
        print_kv("安装后版本", version(ctx))
        print_kv("命令路径", cc_switch_bin() or "未找到")
    return 0


def update(ctx: RuntimeContext) -> int:
    print_title("更新 cc-switch-cli")
    print_kv("当前版本", version(ctx))
    if not confirm(ctx, "确认通过 cc-switch update 更新？"):
        print_step("已取消。")
        return 1
    run_cc_switch(ctx, ["update"], app=False, check=True, timeout=600, capture=False)
    if not ctx.dry_run:
        print_kv("更新后版本", version(ctx))
    return 0


def status(ctx: RuntimeContext) -> int:
    print_title("cc-switch Codex 面板状态")
    print_kv("命令路径", cc_switch_bin() or "未找到")
    print_kv("版本", version(ctx))
    print_kv("配置目录", Path("~/.cc-switch").expanduser())
    print_kv("Codex live 配置", Path("~/.codex/config.toml").expanduser())
    print_kv("Codex live 认证", Path("~/.codex/auth.json").expanduser())

    if not cc_switch_bin():
        return 1

    print_title("cc-switch 配置路径")
    run_cc_switch(ctx, ["config", "path"], check=False, capture=False, timeout=30, dry_run_execute=True)

    print_title("当前 Codex Provider")
    run_cc_switch(ctx, ["provider", "current"], check=False, capture=False, timeout=30, dry_run_execute=True)

    print_title("本机 CLI 工具检查")
    run_cc_switch(ctx, ["env", "tools"], app=False, check=False, capture=False, timeout=30, dry_run_execute=True)
    return 0


def launch_panel(ctx: RuntimeContext) -> int:
    print_title("打开 cc-switch Codex 统一配置面板")
    print_warning("接下来进入 cc-switch 的交互界面；其中 provider/token 等敏感数据由 cc-switch 自己管理。")
    run_cc_switch(ctx, ["interactive"], check=True, capture=False)
    return 0


def provider_list(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["provider", "list"], check=False, capture=False, timeout=60).returncode


def provider_current(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["provider", "current"], check=False, capture=False, timeout=30).returncode


def provider_switch(ctx: RuntimeContext, provider_id: str) -> int:
    if not provider_id:
        raise RuntimeError("Provider ID 不能为空。")
    return run_cc_switch(ctx, ["provider", "switch", provider_id], check=True, capture=False, timeout=60).returncode


def config_path(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["config", "path"], check=False, capture=False, timeout=30).returncode


def config_backup(ctx: RuntimeContext) -> int:
    if not confirm(ctx, "确认让 cc-switch 备份当前配置？"):
        print_step("已取消。")
        return 1
    return run_cc_switch(ctx, ["config", "backup"], check=True, capture=False, timeout=120).returncode


def config_validate(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["config", "validate"], check=False, capture=False, timeout=60).returncode


def mcp_list(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["mcp", "list"], check=False, capture=False, timeout=60).returncode


def mcp_import(ctx: RuntimeContext) -> int:
    if not confirm(ctx, "确认从 Codex live 配置导入 MCP 到 cc-switch？"):
        print_step("已取消。")
        return 1
    return run_cc_switch(ctx, ["mcp", "import"], check=True, capture=False, timeout=120).returncode


def mcp_sync(ctx: RuntimeContext) -> int:
    print_warning("该操作会把 cc-switch 的 MCP 配置同步到 Codex live 配置文件。")
    if not confirm(ctx, "确认同步 MCP 配置到 Codex？"):
        print_step("已取消。")
        return 1
    return run_cc_switch(ctx, ["mcp", "sync"], check=True, capture=False, timeout=120).returncode


def prompts_list(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["prompts", "list"], check=False, capture=False, timeout=60).returncode


def prompts_current(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["prompts", "current"], check=False, capture=False, timeout=30).returncode


def skills_list(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["skills", "list"], check=False, capture=False, timeout=60).returncode


def skills_sync(ctx: RuntimeContext) -> int:
    print_warning("该操作会把 cc-switch 管理的技能同步到 Codex skills 目录。")
    if not confirm(ctx, "确认同步技能到 Codex？"):
        print_step("已取消。")
        return 1
    return run_cc_switch(ctx, ["skills", "sync"], check=True, capture=False, timeout=120).returncode


def env_check(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["env", "check"], app=False, check=False, capture=False, timeout=60).returncode


def env_tools(ctx: RuntimeContext) -> int:
    return run_cc_switch(ctx, ["env", "tools"], app=False, check=False, capture=False, timeout=60).returncode


def start_codex(ctx: RuntimeContext, selector: str, native_args: list[str] | None = None) -> int:
    if not selector:
        raise RuntimeError("Provider 选择器不能为空。")
    command = ["start", "codex", selector]
    if native_args:
        command.append("--")
        command.extend(native_args)
    return run_cc_switch(ctx, command, app=False, check=True, capture=False).returncode
