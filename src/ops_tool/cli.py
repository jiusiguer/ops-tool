from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .context import RuntimeContext
from .log import OpsLogger
from .menu import run_interactive
from .tasks import ccswitch, codex, proxy
from .ui import print_error


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ops-tool",
        description="中文 Linux 服务器运维工具。无参数运行时进入交互菜单。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只展示将执行的操作，不实际修改系统")
    parser.add_argument("-y", "--yes", action="store_true", help="自动确认普通确认提示")
    parser.add_argument("-v", "--verbose", action="store_true", help="记录更详细的命令输出")

    subparsers = parser.add_subparsers(dest="module")
    codex_parser = subparsers.add_parser("codex", help="安装、更新、卸载和管理 Codex CLI")
    codex_sub = codex_parser.add_subparsers(dest="action")

    codex_sub.add_parser("status", help="查看 Codex 安装、版本、配置和登录状态")
    codex_sub.add_parser("panel", help="打开 cc-switch Codex 统一配置面板")
    codex_sub.add_parser("install", help="通过 npm 安装 @openai/codex@latest")

    update_parser = codex_sub.add_parser("update", help="更新 Codex 到最新版")
    update_parser.add_argument("--method", choices=("auto", "codex", "npm"), default="auto", help="更新方式")

    uninstall_parser = codex_sub.add_parser("uninstall", help="卸载 Codex CLI")
    uninstall_parser.add_argument(
        "--purge-config",
        action="store_true",
        help="卸载后备份并删除 config.toml 和 auth.json",
    )

    login_parser = codex_sub.add_parser("login", help="运行 codex login")
    login_parser.add_argument("--device-auth", action="store_true", help="使用设备码登录流程")
    codex_sub.add_parser("logout", help="备份认证文件后运行 codex logout")

    config_parser = codex_sub.add_parser("config", help="管理 ~/.codex/config.toml")
    config_sub = config_parser.add_subparsers(dest="config_action")
    show_parser = config_sub.add_parser("show", help="显示配置文件，默认隐藏敏感字段")
    show_parser.add_argument("--raw", action="store_true", help="原样显示配置文件，谨慎使用")
    config_sub.add_parser("edit", help="用 EDITOR/nano/vim 编辑配置文件")
    set_parser = config_sub.add_parser("set", help="设置简单 TOML 配置项")
    set_parser.add_argument("key", help="配置键，例如 model 或 sandbox_mode")
    set_parser.add_argument("value", help="配置值")
    set_parser.add_argument(
        "--type",
        choices=("raw", "string", "int", "bool"),
        default="raw",
        help="值类型；raw 会按 TOML 片段解析",
    )
    config_sub.add_parser("backup", help="备份配置文件")
    restore_parser = config_sub.add_parser("restore", help="从备份恢复配置文件")
    restore_parser.add_argument("file", type=Path, help="备份文件路径")

    auth_parser = codex_sub.add_parser("auth", help="管理 ~/.codex/auth.json")
    auth_sub = auth_parser.add_subparsers(dest="auth_action")
    auth_sub.add_parser("status", help="查看认证文件状态，隐藏具体密钥")
    auth_sub.add_parser("backup", help="备份认证文件")
    auth_sub.add_parser("fix-perms", help="将认证文件权限修正为 0600")
    import_parser = auth_sub.add_parser("import", help="导入认证 JSON 文件")
    import_parser.add_argument("file", type=Path, help="认证 JSON 文件路径")

    backup_parser = codex_sub.add_parser("backup", help="备份 Codex 数据")
    backup_parser.add_argument("--all", action="store_true", help="备份整个 Codex 目录")

    ccswitch_parser = subparsers.add_parser("ccswitch", help="安装和调用 cc-switch Codex 配置面板")
    ccswitch_sub = ccswitch_parser.add_subparsers(dest="action")
    ccswitch_sub.add_parser("status", help="查看 cc-switch 和 Codex 配置面板状态")
    ccswitch_sub.add_parser("install", help="安装或覆盖安装 cc-switch-cli")
    ccswitch_sub.add_parser("update", help="更新 cc-switch-cli")
    ccswitch_sub.add_parser("launch", help="打开 cc-switch --app codex interactive")
    ccswitch_sub.add_parser("provider-current", help="查看当前 Codex Provider")
    ccswitch_sub.add_parser("provider-list", help="列出 Codex Provider")
    provider_switch = ccswitch_sub.add_parser("provider-switch", help="切换 Codex Provider")
    provider_switch.add_argument("provider_id", help="cc-switch Provider ID")
    ccswitch_sub.add_parser("config-path", help="查看 cc-switch 配置路径")
    ccswitch_sub.add_parser("config-backup", help="让 cc-switch 备份当前配置")
    ccswitch_sub.add_parser("config-validate", help="校验 cc-switch 配置")
    ccswitch_sub.add_parser("mcp-list", help="列出 MCP")
    ccswitch_sub.add_parser("mcp-import", help="从 Codex live 配置导入 MCP")
    ccswitch_sub.add_parser("mcp-sync", help="同步 MCP 到 Codex live 配置")
    ccswitch_sub.add_parser("prompts-list", help="列出 Prompt 预设")
    ccswitch_sub.add_parser("prompts-current", help="查看当前 Prompt")
    ccswitch_sub.add_parser("skills-list", help="列出 Skill")
    ccswitch_sub.add_parser("skills-sync", help="同步 Skill 到 Codex")
    ccswitch_sub.add_parser("env-check", help="检查环境变量冲突")
    ccswitch_sub.add_parser("env-tools", help="检查本机 CLI 工具")
    start_parser = ccswitch_sub.add_parser("start-codex", help="用指定 Provider 启动 Codex")
    start_parser.add_argument("selector", help="Provider ID 或名称")
    start_parser.add_argument("native_args", nargs=argparse.REMAINDER, help="传给 codex 的原生命令参数，使用 -- 分隔")

    proxy_parser = subparsers.add_parser("proxy", help="一键搭建常见代理协议组合")
    proxy_sub = proxy_parser.add_subparsers(dest="action")
    proxy_sub.add_parser("status", help="查看 Xray / sing-box 安装和服务状态")
    proxy_sub.add_parser("docs", help="显示当前功能参考的官方协议文档")
    proxy_sub.add_parser("install-xray", help="安装或更新 Xray core")
    proxy_sub.add_parser("install-sing-box", help="安装或更新 sing-box core")
    proxy_sub.add_parser("repair-xray-perms", help="修复 Xray config.json 权限并重启服务")

    vless_default_parser = proxy_sub.add_parser("deploy-vless-default", help="使用默认配置一键部署 VLESS + REALITY + XHTTP")
    vless_default_parser.add_argument("--server", default=None, help="客户端连接用的公网 IP 或域名；不填则自动检测")

    hy2_default_parser = proxy_sub.add_parser("deploy-hy2-default", help="使用默认配置一键部署 Hysteria2 / HY2")
    hy2_default_parser.add_argument("--server", default=None, help="客户端连接用的公网 IP 或域名；不填则自动检测")

    vless_parser = proxy_sub.add_parser("deploy-vless-reality-xhttp", help="部署 VLESS + REALITY + XHTTP")
    add_common_deploy_args(vless_parser)
    vless_parser.add_argument("--reality-target", default="www.microsoft.com:443", help="REALITY target 回落目标")
    vless_parser.add_argument("--server-name", default="www.microsoft.com", help="REALITY serverName/SNI")
    vless_parser.add_argument("--path", default="/xhttp", help="XHTTP path")
    vless_parser.add_argument("--xhttp-mode", default="auto", help="XHTTP mode")
    vless_parser.add_argument("--email", default="ops-tool@local", help="Xray client email 标识")

    hy2_parser = proxy_sub.add_parser("deploy-hy2", help="通过 sing-box 部署 Hysteria2 / HY2")
    add_common_deploy_args(hy2_parser)
    hy2_parser.add_argument("--server-name", default=None, help="TLS server_name；默认使用 --server")
    hy2_parser.add_argument("--user", default="default", help="HY2 用户名")
    hy2_parser.add_argument("--password", default=None, help="HY2 密码；默认自动生成")
    hy2_parser.add_argument("--obfs-password", default=None, help="HY2 salamander 混淆密码；默认自动生成")
    hy2_parser.add_argument("--up-mbps", type=int, default=100, help="服务端上行 Mbps")
    hy2_parser.add_argument("--down-mbps", type=int, default=100, help="服务端下行 Mbps")
    hy2_parser.add_argument("--cert-path", type=Path, default=None, help="已有证书路径")
    hy2_parser.add_argument("--key-path", type=Path, default=None, help="已有私钥路径")
    hy2_parser.add_argument("--no-self-signed", action="store_true", help="不自动生成自签证书")

    return parser


