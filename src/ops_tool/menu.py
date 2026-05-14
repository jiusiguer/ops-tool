from __future__ import annotations

from collections.abc import Callable
from typing import Final

from .context import RuntimeContext
from .tasks import ccswitch, codex, proxy
from .ui import print_error, print_title


MenuAction = Callable[[RuntimeContext], object]
NO_PAUSE: Final = "NO_PAUSE"


def run_interactive(ctx: RuntimeContext) -> int:
    while True:
        print_title("一键化服务器运维工具")
        print("1. Codex 管理")
        print("2. 代理服务搭建")
        print("0. 退出")

        choice = read_choice("请选择操作：")
        try:
            if choice == "1":
                run_codex_menu(ctx)
            elif choice == "2":
                run_proxy_menu(ctx)
            elif choice == "0":
                return 0
            else:
                print_error("无效选择。")
        except Exception as exc:  # noqa: BLE001 - interactive mode should keep running.
            ctx.logger.error(str(exc))
            print_error(str(exc))


def read_choice(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "0"


def wait_return() -> None:
    try:
        input("\n按回车返回上一级菜单...")
    except EOFError:
        return


def run_menu(ctx: RuntimeContext, title: str, items: list[tuple[str, MenuAction]]) -> int:
    while True:
        print_title(title)
        for index, (label, _) in enumerate(items, start=1):
            print(f"{index}. {label}")
        print("0. 返回")

        choice = read_choice("请选择操作：")
        if choice == "0":
            return 0

        try:
            selected = int(choice)
        except ValueError:
            print_error("无效选择。")
            continue

        if not 1 <= selected <= len(items):
            print_error("无效选择。")
            continue

        try:
            result = items[selected - 1][1](ctx)
        except Exception as exc:  # noqa: BLE001 - interactive mode should keep running.
            ctx.logger.error(str(exc))
            print_error(str(exc))
            result = None

        if result != NO_PAUSE:
            wait_return()


def run_codex_menu(ctx: RuntimeContext) -> int:
    return run_menu(
        ctx,
        "Codex 管理",
        [
            ("查看 Codex 总状态", lambda inner: codex.print_status(inner)),
            ("Codex CLI 安装 / 更新 / 卸载", run_codex_cli_menu),
            ("Codex 登录和认证文件", run_codex_auth_menu),
            ("Codex config.toml 配置文件", run_codex_config_menu),
            ("cc-switch Codex 统一配置面板", run_ccswitch_menu),
        ],
    )


def run_codex_cli_menu(ctx: RuntimeContext) -> str:
    run_menu(
        ctx,
        "Codex CLI 安装 / 更新 / 卸载",
        [
            ("安装 Codex 最新版", lambda inner: codex.install(inner)),
            ("更新 Codex", lambda inner: codex.update(inner)),
            ("卸载 Codex", lambda inner: codex.uninstall(inner)),
        ],
    )
    return NO_PAUSE


def run_codex_auth_menu(ctx: RuntimeContext) -> str:
    run_menu(
        ctx,
        "Codex 登录和认证文件",
        [
            ("Codex 登录", lambda inner: codex.login(inner)),
            ("Codex 登出", lambda inner: codex.logout(inner)),
            ("查看认证文件状态", lambda inner: codex.auth_status(inner)),
            ("备份认证文件", lambda inner: codex.backup_auth(inner)),
            ("修正认证文件权限为 0600", lambda inner: codex.fix_auth_permissions(inner)),
        ],
    )
    return NO_PAUSE


def run_codex_config_menu(ctx: RuntimeContext) -> str:
    run_menu(
        ctx,
        "Codex config.toml 配置文件",
        [
            ("查看配置", lambda inner: codex.show_config(inner)),
            ("编辑配置", lambda inner: codex.edit_config(inner)),
            ("备份配置", lambda inner: codex.backup_config(inner)),
        ],
    )
    return NO_PAUSE


def run_ccswitch_menu(ctx: RuntimeContext) -> str:
    run_menu(
        ctx,
        "cc-switch Codex 统一配置面板",
        [
            ("查看 cc-switch 状态", lambda inner: ccswitch.status(inner)),
            ("打开 cc-switch Codex 交互面板", lambda inner: ccswitch.launch_panel(inner)),
            ("安装 / 覆盖安装 cc-switch", lambda inner: ccswitch.install(inner)),
            ("更新 cc-switch", lambda inner: ccswitch.update(inner)),
            ("查看当前 Provider", lambda inner: ccswitch.provider_current(inner)),
            ("列出 Provider", lambda inner: ccswitch.provider_list(inner)),
            ("切换 Provider", switch_provider_prompt),
            ("查看 MCP 列表", lambda inner: ccswitch.mcp_list(inner)),
            ("从 Codex 导入 MCP 到 cc-switch", lambda inner: ccswitch.mcp_import(inner)),
            ("同步 MCP 到 Codex live 配置", lambda inner: ccswitch.mcp_sync(inner)),
            ("查看 Prompt 预设", lambda inner: ccswitch.prompts_list(inner)),
            ("查看 Skill 列表", lambda inner: ccswitch.skills_list(inner)),
            ("同步 Skill 到 Codex", lambda inner: ccswitch.skills_sync(inner)),
            ("检查环境变量冲突", lambda inner: ccswitch.env_check(inner)),
            ("检查本机 CLI 工具", lambda inner: ccswitch.env_tools(inner)),
        ],
    )
    return NO_PAUSE


def switch_provider_prompt(ctx: RuntimeContext) -> int:
    ccswitch.provider_list(ctx)
    provider_id = read_choice("\n请输入要切换的 Provider ID：")
    return ccswitch.provider_switch(ctx, provider_id)


def run_proxy_menu(ctx: RuntimeContext) -> int:
    run_menu(
        ctx,
        "代理服务搭建",
        [
            ("查看代理服务状态", lambda inner: proxy.status(inner)),
            ("查看协议文档来源", lambda inner: proxy.docs(inner)),
            ("安装 / 更新 Xray core", lambda inner: proxy.install_xray(inner)),
            ("安装 / 更新 sing-box core", lambda inner: proxy.install_sing_box(inner)),
            ("修复 Xray 配置权限并重启", lambda inner: proxy.repair_xray_permissions(inner, restart=True)),
            ("一键部署默认 VLESS + REALITY + XHTTP", lambda inner: proxy.deploy_vless_default(inner)),
            ("一键部署默认 Hysteria2 / HY2", lambda inner: proxy.deploy_hy2_default(inner)),
            ("部署 VLESS + REALITY + XHTTP", deploy_vless_prompt),
            ("部署 Hysteria2 / HY2", deploy_hy2_prompt),
        ],
    )
    return 0


def prompt_default(label: str, default: str) -> str:
    value = read_choice(f"{label} [{default}]：")
    return value or default


def prompt_int(label: str, default: int) -> int:
    value = prompt_default(label, str(default))
    return int(value)


def prompt_yes_no(label: str, default: bool) -> bool:
    default_text = "y" if default else "n"
    value = prompt_default(label, default_text).lower()
    return value in {"y", "yes", "1", "true", "是", "好"}


def deploy_vless_prompt(ctx: RuntimeContext) -> int:
    server = prompt_default("服务器公网 IP 或域名", proxy.guess_public_server())
    port = prompt_int("监听端口 TCP", 443)
    server_name = prompt_default("REALITY SNI / serverName", "www.microsoft.com")
    reality_target = prompt_default("REALITY 回落目标 target", f"{server_name}:443")
    path = prompt_default("XHTTP path", "/xhttp")
    mode = prompt_default("XHTTP mode", "auto")
    remark = prompt_default("备注", "ops-vless-reality-xhttp")
    open_firewall = prompt_yes_no("是否尝试放行本机防火墙端口", False)
    return proxy.deploy_vless_reality_xhttp(
        ctx,
        server=server,
        port=port,
        server_name=server_name,
        reality_target=reality_target,
        path=path,
        xhttp_mode=mode,
        open_firewall=open_firewall,
        remark=remark,
    )


def deploy_hy2_prompt(ctx: RuntimeContext) -> int:
    server = prompt_default("服务器公网 IP 或域名", proxy.guess_public_server())
    port = prompt_int("监听端口 UDP", 443)
    server_name = prompt_default("TLS SNI / 证书 CN", server)
    up_mbps = prompt_int("服务端上行 Mbps", 100)
    down_mbps = prompt_int("服务端下行 Mbps", 100)
    self_signed = prompt_yes_no("是否自动生成自签证书", True)
    remark = prompt_default("备注", "ops-hy2")
    open_firewall = prompt_yes_no("是否尝试放行本机防火墙端口", False)
    return proxy.deploy_hy2(
        ctx,
        server=server,
        port=port,
        server_name=server_name,
        up_mbps=up_mbps,
        down_mbps=down_mbps,
        self_signed=self_signed,
        open_firewall=open_firewall,
        remark=remark,
    )