def add_common_deploy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--server", default=proxy.guess_public_server(), help="客户端连接用的公网 IP 或域名")
    parser.add_argument("--port", type=int, default=443, help="监听端口")
    parser.add_argument("--listen", default="0.0.0.0", help="监听地址")
    parser.add_argument("--remark", default=None, help="客户端备注")
    parser.add_argument("--no-install-core", action="store_true", help="缺少核心时不自动安装")
    parser.add_argument("--no-start", action="store_true", help="只写配置，不启动或重启服务")
    parser.add_argument("--open-firewall", action="store_true", help="尝试放行本机 ufw/firewalld 端口")


def dispatch(args: argparse.Namespace, ctx: RuntimeContext) -> int:
    if args.module is None:
        return run_interactive(ctx)

    if args.module == "ccswitch":
        return dispatch_ccswitch(args, ctx)

    if args.module == "proxy":
        return dispatch_proxy(args, ctx)

    if args.module != "codex":
        raise RuntimeError(f"未知模块：{args.module}")

    action = args.action
    if action == "status":
        return codex.print_status(ctx)
    if action == "panel":
        return ccswitch.launch_panel(ctx)
    if action == "install":
        return codex.install(ctx)
    if action == "update":
        return codex.update(ctx, method=args.method)
    if action == "uninstall":
        return codex.uninstall(ctx, purge_config=args.purge_config)
    if action == "login":
        return codex.login(ctx, device_auth=args.device_auth)
    if action == "logout":
        return codex.logout(ctx)
    if action == "config":
        return dispatch_config(args, ctx)
    if action == "auth":
        return dispatch_auth(args, ctx)
    if action == "backup":
        if args.all:
            return codex.backup_all(ctx)
        rc1 = codex.backup_config(ctx)
        rc2 = codex.backup_auth(ctx)
        return 0 if rc1 == 0 or rc2 == 0 else 1

    raise RuntimeError("缺少 Codex 子命令。可运行 ./run.sh codex --help 查看帮助。")


def dispatch_ccswitch(args: argparse.Namespace, ctx: RuntimeContext) -> int:
    action = args.action
    if action == "status":
        return ccswitch.status(ctx)
    if action == "install":
        return ccswitch.install(ctx)
    if action == "update":
        return ccswitch.update(ctx)
    if action == "launch":
        return ccswitch.launch_panel(ctx)
    if action == "provider-current":
        return ccswitch.provider_current(ctx)
    if action == "provider-list":
        return ccswitch.provider_list(ctx)
    if action == "provider-switch":
        return ccswitch.provider_switch(ctx, args.provider_id)
    if action == "config-path":
        return ccswitch.config_path(ctx)
    if action == "config-backup":
        return ccswitch.config_backup(ctx)
    if action == "config-validate":
        return ccswitch.config_validate(ctx)
    if action == "mcp-list":
        return ccswitch.mcp_list(ctx)
    if action == "mcp-import":
        return ccswitch.mcp_import(ctx)
    if action == "mcp-sync":
        return ccswitch.mcp_sync(ctx)
    if action == "prompts-list":
        return ccswitch.prompts_list(ctx)
    if action == "prompts-current":
        return ccswitch.prompts_current(ctx)
    if action == "skills-list":
        return ccswitch.skills_list(ctx)
    if action == "skills-sync":
        return ccswitch.skills_sync(ctx)
    if action == "env-check":
        return ccswitch.env_check(ctx)
    if action == "env-tools":
        return ccswitch.env_tools(ctx)
    if action == "start-codex":
        native_args = args.native_args
        if native_args and native_args[0] == "--":
            native_args = native_args[1:]
        return ccswitch.start_codex(ctx, args.selector, native_args)
    raise RuntimeError("缺少 ccswitch 子命令。可运行 ./run.sh ccswitch --help 查看帮助。")


def dispatch_proxy(args: argparse.Namespace, ctx: RuntimeContext) -> int:
    action = args.action
    if action == "status":
        return proxy.status(ctx)
    if action == "docs":
        return proxy.docs(ctx)
    if action == "install-xray":
        return proxy.install_xray(ctx)
    if action == "install-sing-box":
        return proxy.install_sing_box(ctx)
    if action == "repair-xray-perms":
        return proxy.repair_xray_permissions(ctx, restart=True)
    if action == "deploy-vless-default":
        return proxy.deploy_vless_default(ctx, server=args.server)
    if action == "deploy-hy2-default":
        return proxy.deploy_hy2_default(ctx, server=args.server)
    if action == "deploy-vless-reality-xhttp":
        return proxy.deploy_vless_reality_xhttp(
            ctx,
            server=args.server,
            port=args.port,
            listen=args.listen,
            reality_target=args.reality_target,
            server_name=args.server_name,
            path=args.path,
            xhttp_mode=args.xhttp_mode,
            email=args.email,
            install_core=not args.no_install_core,
            start=not args.no_start,
            open_firewall=args.open_firewall,
            remark=args.remark or "ops-vless-reality-xhttp",
        )
    if action == "deploy-hy2":
        return proxy.deploy_hy2(
            ctx,
            server=args.server,
            port=args.port,
            listen=args.listen if args.listen != "0.0.0.0" else "::",
            server_name=args.server_name,
            user=args.user,
            password=args.password,
            obfs_password=args.obfs_password,
            up_mbps=args.up_mbps,
            down_mbps=args.down_mbps,
            cert_path=args.cert_path,
            key_path=args.key_path,
            self_signed=not args.no_self_signed,
            install_core=not args.no_install_core,
            start=not args.no_start,
            open_firewall=args.open_firewall,
            remark=args.remark or "ops-hy2",
        )
    raise RuntimeError("缺少 proxy 子命令。可运行 ./run.sh proxy --help 查看帮助。")


def dispatch_config(args: argparse.Namespace, ctx: RuntimeContext) -> int:
    action = args.config_action
    if action == "show":
        return codex.show_config(ctx, raw=args.raw)
    if action == "edit":
        return codex.edit_config(ctx)
    if action == "set":
        return codex.set_config_value(ctx, args.key, args.value, value_type=args.type)
    if action == "backup":
        return codex.backup_config(ctx)
    if action == "restore":
        return codex.restore_config(ctx, args.file)
    raise RuntimeError("缺少 config 子命令。可运行 ./run.sh codex config --help 查看帮助。")


def dispatch_auth(args: argparse.Namespace, ctx: RuntimeContext) -> int:
    action = args.auth_action
    if action == "status":
        return codex.auth_status(ctx)
    if action == "backup":
        return codex.backup_auth(ctx)
    if action == "fix-perms":
        return codex.fix_auth_permissions(ctx)
    if action == "import":
        return codex.import_auth(ctx, args.file)
    raise RuntimeError("缺少 auth 子命令。可运行 ./run.sh codex auth --help 查看帮助。")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = project_root()
    logger = OpsLogger(root / "logs", verbose=args.verbose)
    ctx = RuntimeContext(
        root=root,
        dry_run=args.dry_run,
        assume_yes=args.yes,
        verbose=args.verbose,
        logger=logger,
    )
    try:
        return dispatch(args, ctx)
    except KeyboardInterrupt:
        print_error("已中断。")
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary should render friendly errors.
        logger.error(str(exc))
        print_error(str(exc))
        print(f"日志文件：{logger.path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
